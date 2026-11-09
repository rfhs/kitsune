"""The fox's serial side: reset, banner wait, readback parsing, not-a-fox outcomes.

Every fox prints at 115200 baud. After its radio is up it prints the banner
``Fox: <project> <DIFFICULTY> [<MODE>]`` and then its readback lines, one
value per line, in the formats of the firmware's ``printf`` calls. ``LINES``
holds one regex per line the four projects print; ``Readback.feed`` matches
them and keeps the captured values under the field names in ``LINES``.

Reset. The pulse is esptool's HardReset: DTR low with RTS high for 0.1 s, then
RTS low. On a USB-UART board (CP210x, CH910x) RTS drives EN and DTR drives IO0
through the usual two transistors, so the chip reboots into the application.
On a board with ``ARDUINO_USB_MODE=1`` (M5 AtomS3 and StampS3, Seeed XIAO
ESP32-C5) the USB-Serial-JTAG peripheral emulates that circuit in hardware and
the Arduino core's ``HWCDC.cpp`` never looks at the line state, so the same
pulse reboots it. On the Arduino Nano ESP32 the TinyUSB stack is in charge and
``USBCDC.cpp`` only knows a four step line-state sequence that enters the
bootloader, which this pulse never completes; the Nano ignores it and the
reset button is the fallback. After another 0.1 s the pulse ends with DTR and
RTS asserted again, DTR first, because TinyUSB's ``write()`` drops output
while DTR is low and raising RTS before DTR would pulse EN a second time.

After the reset the device may re-enumerate; ``SerialSource.read`` raises
``PortGone`` and ``read_fox`` reopens the same by-id path.

Not-a-fox outcomes after the reset, each a ``RunError`` (exit 2) with the text
in the constants below: nothing at all within 10 s, or output without a banner
within 15 s of the first byte. The 10 s mark prints the reset-button hint and
keeps waiting until the deadline, so a fox whose USB stack ignores the pulse
still gets its turn. With ``reset=False`` the script waits for the fox's own
wake cycle until the deadline instead.
"""
from __future__ import annotations

import codecs
import os
import re
import time
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from .conf import Block, ConfError, defined_for, select
from .report import Deadline, RunError

BAUD = 115200
NO_OUTPUT_SECONDS = 10.0
NO_BANNER_SECONDS = 15.0
RESET_PULSE_SECONDS = 0.1
# Seconds without a new line after the banner before the readback counts as
# complete when no project specific last line was seen.
QUIET_SECONDS = 2.0
# Seconds the read goes on after the project's last line, so the mismatch and
# PANIC lines a fox prints right after it are still taken. Classic prints
# nothing else for TIME_TO_WAKE seconds after its address, so the read cannot
# wait for a later line there.
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

# Project name in the banner -> directory of its verify script.
PROJECT_DIRS = {
    "classic_discoverable": "bluetooth/classic_discoverable",
    "iBeacon": "bluetooth/iBeacon",
    "wifi_ap_client": "wifi/wifi_ap_client",
    "zigbee_coordinator": "zigbee/zigbee_coordinator",
}

# The field whose line ends a project's readback on the success path.
LAST_FIELD = {
    "classic_discoverable": "address",
    "iBeacon": "advertising",
    "wifi_ap_client": "awake",
    "zigbee_coordinator": "awake",
}


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

_MAC6 = r"((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})"
_MAC8 = r"((?:[0-9A-Fa-f]{2}:){7}[0-9A-Fa-f]{2})"
_U16 = r"(0x[0-9A-Fa-f]{4})"

