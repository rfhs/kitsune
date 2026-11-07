"""The nRF52840 802.15.4 sniffer, a pcap stream for tshark and the Zigbee checks.

The dongle runs Nordic's 802.15.4 sniffer firmware (USB id 1915:154A), the one
Kismet and Wireshark's extcap drive. It speaks plain text over its serial port:
``channel N``, ``receive`` and ``sleep``, each ending in CRLF, and reports every
frame it hears as one line::

    received: <hex frame without FCS> power: <dBm> lqi: <0-255> time: <us>

``Pump`` runs on a thread, turns those lines into pcap records and writes them
to a FIFO that tshark reads with ``-r``. The pcap has link type 283
(IEEE802_15_4_TAP); every record carries a 28 byte TAP header, version 0 and
length 28, then three TLVs: RSS (type 1, a float in dBm), channel assignment
(type 3, channel number and page 0) and LQI (type 10), then the frame. tshark
then decodes the 802.15.4 and Zigbee NWK layers and prints the fields the
checks need, which keeps every protocol detail in Wireshark's dissectors.

The periodic packet is the NWK Link Status the coordinator broadcasts every
``PACKET_INTERVAL`` seconds. It is an NWK command frame to the routers-only
broadcast address 0xFFFC from short address 0x0000. When the NWK payload is in
the clear, ``zbee_nwk.cmd.id`` says 0x08; when the network key encrypts it, the
frame type and destination in the clear header still identify it, and nothing
else a lone coordinator sends has that shape. The coordinator's IEEE address
comes from whichever header carries it: the MAC frame's extended source, the
NWK header's extended source, or the NWK security header's source.

``PACKET_INTERVAL`` needs two Link Status frames: the first may arrive after a
full interval, the second one interval later. ``interval_fits`` decides before
the capture whether that fits in the time left and gives the reason for the
``unverified`` row when it does not.
"""
from __future__ import annotations

import os
import re
import stat
import struct
import subprocess
import tempfile
import threading
import time
from typing import Callable, List, NamedTuple, Optional

from . import tshark
from .conf import Block, format_u16
from .report import Deadline, FAIL, NOT_PRINTED, PASS, Report, RunError, UNVERIFIED
from .serial_fox import Readback

BAUD = 115200
# Seconds a serial read waits before the pump checks whether it should stop.
SERIAL_POLL = 0.2
# Seconds allowed on top of two intervals for tshark to start and the sniffer
# to tune before the first Link Status can be heard.
LINK_STATUS_MARGIN = 2.0
# How far the measured gap may sit from PACKET_INTERVAL and still pass.
INTERVAL_TOLERANCE = 1.0
# Seconds spent waiting for tshark to open the FIFO before giving up.
FIFO_OPEN_POLL = 0.05

PCAP_MAGIC = 0xA1B2C3D4
PCAP_VERSION = (2, 4)
PCAP_SNAPLEN = 255
LINKTYPE_IEEE802_15_4_TAP = 283
TAP_HEADER_LENGTH = 28

LINK_STATUS = 0x08
NWK_COMMAND = 0x1
ROUTERS_BROADCAST = 0xFFFC
COORDINATOR_SHORT = 0x0000

FIELDS = ("frame.time_epoch", "wpan-tap.ch_num", "wpan.src_pan", "wpan.dst_pan", "wpan.src16",
          "wpan.src64", "zbee_nwk.frame_type", "zbee_nwk.cmd.id", "zbee_nwk.src", "zbee_nwk.dst",
          "zbee_nwk.src64", "zbee.sec.src64")

RECEIVED = re.compile(r"received:\s+([0-9a-fA-F]+)\s+power:\s+(-?\d+)\s+lqi:\s+(\d+)\s+time:\s+(-?\d+)")


class Captured(NamedTuple):
    """One frame as the sniffer reported it."""

    frame: bytes
    power: int
    lqi: int
    time: int


def parse_received(line: str) -> Optional[Captured]:
    match = RECEIVED.search(line)
    if not match:
        return None
    digits = match.group(1)
    if len(digits) % 2:
        return None
    return Captured(bytes.fromhex(digits), int(match.group(2)), int(match.group(3)),
                    int(match.group(4)))


