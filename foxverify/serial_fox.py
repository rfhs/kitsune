"""The fox's serial side: reset, banner wait, readback parsing, not-a-fox outcomes.

Every fox prints at 115200 baud. After its radio is up it prints the banner
``Fox: <project> <DIFFICULTY> [<MODE>]`` and then its readback lines, one
value per line, in the formats of the firmware's ``printf`` calls, the
device address first and "Awake and screaming" last. ``LINES`` holds one
regex per line the four projects print; ``Readback.feed`` matches them and
keeps the captured values under the field names in ``LINES``.

Reset. ``SerialSource`` opens and resets the port with the line sequences of
``usbstack``, chosen by the port's USB id: esptool's hard reset for a UART
bridge (the M5 Atom) and for the USB-Serial-JTAG peripheral (M5 AtomS3 and
StampS3, Seeed XIAO ESP32-C5), nothing for the Arduino Nano ESP32, whose
TinyUSB stack has no way to restart the application; ``read_fox`` then says
so and waits for the fox's own wake as with ``reset=False``. Opening a port
never resets a running fox on any stack. After the reset a native USB device
may re-enumerate; ``SerialSource.read`` raises ``PortGone`` and ``read_fox``
reopens the same by-id path. The wall clock moment the reset was released is
kept in ``Readback.reset_time`` for the first transmission figure.

A reset that lands the chip in the ROM's download mode, which the ROM
announces with a ``boot:`` line naming ``DOWNLOAD`` and then ``waiting for
download``, is answered once by another reset; a second download banner ends
the run with the reset-button hint, since the ROM never leaves download mode
on its own.

``Follower`` reads the port after the readback while the sniffer listens
through the fox's first sleep. It watches for ``Going to sleep``, the exact
end of wake 1, and takes the port vanishing, as a native USB board's does in
deep sleep, as the same signal. Every line after that belongs to wake 2 and
is parsed into its own ``Readback``, so a random-channel fox's wake 2
``Operating channel`` line can retune the sniffer; the port is opened again
after it vanished only when those lines are wanted.

Not-a-fox outcomes after the reset, each a ``RunError`` (exit 2) with the text
in the constants below: nothing at all within 10 s, or output without a banner
within 15 s of the first byte. The 10 s mark prints the reset-button hint and
keeps waiting until the deadline, so a fox whose bridge does not wire the
pulse still gets its turn. With ``reset=False`` the script waits for the
fox's own wake cycle until the deadline instead.
"""
from __future__ import annotations

import codecs
import os
import re
import time
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from . import devices, usbstack
from .conf import Block, ConfError, defined_for, select
from .report import Deadline, RunError

BAUD = 115200
NO_OUTPUT_SECONDS = 10.0
NO_BANNER_SECONDS = 15.0
# Seconds without a new line after the banner before the readback counts as
# complete when the awake line was not seen.
QUIET_SECONDS = 2.0
# Seconds the read goes on after the awake line, which ends the readback
# burst, so a line a fox prints on its heels is still taken.
DRAIN_SECONDS = 0.5
# How often a vanished serial device is polled for while it re-enumerates.
REOPEN_POLL_SECONDS = 0.2

NO_OUTPUT = "no output at 115200 after reset; not a fox or wrong device"
NO_BANNER = ("device boots but does not identify as a fox; other firmware, "
             "or a kitsune build older than the banner")
PRESS_RESET = "if this is a fox, press its reset button; waiting until the deadline"
NO_OUTPUT_NO_RESET = ("no output at 115200 before the deadline; not a fox, wrong device, "
                      "or a fox still asleep")
NO_BANNER_NO_RESET = ("device prints but did not identify as a fox before the deadline; "
                      "other firmware, a kitsune build older than the banner, or a wake "
                      "cycle longer than the deadline")
DIFFERENT_HEADER = "fox was built from a different conference header than src/current_conf.h"
PORT_GONE = "the fox's serial device went away and did not come back before the deadline"
NO_SERIAL_RESET = ("the Arduino Nano ESP32 cannot be reset over its serial port; "
                   "waiting for the fox's next wake")
IN_BOOTLOADER = "the reset left the fox in the bootloader; resetting it again"
STILL_IN_BOOTLOADER = "the reset left the fox in the bootloader again; press the board's reset button"