# (field, regex) for every line a fox prints, in the firmware's own formats.
# A field with several lines (mac, sleeping, tx_power) is written by whichever
# appears.
# Group 1 is the value kept; a regex without groups keeps the whole line.
LINES: List[Tuple[str, "re.Pattern[str]"]] = [
    # include/rfhssleeptimers.h and every main.cpp
    ("initializing", re.compile(r"^Initializing\.\.\.$")),
    ("boot_count", re.compile(r"^ESP32 boot count: (\d+)$")),
    ("sleep_stats", re.compile(r"^Sleep stats: (-?\d+s since cold boot, -?\d+s since last wakeup)$")),
    ("mac_set", re.compile(r"^MAC address set (successfully)$")),
    ("awake", re.compile(r"^(Awake and screaming)$")),
    ("sleeping", re.compile(r"^(Going to sleep)$")),
    ("sleeping", re.compile(r"^(entering deep sleep)$")),
    ("setting_up", re.compile(r"^Setting up (.+?)\u2026?$")),
    ("tx_power_status", re.compile(r"^Set power status: (ok|failed)$")),
    ("time_to_wake", re.compile(r"^Time to wake: (\d+)s$")),
    ("time_to_sleep", re.compile(r"^Time to sleep: (\d+)s$")),
    # include/rfhswifi.h, include/rfhszigbee.h and include/rfhsibeacon.h;
    # Wi-Fi prints the WIFI_POWER_* name, Zigbee a dBm number, iBeacon the
    # ESP_PWR_LVL_* name with its dBm in parentheses.
    ("psk", re.compile(r"^Operating PSK: (.*)$")),
    ("ssid_hidden", re.compile(r"^Hidden SSID: ([01])$")),
    ("max_clients", re.compile(r"^Max clients: (\d+)$")),
    ("tx_power", re.compile(r"^Tx power: (\S+?)(?: dBm)?$")),
    ("tx_power", re.compile(r"^Tx power: (ESP_PWR_LVL_\w+) \(-?\d+ dBm\)$")),
    # include/rfhszigbee.h and wifi/wifi_ap_client/src/main.cpp
    ("mac", re.compile(r"^Started Coordinator with MAC Address: " + _MAC8 + "$")),
    ("mac", re.compile(r"^Started AP with MAC Address: " + _MAC6 + "$")),
    ("mac", re.compile(r"^Started Client with MAC Address: " + _MAC6 + "$")),
    ("channel", re.compile(r"^Operating channel: (\d+)$")),
    ("pan_id", re.compile(r"^Operating PAN ID: " + _U16 + "$")),
    ("ext_pan_id", re.compile(r"^Extended PAN ID: " + _MAC8 + "$")),
    ("short_address", re.compile(r"^Short address: " + _U16 + "$")),
    ("packet_interval", re.compile(r"^Packet interval: (\d+)s$")),
    ("ssid", re.compile(r"^Operating SSID: (.*)$")),
    # include/rfhsbt.h, rfhsclassicdiscoverable.h and rfhsibeacon.h
    ("name", re.compile(r"^Device name: (.*)$")),
    ("address", re.compile(r"^Device address: " + _MAC6 + "$")),
    ("uuid", re.compile(r"^Beacon UUID: ([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
                        r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})$")),
    ("major", re.compile(r"^Major: 0x[0-9A-Fa-f]{4} \((\d+)\)$")),
    ("minor", re.compile(r"^Minor: 0x[0-9A-Fa-f]{4} \((\d+)\)$")),
    ("signal_power", re.compile(r"^Signal power: (-?\d+)$")),
    ("advertising", re.compile(r"^(iBeacon advertising!)$")),
]

