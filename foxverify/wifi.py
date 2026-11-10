"""Monitor mode and the on-air checks of the Wi-Fi fox.

The sniffer is a Wi-Fi interface the user names on the command line. Its type
and up/down state are saved before it is switched to monitor mode and put back
in ``finally`` and on SIGINT or SIGTERM, so an interrupted run never leaves the
laptop's card in monitor mode. ``ip`` and ``iw`` do the switching; both need
root or CAP_NET_ADMIN, which ``privileges`` checks before anything changes.

AP fox: one beacon from the fox's BSSID, caught with tshark on the fox's
channel. The card is tuned and tshark started the moment the serial port
names the channel (``ApCapture``): on the fox's ``Starting on channel`` line,
printed before its radio starts, when the host caught it, so the sniffer is on
the channel for the first beacon; otherwise after the readback, from the
header's ``CHANNEL`` or the ``Operating channel`` the fox printed when the
header says 0 (random). A capture started before the banner is filtered to
every MAC_ADDR of the header, since the block is not known yet; the beacons
are then read once the readback is in, with the timestamps tshark gave them.
A beacon gives the BSSID, the SSID (zero length when ``SSID_HIDDEN`` is 1, in
which case the name is only checked on serial), the channel both as the DS
Parameter Set or HT Operation element claims it and as the radiotap frequency
the frame was received on, and the RSN element, which must say WPA2-PSK with
CCMP because the fox always has a ``PSK``.

Client fox: probe requests from the fox's MAC carrying ``FSSID``. The station
sends one on every 2.4 GHz channel each time it scans for the network, which
takes about a second, so the card dwells on each channel at least that long:
the header's ``CHANNEL`` when it has one, otherwise channels 1-11 in turn.

Both captures feed every frame from the fox, with its ``radiotap.dbm_antsignal``
RSSI, into the run's ``cycle.Cycle`` and go on through the fox's sleeps when
the cycle is being measured, retuning a random-channel AP fox's card to the
channel each later wake prints on serial.

tshark prints ``wlan.ssid`` as text on most builds and as hex bytes on some, so
an SSID cell is compared both ways. MACs are compared upper case.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import contextmanager
from typing import Callable, Iterator, List, NamedTuple, Optional, Sequence

from . import tshark
from .conf import Block
from .cycle import Cycle, Heard, listen
from .report import Deadline, FAIL, PASS, Report, RunError, UNVERIFIED
from .serial_fox import Readback

NET_DIR = "/sys/class/net"
IFF_UP = 0x1

BEACON = 0x0008
PROBE_REQUEST = 0x0004
AKM_PSK = 2
CIPHER_CCMP = 4
WPA2_PSK_CCMP = "WPA2-PSK/CCMP"
# Channels a 2.4 GHz client fox is listened for when the header has none.
CLIENT_CHANNELS = tuple(range(1, 12))
# Rough seconds an ESP32 client takes to probe every 2.4 GHz channel once while
# it scans for its network. An estimate, to tell the user what to expect, not a
# measured value.
PROBE_SWEEP_SECONDS = 1.0
# Seconds the card stays on one channel while listening for a client's probes.
# 200 ms is what Kismet and other scanners hop at, so the card covers the band
# the way a hunter's would rather than dwelling on one channel.
PROBE_DWELL = 0.2
# Seconds between checks of the tshark output while hopping.
HOP_POLL = 0.2

AP_FIELDS = ("frame.time_epoch", "wlan.fc.type_subtype", "wlan.bssid", "wlan.sa", "wlan.ssid",
             "wlan.ds.current_channel", "wlan.ht.info.primarychannel", "radiotap.channel.freq",
             "wlan.rsn.akms.type", "wlan.rsn.pcs.type", "radiotap.dbm_antsignal")
CLIENT_FIELDS = ("frame.time_epoch", "wlan.fc.type_subtype", "wlan.sa", "wlan.ssid",
                 "radiotap.channel.freq", "radiotap.dbm_antsignal")


def default_run(argv: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, check=False)


def run_command(argv: Sequence[str], run: Callable = default_run) -> str:
    """stdout of a command that must succeed; a failure is a ``RunError`` that
    names the command and repeats its stderr."""
    try:
        result = run(list(argv))
    except OSError as error:
        raise RunError("%s: %s" % (argv[0], error))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RunError("%s failed (status %d)%s" % (" ".join(argv), result.returncode,
                                                    ": " + detail if detail else ""))
    return result.stdout or ""


class InterfaceState(NamedTuple):
    name: str
    type: str
    up: bool


def interface_type(name: str, run: Callable = default_run) -> str:
    """The ``type`` line of ``iw dev <name> info``: managed, monitor, AP, ..."""
    for line in run_command(["iw", "dev", name, "info"], run).splitlines():
        words = line.strip().split()
        if len(words) >= 2 and words[0] == "type":
            return words[1]
    raise RunError("iw dev %s info did not report the interface type" % name)


def interface_up(name: str, net_dir: str = NET_DIR) -> bool:
    try:
        with open(os.path.join(net_dir, name, "flags"), "r", encoding="ascii") as handle:
            return bool(int(handle.read().strip(), 16) & IFF_UP)
    except (OSError, ValueError):
        raise RunError("%s is not a network interface" % name)


def save_state(name: str, run: Callable = default_run, net_dir: str = NET_DIR) -> InterfaceState:
    return InterfaceState(name, interface_type(name, run), interface_up(name, net_dir))


def set_type(name: str, kind: str, up: bool, run: Callable = default_run) -> None:
    """Switch the interface type, which ``iw`` only allows while it is down,
    then bring it up when asked."""
    run_command(["ip", "link", "set", name, "down"], run)
    run_command(["iw", "dev", name, "set", "type", kind], run)
    if up:
        run_command(["ip", "link", "set", name, "up"], run)


def set_monitor(name: str, run: Callable = default_run) -> None:
    set_type(name, "monitor", True, run)


def restore_state(state: InterfaceState, run: Callable = default_run) -> None:
    set_type(state.name, state.type, state.up, run)


def set_channel(name: str, channel: int, run: Callable = default_run) -> None:
    run_command(["iw", "dev", name, "set", "channel", str(channel)], run)


class Terminated(KeyboardInterrupt):
    """SIGTERM or SIGHUP arrived; raised so that ``finally`` blocks run."""

    def __init__(self, signum: int):
        KeyboardInterrupt.__init__(self, "signal %d" % signum)
        self.signum = signum


def _raise_terminated(signum, frame) -> None:
    raise Terminated(signum)


@contextmanager
def monitor_mode(name: str, run: Callable = default_run, net_dir: str = NET_DIR,
                 handle_signals: bool = True) -> Iterator[InterfaceState]:
    """Put the interface into monitor mode for the block and restore its saved
    type and state afterwards, whatever ended the block. SIGTERM and SIGHUP
    are turned into exceptions for the duration so the restore runs for them
    too; SIGINT already raises ``KeyboardInterrupt``."""
    state = save_state(name, run, net_dir)
    previous = {}
    if handle_signals:
        for signum in (signal.SIGTERM, signal.SIGHUP):
            try:
                previous[signum] = signal.signal(signum, _raise_terminated)
            except ValueError:
                # Not the main thread; the caller restores on its own path.
                pass
    try:
        set_monitor(name, run)
        yield state
    finally:
        try:
            restore_state(state, run)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def norm_mac(text: Optional[str]) -> Optional[str]:
    return tshark.mac_text(text)


def frequency_to_channel(mhz: Optional[int]) -> Optional[int]:
    """The 802.11 channel number of a centre frequency in MHz."""
    if mhz is None:
        return None
    if mhz == 2484:
        return 14
    if 2412 <= mhz <= 2472 and (mhz - 2407) % 5 == 0:
        return (mhz - 2407) // 5
    if 5160 <= mhz <= 5885 and (mhz - 5000) % 5 == 0:
        return (mhz - 5000) // 5
    return None


def _hex_bytes(text: str) -> Optional[bytes]:
    if len(text) % 2 or not text:
        return None
    try:
        return bytes.fromhex(text)
    except ValueError:
        return None


def ssid_matches(cell: Optional[str], ssid: str) -> bool:
    """True when the ``wlan.ssid`` cell is ``ssid`` as text or as its UTF-8
    bytes in hex."""
    if cell is None:
        return ssid == ""
    if cell == ssid:
        return True
    raw = _hex_bytes(cell)
    return raw is not None and raw == ssid.encode("utf-8")


def ssid_hidden(cell: Optional[str]) -> bool:
    """A hidden network beacons a zero length SSID; some stacks send NUL bytes
    of the real length instead, which counts as hidden too."""
    if cell is None or cell == "":
        return True
    raw = _hex_bytes(cell)
    if raw is not None and raw.strip(b"\0") == b"":
        return True
    return cell.strip("\0") == ""


def ssid_display(cell: Optional[str], expected: str) -> str:
    """The SSID cell for the air column: the expected text when the cell is
    that text in either form, else the cell as tshark printed it."""
    if ssid_hidden(cell):
        return "(hidden)"
    if ssid_matches(cell, expected):
        return expected
    return cell or ""


class Beacon(NamedTuple):
    """What one beacon from the fox says."""

    time: Optional[float]
    bssid: Optional[str]
    ssid: Optional[str]
    ds_channel: Optional[int]
    ht_channel: Optional[int]
    frequency: Optional[int]
    akms: List[int]
    ciphers: List[int]
    rssi: Optional[int]

    def heard(self) -> Optional[Heard]:
        """The frame as the cycle records it, None without a timestamp."""
        return None if self.time is None else Heard(self.time, self.rssi)

    def claimed_channel(self) -> Optional[int]:
        """The channel the AP says it is on: the DS Parameter Set, or the HT
        Operation primary channel when the beacon has no DS element."""
        return self.ds_channel if self.ds_channel is not None else self.ht_channel

    def radio_channel(self) -> Optional[int]:
        return frequency_to_channel(self.frequency)

    def channel_text(self) -> Optional[str]:
        """One number when the claimed and the received channel agree, both
        when they do not, None when the beacon gave neither."""
        claimed, radio = self.claimed_channel(), self.radio_channel()
        if claimed is None and radio is None:
            return None
        if claimed is None or radio is None or claimed == radio:
            return str(claimed if claimed is not None else radio)
        return "%d in beacon, received on %d" % (claimed, radio)

    def hidden(self) -> bool:
        return ssid_hidden(self.ssid)

    def security(self) -> str:
        """``WPA2-PSK/CCMP`` when the RSN element says so, else what it says."""
        if AKM_PSK in self.akms and CIPHER_CCMP in self.ciphers:
            return WPA2_PSK_CCMP
        if not self.akms and not self.ciphers:
            return "open (no RSN element)"
        return "RSN akm %s cipher %s" % (",".join(str(a) for a in self.akms) or "-",
                                         ",".join(str(c) for c in self.ciphers) or "-")


def _ints(record: tshark.Record, field: str) -> List[int]:
    values = []
    for text in record.values(field):
        number = tshark.hex_int(text)
        if number is not None:
            values.append(number)
    return values


def parse_beacon(record: tshark.Record) -> Beacon:
    time_text = record.first("frame.time_epoch")
    return Beacon(
        float(time_text) if time_text else None,
        norm_mac(record.get("wlan.bssid")),
        record.get("wlan.ssid"),
        tshark.dec_int(record.get("wlan.ds.current_channel")),
        tshark.dec_int(record.get("wlan.ht.info.primarychannel")),
        tshark.dec_int(record.get("radiotap.channel.freq")),
        _ints(record, "wlan.rsn.akms.type"),
        _ints(record, "wlan.rsn.pcs.type"),
        rssi(record),
    )


def rssi(record: tshark.Record) -> Optional[int]:
    """The frame's ``radiotap.dbm_antsignal``: the first antenna's value when
    the card reports several."""
    return tshark.dec_int(record.first("radiotap.dbm_antsignal"))


def is_beacon_from(record: tshark.Record, bssid: str) -> bool:
    return (tshark.hex_int(record.first("wlan.fc.type_subtype")) == BEACON
            and norm_mac(record.get("wlan.bssid")) == norm_mac(bssid))


def beacon_filter(*bssids: str) -> str:
    """The tshark display filter for beacons from any of ``bssids``."""
    clauses = ["wlan.bssid == %s" % bssid.lower() for bssid in bssids]
    source = clauses[0] if len(clauses) == 1 else "(%s)" % " || ".join(clauses)
    return "wlan.fc.type_subtype == 0x0008 && " + source


def probe_filter(mac: str) -> str:
    return "wlan.fc.type_subtype == 0x0004 && wlan.sa == %s" % mac.lower()


def ap_channel(block: Block, readback: Readback) -> Optional[int]:
    """The channel to listen on for an AP fox: the header's, or the one the fox
    printed when the header says 0 (random)."""
    channel = block.integer("CHANNEL") if "CHANNEL" in block else 0
    if channel:
        return channel
    return readback.integer("channel")


def probe_channels(block: Block) -> List[int]:
    """The channels to listen on for a client fox."""
    if "CHANNEL" in block and block.integer("CHANNEL"):
        return [block.integer("CHANNEL")]
    return list(CLIENT_CHANNELS)


def wait_for_beacon(reader: tshark.FieldReader, bssid: str, deadline: Deadline,
                    debug: Callable[[str], None] = lambda text: None, cycle: Optional[Cycle] = None,
                    follower=None, retune: Optional[Callable[[int], None]] = None) -> Optional[Beacon]:
    """The first beacon from ``bssid`` before the deadline, or None. Every
    beacon from it is fed to ``cycle``, and with a cycle being measured the
    read goes on through the fox's sleeps until the wake the cycle's tier
    wants is heard; ``retune`` moves the card when ``follower`` reads a later
    wake's channel."""
    first: List[Beacon] = []

    def read(timeout: float) -> List[Heard]:
        record = reader.read(timeout)
        if record is None:
            if reader.eof:
                raise RunError(reader.error())
            return []
        debug("tshark: " + "\t".join(record.as_dict().values()))
        if not is_beacon_from(record, bssid):
            return []
        beacon = parse_beacon(record)
        if not first:
            first.append(beacon)
        heard = beacon.heard()
        return [heard] if heard is not None else []

    listen(cycle, deadline, read, lambda: bool(first), follower, retune, debug)
    return first[0] if first else None