def command_line(command: str) -> bytes:
    return (command + "\r\n").encode("ascii")


def pcap_global_header() -> bytes:
    return struct.pack("<IHHiIII", PCAP_MAGIC, PCAP_VERSION[0], PCAP_VERSION[1], 0, 0,
                       PCAP_SNAPLEN, LINKTYPE_IEEE802_15_4_TAP)


def tap_header(channel: int, power: int, lqi: int) -> bytes:
    return (struct.pack("<HH", 0, TAP_HEADER_LENGTH)
            + struct.pack("<HHf", 1, 4, float(power))
            + struct.pack("<HHHH", 3, 3, channel, 0)
            + struct.pack("<HHI", 10, 1, lqi))


def pcap_record(captured: Captured, channel: int, timestamp: float) -> bytes:
    """One pcap record: the TAP header and the frame, stamped with ``timestamp``
    seconds since the epoch."""
    data = tap_header(channel, captured.power, captured.lqi) + captured.frame
    seconds = int(timestamp)
    micros = int(round((timestamp - seconds) * 1000000))
    if micros >= 1000000:
        seconds += 1
        micros -= 1000000
    return struct.pack("<IIII", seconds, micros, len(data), len(data)) + data


def open_sniffer(path: str, baud: int = BAUD):
    """The sniffer's serial port, with short reads so the pump can stop."""
    import serial
    port = serial.Serial(path, baud, timeout=SERIAL_POLL)
    port.reset_input_buffer()
    return port


class Pump(threading.Thread):
    """Drives the sniffer and writes every frame it reports to ``sink`` as pcap.

    ``port`` has ``write`` and ``readline``; ``sink`` has ``write`` and
    ``flush``. ``start`` sends ``channel N`` and ``receive``; ``stop`` ends the
    loop and sends ``sleep`` so the dongle stops transmitting lines after the
    script exits. A failure on the port is kept in ``error`` for the main
    thread.
    """

    def __init__(self, port, sink, channel: int, clock: Callable[[], float] = time.time,
                 debug: Callable[[str], None] = lambda text: None):
        threading.Thread.__init__(self, daemon=True)
        self.port = port
        self.sink = sink
        self.channel = channel
        self.clock = clock
        self.debug = debug
        self.frames = 0
        self.error: Optional[Exception] = None
        self._stopping = threading.Event()

    def start(self) -> None:
        self.port.write(command_line("channel %d" % self.channel))
        self.port.write(command_line("receive"))
        threading.Thread.start(self)

    def run(self) -> None:
        try:
            while not self._stopping.is_set():
                raw = self.port.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", "replace").strip()
                captured = parse_received(line)
                if captured is None:
                    if line:
                        self.debug("sniffer: " + line)
                    continue
                self.sink.write(pcap_record(captured, self.channel, self.clock()))
                self.sink.flush()
                self.frames += 1
        except Exception as error:  # the main thread reports it as a RunError
            self.error = error

    def stop(self) -> None:
        self._stopping.set()
        if self.is_alive():
            self.join(SERIAL_POLL * 5)
        try:
            self.port.write(command_line("sleep"))
        except Exception:
            pass


def open_fifo_for_tshark(path: str, reader: tshark.FieldReader, deadline: Deadline):
    """Open the FIFO's write end once tshark holds the read end. A blocking
    open would hang forever if tshark failed to start, so the open is retried
    without blocking until tshark exits or the deadline passes."""
    while True:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
            break
        except OSError:
            pass
        if reader.exited():
            raise RunError(reader.error())
        if deadline.expired():
            raise RunError("tshark did not open the capture FIFO before the deadline")
        time.sleep(FIFO_OPEN_POLL)
    import fcntl
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
    return os.fdopen(fd, "wb", buffering=0)