# What the ROM prints after a reset into download mode: its boot-mode line,
# ``rst:0x1 (POWERON),boot:0x0 (DOWNLOAD(USB/UART0))`` on an ESP32-S3 or
# ESP32-C5 and ``boot:0x3 (DOWNLOAD_BOOT(UART0/UART1/SDIO_REI_REO_V2))`` on an
# ESP32, then ``waiting for download``, the line esptool keys on.
DOWNLOAD_BOOT = re.compile(r"^rst:0x[0-9A-Fa-f]+ \([^)]*\),boot:0x[0-9A-Fa-f]+ \(DOWNLOAD")
WAITING_FOR_DOWNLOAD = "waiting for download"

# Project name in the banner -> directory of its verify script.
PROJECT_DIRS = {
    "classic_discoverable": "bluetooth/classic_discoverable",
    "iBeacon": "bluetooth/iBeacon",
    "wifi_ap_client": "wifi/wifi_ap_client",
    "zigbee_coordinator": "zigbee/zigbee_coordinator",
}

# The field whose line ends every fox's readback on the success path: the
# radio header's checks are printed and then "Awake and screaming".
LAST_FIELD = "awake"


def wrong_project(project: str) -> str:
    return "this is a %s fox; run %s/verify" % (project, PROJECT_DIRS.get(project, project))


def missing_block(difficulty: str, mode: Optional[str]) -> str:
    tokens = difficulty + (" " + mode if mode else "")
    return "src/current_conf.h has no %s block; the fox was built with -D %s" % (
        tokens, " -D ".join(tokens.split()))


class Banner(NamedTuple):
    project: str
    difficulty: str
    mode: Optional[str]

    def text(self) -> str:
        return "Fox: %s %s%s" % (self.project, self.difficulty, " " + self.mode if self.mode else "")


BANNER = re.compile(r"^Fox: (\S+) (EASY|MEDIUM|HARD|FIVEEASY|FIVEHARD)(?: (AP|CLIENT))?$")

# Six colon separated bytes for a Bluetooth or Wi-Fi address, eight for the
# Zigbee EUI-64 and the extended PAN ID.
_MAC6_OR_8 = r"((?:[0-9A-Fa-f]{2}:){5}(?:(?:[0-9A-Fa-f]{2}:){2})?[0-9A-Fa-f]{2})"
_MAC8 = r"((?:[0-9A-Fa-f]{2}:){7}[0-9A-Fa-f]{2})"
_U16 = r"(0x[0-9A-Fa-f]{4})"

# (field, regex) for every line a fox prints, in the firmware's own formats.
# A field with several lines (tx_power) is written by whichever appears.
# Group 1 is the value kept; a regex without groups keeps the whole line.
LINES: List[Tuple[str, "re.Pattern[str]"]] = [
    # include/rfhsfox.h and include/rfhssleeptimers.h, the same in every fox.
    # "Last cycle" comes with a timer wake-up and "Cycle behind" when a
    # fox with a non-zero TIME_TO_SLEEP ran past its cycle; both are
    # informational, no row reads them.
    ("initializing", re.compile(r"^Initializing\.\.\.$")),
    ("boot_count", re.compile(r"^ESP32 boot count: (\d+)$")),
    ("sleep_stats", re.compile(r"^Sleep stats: (-?\d+s since cold boot, -?\d+s since last wakeup)$")),
    ("last_cycle", re.compile(r"^Last cycle: (\d+\.\d+s, target \d+s)$")),
    ("setting_up", re.compile(r"^Setting up (.+)\.\.\.$")),
    ("mac_set", re.compile(r"^MAC address set (successfully)$")),
    ("time_to_wake", re.compile(r"^Time to wake: (\d+)s$")),
    ("time_to_sleep", re.compile(r"^Time to sleep: (\d+)s$")),
    ("awake", re.compile(r"^(Awake and screaming)$")),
    ("sleeping", re.compile(r"^(Going to sleep)$")),
    ("cycle_behind", re.compile(r"^Cycle behind by (\d+\.\d+)s, rebooting at once$")),
    # include/rfhsconfcheck.h: the first readback line of every fox.
    ("address", re.compile(r"^Device address: " + _MAC6_OR_8 + "$")),
    # include/rfhswifi.h, include/rfhszigbee.h and include/rfhsibeacon.h;
    # Wi-Fi prints the WIFI_POWER_* name, Zigbee a dBm number, iBeacon the
    # ESP_PWR_LVL_* name with its dBm in parentheses.
    ("tx_power_status", re.compile(r"^Set power status: (ok|failed)$")),
    ("psk", re.compile(r"^Operating PSK: (.*)$")),
    ("ssid_hidden", re.compile(r"^Hidden SSID: ([01])$")),
    ("max_clients", re.compile(r"^Max clients: (\d+)$")),
    ("tx_power", re.compile(r"^Tx power: (\S+?)(?: dBm)?$")),
    ("tx_power", re.compile(r"^Tx power: (ESP_PWR_LVL_\w+) \(-?\d+ dBm\)$")),
    # include/rfhswifi.h and include/rfhszigbee.h
    ("channel", re.compile(r"^Operating channel: (\d+)$")),
    ("pan_id", re.compile(r"^Operating PAN ID: " + _U16 + "$")),
    ("ext_pan_id", re.compile(r"^Extended PAN ID: " + _MAC8 + "$")),
    ("short_address", re.compile(r"^Short address: " + _U16 + "$")),
    ("packet_interval", re.compile(r"^Packet interval: (\d+)s$")),
    ("ssid", re.compile(r"^Operating SSID: (.*)$")),
    # include/rfhsclassicdiscoverable.h and include/rfhsibeacon.h
    ("name", re.compile(r"^Device name: (.*)$")),
    ("uuid", re.compile(r"^Beacon UUID: ([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
                        r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})$")),
    ("major", re.compile(r"^Major: 0x[0-9A-Fa-f]{4} \((\d+)\)$")),
    ("minor", re.compile(r"^Minor: 0x[0-9A-Fa-f]{4} \((\d+)\)$")),
    ("signal_power", re.compile(r"^Signal power: (-?\d+)$")),
]
# The first regex of each field, for code that looks for one line.
LINES_BY_FIELD: Dict[str, "re.Pattern[str]"] = {}
for _field, _pattern in LINES:
    LINES_BY_FIELD.setdefault(_field, _pattern)