class ApCapture:
    """A running capture of beacons on one channel of a monitor mode
    interface, started the moment the fox names its channel and read later.

    Opening it tunes ``interface`` to ``channel`` and starts tshark filtered
    to beacons from any of ``bssids``, every MAC_ADDR of the header when the
    banner has not yet chosen the block; tshark keeps what it hears until
    ``wait`` reads it, with the frames' own timestamps, so a beacon sent
    while the readback was still being read is not lost. ``retune`` moves
    the card for a later wake of a random-channel fox and ``close`` stops
    tshark. The interface is already in monitor mode (``monitor_mode``).
    """

    def __init__(self, interface: str, bssids: Sequence[str], channel: int, tshark_path: str,
                 run: Callable = default_run, popen: Callable = subprocess.Popen,
                 debug: Callable[[str], None] = lambda text: None):
        self.interface = interface
        self.channel = channel
        self.run = run
        self.debug = debug
        set_channel(interface, channel, run)
        argv = tshark.live_command(tshark_path, interface, AP_FIELDS, beacon_filter(*bssids))
        debug("running: " + " ".join(argv))
        self.reader = tshark.FieldReader(argv, AP_FIELDS, popen).start()

    def retune(self, channel: int) -> None:
        set_channel(self.interface, channel, self.run)

    def wait(self, bssid: str, deadline: Deadline, cycle: Optional[Cycle] = None, follower=None,
             random_channel: bool = False) -> Optional[Beacon]:
        """The first beacon from ``bssid`` before the deadline, or None,
        feeding ``cycle`` as ``wait_for_beacon`` says. With ``random_channel``
        the card follows each later wake's channel from the serial port."""
        return wait_for_beacon(self.reader, bssid, deadline, self.debug, cycle, follower,
                               self.retune if random_channel else None)

    def close(self) -> None:
        self.reader.stop()