class Frame(NamedTuple):
    """The fields of one captured frame the checks look at."""

    time: Optional[float]
    channel: Optional[int]
    pan: Optional[int]
    short: Optional[int]
    mac: Optional[str]
    nwk_type: Optional[int]
    command: Optional[int]
    nwk_src: Optional[int]
    nwk_dst: Optional[int]

    def from_coordinator(self) -> bool:
        return self.short == COORDINATOR_SHORT

    def is_link_status(self) -> bool:
        if self.command is not None:
            return self.command == LINK_STATUS
        return (self.nwk_type == NWK_COMMAND and self.nwk_dst == ROUTERS_BROADCAST
                and self.nwk_src in (None, COORDINATOR_SHORT))


def parse_frame(record: tshark.Record) -> Frame:
    time_text = record.first("frame.time_epoch")
    pan = tshark.hex_int(record.first("wpan.src_pan"))
    if pan is None:
        pan = tshark.hex_int(record.first("wpan.dst_pan"))
    mac = None
    for field in ("wpan.src64", "zbee_nwk.src64", "zbee.sec.src64"):
        mac = tshark.mac_text(record.get(field))
        if mac is not None:
            break
    return Frame(
        float(time_text) if time_text else None,
        tshark.dec_int(record.get("wpan-tap.ch_num")),
        pan,
        tshark.hex_int(record.first("wpan.src16")),
        mac,
        tshark.hex_int(record.first("zbee_nwk.frame_type")),
        tshark.hex_int(record.first("zbee_nwk.cmd.id")),
        tshark.hex_int(record.first("zbee_nwk.src")),
        tshark.hex_int(record.first("zbee_nwk.dst")),
    )


def interval_fits(interval: int, remaining: float) -> Optional[str]:
    """None when two Link Status frames fit in ``remaining`` seconds, else the
    reason for the unverified row."""
    need = 2 * interval + LINK_STATUS_MARGIN
    if need <= remaining:
        return None
    return "two Link Status frames need up to %.0f s, %.0f s left" % (need, remaining)


class Observation(NamedTuple):
    """Frames from a coordinator heard during the capture."""

    frames: List[Frame]
    link_status: List[Frame]

    def heard(self) -> bool:
        return bool(self.frames)

    def first(self) -> Optional[Frame]:
        """The frame the identity rows use: a Link Status when one was heard,
        else the first coordinator frame."""
        if self.link_status:
            return self.link_status[0]
        return self.frames[0] if self.frames else None

    def gap(self) -> Optional[float]:
        """Seconds between the first two Link Status frames."""
        if len(self.link_status) < 2:
            return None
        first, second = self.link_status[0], self.link_status[1]
        if first.time is None or second.time is None:
            return None
        return second.time - first.time


def collect(reader: tshark.FieldReader, deadline: Deadline, pan_id: Optional[int],
            want_link_status: int, debug: Callable[[str], None] = lambda text: None) -> Observation:
    """Read coordinator frames until ``want_link_status`` Link Status frames
    from ``pan_id`` (any PAN when None) arrived or the deadline passed."""
    frames: List[Frame] = []
    link_status: List[Frame] = []
    while True:
        remaining = deadline.remaining()
        if remaining <= 0:
            break
        record = reader.read(remaining)
        if record is None:
            if reader.eof:
                raise RunError(reader.error())
            continue
        frame = parse_frame(record)
        if not frame.from_coordinator():
            continue
        debug("frame: pan %s short %s mac %s cmd %s" % (
            format_u16(frame.pan) if frame.pan is not None else "-",
            format_u16(frame.short) if frame.short is not None else "-",
            frame.mac or "-", frame.command))
        frames.append(frame)
        if frame.is_link_status() and (pan_id is None or frame.pan == pan_id):
            link_status.append(frame)
            if len(link_status) >= want_link_status:
                break
    return Observation(frames, link_status)