# Lines that mean the fox refused to run or is not healthy. The firmware
# prints one of these, then halts on the fatal LED and prints PANIC.
PROBLEMS = [
    re.compile(r"^.* != .*$"),
    re.compile(r"^Error .*$"),
    re.compile(r"^Device address: unavailable.*$"),
    re.compile(r"^Beacon data is \d+ bytes, not 25$"),
    re.compile(r"^PANIC$"),
    re.compile(r"^Entered loop, we are broken$"),
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
        """True once the project's last readback line or a problem was seen."""
        if self.banner is None:
            return False
        if self.problems:
            return True
        last = LAST_FIELD.get(self.banner.project)
        return last is not None and last in self.fields

    def transcript(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.lines else "")


def parse_transcript(text: str) -> Readback:
    readback = Readback()
    readback.feed_text(text)
    return readback


class PortGone(Exception):
    """The serial device disappeared, as a native USB board does when it resets."""


class SerialSource:
    """A pyserial port read in chunks, with the reset pulse and reopening."""

    def __init__(self, path: str, baud: int = BAUD, sleep: Callable[[float], None] = time.sleep):
        self.path = path
        self.baud = baud
        self.sleep = sleep
        self.serial = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.open()

    def open(self) -> None:
        import serial
        port = serial.Serial()
        port.port = self.path
        port.baudrate = self.baud
        port.timeout = 0
        # pyserial asserts DTR before RTS when it opens, which leaves EN high
        # throughout on the auto-reset circuit.
        port.dtr = True
        port.rts = True
        port.open()
        self.serial = port
        self._decoder.reset()

    def close(self) -> None:
        if self.serial is not None:
            try:
                self.serial.close()
            except (OSError, ValueError):
                pass
            self.serial = None

    def reset(self) -> None:
        """esptool's HardReset, ending with both lines asserted again.

        The chip samples IO0 when EN rises, so the pause after RTS drops keeps
        the brief IO0 dip of raising DTR alone away from that moment. A native
        USB board may already have dropped off the bus by then; ``reopen``
        asserts the lines again in the same order.
        """
        port = self.serial
        # RTS is asserted from open(), so on the USB-Serial-JTAG circuit this
        # first change already pulls EN low and the device can be gone before
        # the next line-state call.
        port.dtr = False
        try:
            port.rts = True
            self.sleep(RESET_PULSE_SECONDS)
            port.rts = False
            self.sleep(RESET_PULSE_SECONDS)
            port.dtr = True
            port.rts = True
        except OSError:
            pass

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

    def reopen(self, deadline: Deadline) -> None:
        """Wait for the device path to come back and open it again."""
        import serial
        self.close()
        while True:
            if os.path.exists(self.path):
                try:
                    self.open()
                    return
                except (serial.SerialException, OSError):
                    pass
            if deadline.expired():
                raise RunError(PORT_GONE)
            self.sleep(min(REOPEN_POLL_SECONDS, deadline.remaining()))


class TranscriptSource:
    """A recorded transcript played back as a serial source, for the tests and
    for a serial-only run against a saved transcript.

    ``items`` are lines, each optionally preceded by a delay in seconds as
    ``(delay, line)``. ``read`` advances ``clock`` by the delay of the next
    line when the clock is a ``FakeClock``; with the real clock it sleeps.
    After the last line every read times out.
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

    @classmethod
    def from_file(cls, path: str, **kwargs) -> "TranscriptSource":
        with open(path, "r", encoding="utf-8") as handle:
            return cls(handle.read().splitlines(True), path=path, **kwargs)

    def _advance(self, seconds: float) -> None:
        if hasattr(self.clock, "advance"):
            self.clock.advance(seconds)
        elif seconds > 0:
            self.sleep(seconds)

    def reset(self) -> None:
        self.resets += 1

    def reopen(self, deadline: Deadline) -> None:
        self.reopens += 1

    def close(self) -> None:
        pass

    def read(self, timeout: float) -> Optional[str]:
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
        if not line.endswith("\n"):
            line += "\n"
        return line


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
             debug: Callable[[str], None] = lambda text: None) -> Readback:
    """Reset the fox, wait for its banner, read its readback lines.

    Returns the ``Readback`` once a problem line, the project's last line plus
    ``DRAIN_SECONDS``, a quiet spell after the banner or the deadline ends it.
    Raises ``RunError`` with the not-a-fox texts when no banner arrives.
    """
    readback = Readback()
    buffer = ""
    clock = deadline.now
    if reset:
        debug("resetting the fox on %s" % source.path)
        source.reset()
    started = clock()
    first_output: Optional[float] = None
    last_line: Optional[float] = None
    drain_until: Optional[float] = None
    hinted = False
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
            if readback.feed(line) == "banner":
                say(readback.banner.text())
    if buffer.strip():
        readback.feed(buffer)
    return readback


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