def observe_ap(interface: str, bssid: str, channel: int, deadline: Deadline, tshark_path: str,
               run: Callable = default_run, popen: Callable = subprocess.Popen,
               debug: Callable[[str], None] = lambda text: None, cycle: Optional[Cycle] = None,
               follower=None, random_channel: bool = False) -> Optional[Beacon]:
    """Tune the monitor interface to ``channel`` and return the first beacon
    from ``bssid`` before the deadline, or None, feeding ``cycle`` as
    ``wait_for_beacon`` says. With ``random_channel`` the card follows each
    later wake's channel from the serial port. The interface is already in
    monitor mode (``monitor_mode``)."""
    capture = ApCapture(interface, [bssid], channel, tshark_path, run, popen, debug)
    try:
        return capture.wait(bssid, deadline, cycle, follower, random_channel)
    finally:
        capture.close()


class Probes(NamedTuple):
    """Probe requests seen from the client fox."""

    mac: Optional[str]
    count: int
    ssids: List[Optional[str]]
    channels: List[int]
    first_time: Optional[float]

    def seen(self) -> bool:
        return self.count > 0

    def carried(self, ssid: str) -> bool:
        return any(ssid_matches(cell, ssid) for cell in self.ssids)

    def other_ssids(self, ssid: str) -> List[str]:
        """SSIDs the fox probed for that are neither ``ssid`` nor the wildcard."""
        seen: List[str] = []
        for cell in self.ssids:
            if cell is None or cell == "" or ssid_matches(cell, ssid):
                continue
            if cell not in seen:
                seen.append(cell)
        return seen