# Lines that mean the fox refused to run or is not healthy. The firmware
# prints one of these, then "Fatal <code>: <reason>" and PANIC before it
# halts on the blinking LED.
PROBLEMS = [
    re.compile(r"^.* != .*$"),
    re.compile(r"^Error .*$"),
    re.compile(r"^Device address: unavailable.*$"),
    re.compile(r"^Beacon data is \d+ bytes, not 25$"),
    re.compile(r"^Fatal \d+: "),
    re.compile(r"^PANIC$"),
]

# "Requested <what>: <value>" accompanies a mismatch; kept under requested:<what>.
_REQUESTED = re.compile(r"^Requested ([A-Za-z ]+?)\s*: (.*)$")


class Readback:
    """Everything a fox printed, with the values the regexes picked out."""

    def __init__(self):
        self.lines: List[str] = []
        self.banner: Optional[Banner] = None
        self.fields: Dict[str, str] = {}
        self.problems: List[str] = []
        self.unmatched: List[str] = []
        # Wall clock times of the reset's release, None when the fox was not
        # reset, and of the banner's arrival, which the fox prints once its
        # radio is up.
        self.reset_time: Optional[float] = None
        self.banner_time: Optional[float] = None

    def feed(self, line: str) -> Optional[str]:
        """Record one complete line; return the field it set, if any."""
        line = line.rstrip("\r\n")
        if not line.strip():
            return None
        self.lines.append(line)
        match = BANNER.match(line)
        if match:
            self.banner = Banner(match.group(1), match.group(2), match.group(3))
            return "banner"
        found = None
        for field, pattern in LINES:
            match = pattern.match(line)
            if match:
                self.fields[field] = match.group(1) if pattern.groups else line
                found = found or field
        if found is not None:
            return found
        match = _REQUESTED.match(line)
        if match:
            field = "requested:" + match.group(1).strip().lower()
            self.fields[field] = match.group(2)
            return field
        for pattern in PROBLEMS:
            if pattern.match(line):
                self.problems.append(line)
                return "problem"
        self.unmatched.append(line)
        return None

    def feed_text(self, text: str) -> None:
        for line in text.splitlines():
            self.feed(line)

    def get(self, field: str) -> Optional[str]:
        return self.fields.get(field)

    def integer(self, field: str) -> Optional[int]:
        value = self.fields.get(field)
        if value is None:
            return None
        return int(value, 0)

    def upper(self, field: str) -> Optional[str]:
        value = self.fields.get(field)
        return None if value is None else value.upper()

    def halted(self) -> bool:
        return bool(self.problems)

    def complete(self) -> bool:
        """True once the awake line or a problem was seen after the banner."""
        if self.banner is None:
            return False
        return bool(self.problems) or LAST_FIELD in self.fields

    def transcript(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.lines else "")