def observe(sniffer_path: str, channel: int, deadline: Deadline, tshark_path: str,
            pan_id: Optional[int] = None, want_link_status: int = 2,
            open_port: Callable = open_sniffer, popen: Callable = subprocess.Popen,
            debug: Callable[[str], None] = lambda text: None) -> Observation:
    """Capture on ``channel`` with the sniffer at ``sniffer_path`` until the
    wanted Link Status frames arrived or the deadline passed. tshark reads the
    pcap stream from a FIFO in a temporary directory; the dongle is put to
    sleep and the directory removed on every exit path."""
    workdir = tempfile.mkdtemp(prefix="foxverify-")
    fifo = os.path.join(workdir, "sniffer.pcap")
    os.mkfifo(fifo, stat.S_IRUSR | stat.S_IWUSR)
    argv = tshark.file_command(tshark_path, fifo, FIELDS)
    debug("running: " + " ".join(argv))
    reader = tshark.FieldReader(argv, FIELDS, popen).start()
    sink = None
    pump = None
    try:
        sink = open_fifo_for_tshark(fifo, reader, deadline)
        sink.write(pcap_global_header())
        sink.flush()
        try:
            port = open_port(sniffer_path)
            pump = Pump(port, sink, channel, debug=debug)
            pump.start()
        except OSError as error:
            raise RunError("sniffer %s: %s" % (sniffer_path, error))
        observation = collect(reader, deadline, pan_id, want_link_status, debug)
        if pump.error is not None:
            raise RunError("sniffer %s: %s" % (sniffer_path, pump.error))
        debug("sniffer reported %d frames" % pump.frames)
        return observation
    finally:
        if pump is not None:
            pump.stop()
            try:
                pump.port.close()
            except Exception:
                pass
        if sink is not None:
            try:
                sink.close()
            except OSError:
                pass
        reader.stop()
        try:
            os.unlink(fifo)
            os.rmdir(workdir)
        except OSError:
            pass


def _u16(value: Optional[int]) -> Optional[str]:
    return None if value is None else format_u16(value)


def rows(report: Report, block: Block, readback: Readback, observation: Optional[Observation],
         interval_reason: Optional[str] = None, reason: str = "") -> None:
    """The on-air rows of the Zigbee fox: MAC_ADDR, CHANNEL, PAN_ID, the short
    address and PACKET_INTERVAL. ``observation`` None means nothing was
    captured and ``reason`` says why; ``interval_reason`` is the budget
    decision from ``interval_fits``. EXT_PAN_ID, the timers and TXPOWER are
    the caller's serial-only rows."""
    frame = observation.first() if observation else None
    if frame is None and not reason:
        reason = "no frame from a coordinator heard"

    report.check("MAC_ADDR", block.mac("MAC_ADDR"), readback.upper("mac"),
                 frame.mac if frame else None, reason=reason)

    channel = block.integer("CHANNEL")
    channel_header = "random" if channel == 0 else channel
    serial_channel = readback.integer("channel")
    report.check("CHANNEL", channel_header, serial_channel, frame.channel if frame else None,
                 agree=(serial_channel is not None and channel == 0) or None, reason=reason)

    pan_random = block.is_bare_zero("PAN_ID")
    pan_header = "random" if pan_random else format_u16(block.integer("PAN_ID"))
    serial_pan = _u16(readback.integer("pan_id"))
    report.check("PAN_ID", pan_header, serial_pan, _u16(frame.pan) if frame else None,
                 agree=(serial_pan is not None and pan_random) or None, reason=reason)

    report.check("SHORT_ADDR", format_u16(COORDINATOR_SHORT), _u16(readback.integer("short_address")),
                 _u16(frame.short) if frame else None, reason=reason)

    interval = block.integer("PACKET_INTERVAL")
    serial_interval = readback.integer("packet_interval")
    if serial_interval != interval:
        report.add("PACKET_INTERVAL", interval, serial_interval, None, FAIL,
                   NOT_PRINTED if serial_interval is None else "")
        return
    if interval_reason:
        report.add("PACKET_INTERVAL", interval, serial_interval, None, UNVERIFIED, interval_reason)
        return
    gap = observation.gap() if observation else None
    if gap is None:
        heard = len(observation.link_status) if observation else 0
        report.add("PACKET_INTERVAL", interval, serial_interval, None, UNVERIFIED,
                   reason or "%d Link Status frame%s heard, two needed" % (heard, "" if heard == 1 else "s"))
        return
    verdict = PASS if abs(gap - interval) <= INTERVAL_TOLERANCE else FAIL
    report.add("PACKET_INTERVAL", interval, serial_interval, "%.1f s between Link Status frames" % gap,
               verdict)