def collect_probes(reader: tshark.FieldReader, mac: str, ssid: str, deadline: Deadline,
                   channels: Sequence[int], tune: Callable[[int], None],
                   dwell: float = PROBE_DWELL, clock: Callable[[], float] = time.monotonic,
                   debug: Callable[[str], None] = lambda text: None, cycle: Optional[Cycle] = None,
                   follower=None) -> Probes:
    """Read probe requests from ``mac`` until one carries ``ssid`` or the
    deadline passes, moving the card through ``channels`` every ``dwell``
    seconds. A single channel is never changed. Every probe from the fox is
    fed to ``cycle``; with a cycle being measured the read goes on through
    the sleep, still hopping, since the station probes on every channel."""
    want = norm_mac(mac)
    state = {"mac": None, "count": 0, "first_time": None, "carried": False, "index": 0,
             "next_hop": clock() + dwell}
    ssids: List[Optional[str]] = []
    seen_channels: List[int] = []
    tune(channels[0])

    def read(timeout: float) -> List[Heard]:
        if len(channels) > 1:
            timeout = min(timeout, max(0.0, state["next_hop"] - clock()), HOP_POLL)
        record = reader.read(timeout)
        now = clock()
        if len(channels) > 1 and now >= state["next_hop"]:
            state["index"] = (state["index"] + 1) % len(channels)
            tune(channels[state["index"]])
            state["next_hop"] = now + dwell
        if record is None:
            if reader.eof:
                raise RunError(reader.error())
            return []
        if tshark.hex_int(record.first("wlan.fc.type_subtype")) != PROBE_REQUEST:
            return []
        source = norm_mac(record.get("wlan.sa"))
        if source != want:
            return []
        state["mac"] = source
        state["count"] += 1
        cell = record.get("wlan.ssid")
        debug("probe request from %s for %r" % (want, cell))
        ssids.append(cell)
        channel = frequency_to_channel(tshark.dec_int(record.get("radiotap.channel.freq")))
        if channel is not None and channel not in seen_channels:
            seen_channels.append(channel)
        time_text = record.first("frame.time_epoch")
        if not time_text:
            return []
        when = float(time_text)
        if state["first_time"] is None:
            state["first_time"] = when
        if ssid_matches(cell, ssid):
            state["carried"] = True
        return [Heard(when, rssi(record))]

    listen(cycle, deadline, read, lambda: state["carried"], follower, debug=debug)
    return Probes(state["mac"], state["count"], ssids, seen_channels, state["first_time"])