def parse_transcript(text: str) -> Readback:
    readback = Readback()
    readback.feed_text(text)
    return readback


class PortGone(Exception):
    """The serial device disappeared, as a native USB board does when it resets."""


class SerialSource:
    """A pyserial port read in chunks, with the hard reset of the port's USB
    stack and reopening.

    ``port`` is the ``devices.Port`` of ``path``, whose USB id picks the line
    sequences; when it is not given the port is looked up among the serial
    ports pyserial lists. A path without a USB id gets the UART bridge
    sequences.
    """

    def __init__(self, path: str, baud: int = BAUD, sleep: Callable[[float], None] = time.sleep,
                 port: Optional[devices.Port] = None):
        self.path = path
        self.baud = baud
        self.sleep = sleep
        if port is None:
            port = devices.find_port(path, devices.list_ports())
        self.port = port
        self.stack = usbstack.usb_stack(port)
        self.serial = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.open()

    def open(self) -> None:
        import serial
        port = serial.Serial()
        port.port = self.path
        port.baudrate = self.baud
        port.timeout = 0
        usbstack.open_port(port, self.stack)
        self.serial = port
        self._decoder.reset()

    def close(self) -> None:
        if self.serial is not None:
            try:
                self.serial.close()
            except (OSError, ValueError):
                pass
            self.serial = None

    def reset(self, wall: Callable[[], float] = time.time) -> Optional[float]:
        """The hard reset of the port's USB stack: the moment the chip left
        reset on ``wall``, or None when the stack has no reset.

        A USB-Serial-JTAG chip that dropped off the bus during the reset
        leaves a port that cannot be used; it is closed so that the next
        ``read`` raises ``PortGone`` and the caller opens the path again.
        """
        try:
            done = usbstack.hard_reset(self.serial, self.stack, self.sleep, wall)
        except OSError:
            self.close()
            return wall()
        if done.dropped:
            self.close()
        return done.released

    def read(self, timeout: float) -> Optional[str]:
        """Text that arrived within ``timeout`` seconds, or None when nothing did."""
        port = self.serial
        if port is None:
            raise PortGone(self.path)
        try:
            port.timeout = max(0.0, timeout)
            data = port.read(1)
            if not data:
                return None
            waiting = port.in_waiting
            if waiting:
                data += port.read(waiting)
        except OSError as error:
            # pyserial's SerialException is an OSError; a disconnected device
            # raises it from read().
            self.close()
            raise PortGone("%s: %s" % (self.path, error))
        return self._decoder.decode(data)

    def try_open(self) -> bool:
        """One attempt to open the device path again; False when it is not
        back yet."""
        import serial
        if not os.path.exists(self.path):
            return False
        try:
            self.open()
        except (serial.SerialException, OSError):
            return False
        return True

    def reopen(self, deadline: Deadline) -> None:
        """Wait for the device path to come back and open it again."""
        self.close()
        while True:
            if self.try_open():
                return
            if deadline.expired():
                raise RunError(PORT_GONE)
            self.sleep(min(REOPEN_POLL_SECONDS, deadline.remaining()))


class TranscriptSource:
    """A recorded transcript played back as a serial source, for the tests and
    for a serial-only run against a saved transcript.

    ``items`` are lines, each optionally preceded by a delay in seconds as
    ``(delay, line)``. With a ``FakeClock`` a line is due its delay after the
    previous line was due, ``read`` moves the clock to the due time of the
    next line when that is within the timeout, and a line whose moment has
    passed is delivered at once, so a poll with a zero timeout catches up
    with lines the clock has moved past. With the real clock ``read`` sleeps
    the delay. After the last line every read times out.
    """

    def __init__(self, items, clock=None, sleep: Callable[[float], None] = time.sleep,
                 path: str = "transcript"):
        self.path = path
        self.items = []
        for item in items:
            if isinstance(item, tuple):
                self.items.append((float(item[0]), item[1]))
            else:
                self.items.append((0.0, item))
        self.clock = clock
        self.sleep = sleep
        self.resets = 0
        self.reopens = 0
        # On a fake clock, the time the next line's delay counts from.
        self._ref: Optional[float] = clock() if hasattr(clock, "advance") else None

    @classmethod
    def from_file(cls, path: str, **kwargs) -> "TranscriptSource":
        with open(path, "r", encoding="utf-8") as handle:
            return cls(handle.read().splitlines(True), path=path, **kwargs)

    def _advance(self, seconds: float) -> None:
        if hasattr(self.clock, "advance"):
            self.clock.advance(seconds)
        elif seconds > 0:
            self.sleep(seconds)

    def reset(self, wall: Callable[[], float] = time.time) -> Optional[float]:
        self.resets += 1
        return wall()

    def reopen(self, deadline: Deadline) -> None:
        self.reopens += 1

    def try_open(self) -> bool:
        self.reopens += 1
        return True

    def close(self) -> None:
        pass

    @staticmethod
    def _line(text: str) -> str:
        return text if text.endswith("\n") else text + "\n"

    def read(self, timeout: float) -> Optional[str]:
        if self._ref is not None:
            return self._read_on_clock(timeout)
        if not self.items:
            self._advance(timeout)
            return None
        delay, line = self.items[0]
        if delay > timeout:
            self.items[0] = (delay - timeout, line)
            self._advance(timeout)
            return None
        self.items.pop(0)
        self._advance(delay)
        return self._line(line)

    def _read_on_clock(self, timeout: float) -> Optional[str]:
        now = self.clock()
        if not self.items:
            self.clock.advance(timeout)
            return None
        delay, line = self.items[0]
        due = self._ref + delay
        if due > now + timeout:
            self.clock.advance(timeout)
            return None
        self.items.pop(0)
        if due > now:
            self.clock.advance(due - now)
        self._ref = due
        return self._line(line)