def observe_client(interface: str, mac: str, ssid: str, channels: Sequence[int], deadline: Deadline,
                   tshark_path: str, run: Callable = default_run, popen: Callable = subprocess.Popen,
                   dwell: float = PROBE_DWELL,
                   debug: Callable[[str], None] = lambda text: None, cycle: Optional[Cycle] = None,
                   follower=None) -> Probes:
    """Listen for the client fox's probe requests on ``channels`` until one
    carries ``ssid`` or the deadline passes, feeding ``cycle`` as
    ``collect_probes`` says. The interface is already in monitor mode."""
    argv = tshark.live_command(tshark_path, interface, CLIENT_FIELDS, probe_filter(mac))
    debug("running: " + " ".join(argv))

    def tune(channel: int) -> None:
        debug("listening on channel %d" % channel)
        set_channel(interface, channel, run)

    with tshark.FieldReader(argv, CLIENT_FIELDS, popen) as reader:
        return collect_probes(reader, mac, ssid, deadline, list(channels), tune, dwell, debug=debug,
                              cycle=cycle, follower=follower)


def _channel_header(block: Block) -> Optional[object]:
    """The CHANNEL header value for the row: ``random`` for 0."""
    if "CHANNEL" not in block:
        return None
    channel = block.integer("CHANNEL")
    return "random" if channel == 0 else channel