class FakeClock:
    """A monotonic clock the tests move by hand."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


def read_fox(source, deadline: Deadline, reset: bool = True,
             say: Callable[[str], None] = lambda text: None,
             debug: Callable[[str], None] = lambda text: None,
             wall: Callable[[], float] = time.time) -> Readback:
    """Reset the fox, wait for its banner, read its readback lines.

    Returns the ``Readback`` once a problem line, the awake line plus
    ``DRAIN_SECONDS``, a quiet spell after the banner or the deadline ends it.
    A fox whose radio start failed prints its "Error ..." line before the
    banner; the read goes on to the banner and stops there. Raises
    ``RunError`` with the not-a-fox texts when no banner arrives. ``wall`` is
    the clock the sniffers stamp frames with; the reset is stamped on it.

    A source whose USB stack cannot reset the fox (``reset`` returns None)
    is read as with ``reset=False`` after saying so. A reset that leaves the
    chip in the ROM's download mode is seen in the ROM's lines and answered
    with one more reset; the second time the run ends with the hint to press
    the board's reset button.
    """
    readback = Readback()
    buffer = ""
    clock = deadline.now
    if reset:
        debug("resetting the fox on %s" % source.path)
        readback.reset_time = source.reset(wall)
        if readback.reset_time is None:
            say(NO_SERIAL_RESET)
            reset = False
    started = clock()
    first_output: Optional[float] = None
    last_line: Optional[float] = None
    drain_until: Optional[float] = None
    hinted = False
    reset_again = reset
    while True:
        now = clock()
        if readback.banner is not None:
            if readback.halted():
                break
            if readback.complete():
                if drain_until is None:
                    drain_until = now + DRAIN_SECONDS
                if now >= drain_until:
                    break
                checkpoint = drain_until
            else:
                stop = (last_line or now) + QUIET_SECONDS
                if now >= stop:
                    break
                checkpoint = stop
        elif first_output is None:
            checkpoint = started + NO_OUTPUT_SECONDS if reset and not hinted else deadline.at
        else:
            checkpoint = first_output + NO_BANNER_SECONDS if reset else deadline.at
        checkpoint = min(checkpoint, deadline.at)
        if deadline.expired():
            if readback.banner is not None:
                break
            if first_output is None:
                raise RunError(NO_OUTPUT if reset else NO_OUTPUT_NO_RESET)
            raise RunError(NO_BANNER if reset else NO_BANNER_NO_RESET)
        try:
            chunk = source.read(max(0.0, checkpoint - now))
        except PortGone as gone:
            debug("serial device gone (%s), waiting for it to come back" % gone)
            source.reopen(deadline)
            continue
        now = clock()
        if chunk is None:
            if readback.banner is None and first_output is None and reset and not hinted \
                    and now >= started + NO_OUTPUT_SECONDS:
                say(NO_OUTPUT + "; " + PRESS_RESET)
                hinted = True
            elif readback.banner is None and first_output is not None and reset \
                    and now >= first_output + NO_BANNER_SECONDS:
                raise RunError(NO_BANNER)
            continue
        if first_output is None:
            first_output = now
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if not line.strip():
                continue
            last_line = now
            debug("serial: " + line.rstrip("\r"))
            rom = download_mode_line(line) if reset and readback.banner is None else None
            # The ROM's boot line opens every boot's output, so it is a fresh
            # verdict whenever it comes. Its waiting line alone is taken only
            # before the second reset: after it, that line can still be the
            # first boot's, in flight while the chip was reset again.
            if rom == BOOT_LINE or (rom == WAITING_LINE and reset_again):
                if not reset_again:
                    raise RunError(STILL_IN_BOOTLOADER)
                # The ROM never leaves download mode on its own; the reset
                # is repeated once and the wait starts over.
                say(IN_BOOTLOADER)
                readback.feed(line)
                reset_again = False
                readback.reset_time = source.reset(wall)
                started = clock()
                first_output = None
                buffer = ""
                break
            if readback.feed(line) == "banner":
                readback.banner_time = wall()
                say(readback.banner.text())
    if buffer.strip():
        readback.feed(buffer)
    return readback


BOOT_LINE = "boot"
WAITING_LINE = "waiting"


def download_mode_line(line: str) -> Optional[str]:
    """``BOOT_LINE`` for the ROM's boot-mode line naming download mode,
    ``WAITING_LINE`` for its ``waiting for download``, None for anything else."""
    line = line.rstrip("\r")
    if DOWNLOAD_BOOT.match(line):
        return BOOT_LINE
    if WAITING_FOR_DOWNLOAD in line:
        return WAITING_LINE
    return None


class Follower:
    """Reads the fox's port after the readback, without blocking, while the
    sniffer listens through the first sleep.

    ``poll`` takes whatever arrived. Until the fox has gone to sleep only the
    ``Going to sleep`` line matters and is stamped on ``clock``; the port
    vanishing is stamped the same way. From then on every line is wake 2's
    and goes into ``wake2``. With ``reopen`` the port is tried again on every
    poll after it vanished, which a random-channel fox needs for its wake 2
    channel; without it a vanished port is left alone.
    """

    def __init__(self, source, clock: Callable[[], float] = time.time, reopen: bool = False,
                 debug: Callable[[str], None] = lambda text: None):
        self.source = source
        self.clock = clock
        self.reopen = reopen
        self.debug = debug
        self.wake2 = Readback()
        self.sleep_time: Optional[float] = None
        self.gone_time: Optional[float] = None
        self.gone = False
        self.reopened = False
        self._buffer = ""
        self._asleep = False

    def poll(self) -> None:
        if self.gone:
            if not self.reopen or not self.source.try_open():
                return
            self.gone = False
            self.reopened = True
            self._asleep = True
            self._buffer = ""
            self.debug("serial device is back, reading wake 2")
        try:
            chunk = self.source.read(0.0)
        except PortGone:
            self.gone = True
            if self.gone_time is None:
                self.gone_time = self.clock()
                self._asleep = True
                self.debug("serial device gone, taking it as the end of wake 1")
            return
        if chunk is None:
            return
        self._buffer += chunk
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line.strip():
                self._line(line)

    def _line(self, line: str) -> None:
        self.debug("serial: " + line)
        if self._asleep:
            self.wake2.feed(line)
            return
        if LINES_BY_FIELD["sleeping"].match(line):
            self.sleep_time = self.clock()
            self._asleep = True

    def boundary(self) -> Optional[float]:
        """When wake 1 ended, by the sleep line or the port vanishing."""
        return self.sleep_time if self.sleep_time is not None else self.gone_time

    def channel(self) -> Optional[int]:
        """Wake 2's operating channel once the fox printed it."""
        return self.wake2.integer("channel")

    def pan_id(self) -> Optional[int]:
        return self.wake2.integer("pan_id")


def block_for(readback: Readback, project: str, header_text: str) -> Block:
    """The block of ``current_conf.h`` the banner selects, or a ``RunError``
    naming the other project or the missing block."""
    banner = readback.banner
    if banner is None:
        raise RunError(NO_BANNER)
    if banner.project != project:
        raise RunError(wrong_project(banner.project))
    try:
        block = select(header_text, defined_for(project, banner.difficulty, banner.mode))
    except ConfError as error:
        raise RunError("cannot parse src/current_conf.h: %s" % error)
    if "MAC_ADDR" not in block:
        raise RunError(missing_block(banner.difficulty, banner.mode))
    return block


def same_mac(header_mac: str, serial_mac: Optional[str]) -> bool:
    """Case insensitive comparison of two colon separated addresses."""
    return serial_mac is not None and header_mac.upper() == serial_mac.upper()