def ap_rows(report: Report, block: Block, readback: Readback, beacon: Optional[Beacon],
            reason: str = "") -> None:
    """The on-air rows of an AP fox: MAC_ADDR, CHANNEL, FSSID, SSID_HIDDEN and
    the security the beacon advertises. ``beacon`` None means nothing was heard
    and ``reason`` says why; the serial-only values (PSK text, MAX_CLIENTS,
    the timers, TXPOWER) are the caller's rows."""
    header_mac = block.mac("MAC_ADDR")
    serial_mac = readback.upper("address")
    report.check("MAC_ADDR", header_mac, serial_mac, beacon.bssid if beacon else None,
                 reason=reason)

    channel_header = _channel_header(block)
    serial_channel = readback.integer("channel")
    air_channel = beacon.channel_text() if beacon else None
    mismatch = readback.channel_mismatch()
    if mismatch is not None:
        # The fox named one channel before its radio started and read back
        # another; both are shown.
        report.add("CHANNEL", channel_header, mismatch, air_channel, FAIL)
    else:
        report.check("CHANNEL", channel_header, serial_channel, air_channel,
                     agree=(serial_channel is not None and channel_header == "random") or None,
                     reason=reason)

    ssid = block.string("FSSID")
    hidden = bool(block.integer("SSID_HIDDEN")) if "SSID_HIDDEN" in block else False
    serial_ssid = readback.get("ssid")
    if hidden:
        report.check("FSSID", ssid, serial_ssid, on_air=False,
                     reason="hidden network, name not in beacons")
    else:
        report.check("FSSID", ssid, serial_ssid,
                     ssid_display(beacon.ssid, ssid) if beacon else None, reason=reason)

    if "SSID_HIDDEN" in block:
        air_hidden = None if beacon is None else int(beacon.hidden())
        report.check("SSID_HIDDEN", int(hidden), readback.integer("ssid_hidden"), air_hidden,
                     reason=reason)

    if "PSK" in block:
        report.check("SECURITY", WPA2_PSK_CCMP, None, beacon.security() if beacon else None,
                     agree=True, reason=reason)


def client_rows(report: Report, block: Block, readback: Readback, probes: Optional[Probes],
                reason: str = "") -> None:
    """The on-air rows of a client fox: MAC_ADDR from the probe requests'
    source and FSSID from the SSID they carry."""
    header_mac = block.mac("MAC_ADDR")
    serial_mac = readback.upper("address")
    ssid = block.string("FSSID")
    serial_ssid = readback.get("ssid")
    if probes is None or not probes.seen():
        report.check("MAC_ADDR", header_mac, serial_mac, None,
                     reason=reason or "no probe request from the fox")
        report.check("FSSID", ssid, serial_ssid, None,
                     reason=reason or "no probe request from the fox")
        return
    report.check("MAC_ADDR", header_mac, serial_mac, probes.mac)
    if serial_ssid != ssid:
        report.add("FSSID", ssid, serial_ssid, None, FAIL)
        return
    if probes.carried(ssid):
        report.add("FSSID", ssid, serial_ssid, ssid, PASS)
        return
    others = probes.other_ssids(ssid)
    if others:
        report.add("FSSID", ssid, serial_ssid, ", ".join(others), FAIL,
                   "the fox probed for another network")
    else:
        report.add("FSSID", ssid, serial_ssid, None, UNVERIFIED,
                   "%d probe requests from the fox, none carried the SSID" % probes.count)
