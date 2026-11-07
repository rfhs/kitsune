"""The Bluetooth Classic fox on the air: a BR/EDR inquiry driven through ``btmgmt``.

``btmgmt --index N find -b`` runs one general inquiry on ``hciN``, 10.24 s long,
and prints a line for every device that answers::

    hci0 dev_found: F2:F6:6D:BC:2A:80 type BR/EDR rssi -61 flags 0x0000
    AD flags 0x00
    name Demo Case BTC Hard Fox

The ``name`` line (``short name`` when the EIR had to shorten it) belongs to
the ``dev_found`` just before it. ``Inquiry`` is a thread started before the
fox is reset, so the first inquiry already runs while the fox boots. It does
not yet know which block of the header the fox was built from, so it keeps
every device that answers and the caller names the address to look for with
``set_target`` once the banner has arrived. An inquiry stops as soon as the
target answered with a name, and another one starts while the remaining time
allows, because the fox may still have been booting during the first. btmgmt
needs root or CAP_NET_ADMIN, checked by the caller through ``privileges``
before the fox is reset.

When the fox answered without a name in its EIR, ``remote_name`` asks
``bluetoothctl info`` for the name bluetoothd resolved, and when it has none
yet runs a short ``bluetoothctl scan bredr`` so bluetoothd requests it, then
asks again. Both are best effort: no bluetoothctl, or no name, leaves the
NAME row unverified with that reason.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence

from .conf import Block
from .report import Deadline, Report, RunError
from .serial_fox import Readback
from .tshark import LineReader

# A general inquiry is 10.24 s; btmgmt reports the end a moment later.
INQUIRY_SECONDS = 11.0
# Seconds bluetoothctl scans for a remote name when bluetoothd has none cached.
REMOTE_NAME_SCAN_SECONDS = 12.0
POLL_SECONDS = 0.25

DEV_FOUND = re.compile(r"(?:^|\s)dev_found:\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+type\s+(\S+)"
                       r"\s+rssi\s+(-?\d+)\s+flags\s+(0x[0-9A-Fa-f]+)")
NAME_LINE = re.compile(r"^\s*(short name|name)\s+(.*?)\s*$")
INFO_NAME = re.compile(r"^\s*Name:\s+(.*?)\s*$")


class Found(NamedTuple):
    """One inquiry response, with the name when the EIR carried one."""

    address: str
    type: str
    rssi: int
    flags: str
    name: Optional[str]
    short_name: bool


class BtmgmtParser:
    """Feeds ``btmgmt`` output line by line and keeps the devices by address."""

    def __init__(self):
        self.devices: Dict[str, Found] = {}
        self._last: Optional[str] = None

    def feed(self, line: str) -> Optional[Found]:
        """Record one line; return the device it completed or changed."""
        line = line.rstrip("\r\n")
        match = DEV_FOUND.search(line)
        if match:
            address = match.group(1).upper()
            found = Found(address, match.group(2), int(match.group(3)), match.group(4), None, False)
            previous = self.devices.get(address)
            if previous is not None and previous.name is not None:
                found = found._replace(name=previous.name, short_name=previous.short_name)
            self.devices[address] = found
            self._last = address
            return found
        match = NAME_LINE.match(line)
        if match and self._last is not None:
            found = self.devices[self._last]._replace(name=match.group(2),
                                                      short_name=match.group(1) == "short name")
            self.devices[self._last] = found
            return found
        return None

    def feed_text(self, text: str) -> None:
        for line in text.splitlines():
            self.feed(line)

    def get(self, address: str) -> Optional[Found]:
        return self.devices.get(address.upper())


def parse_btmgmt(text: str) -> List[Found]:
    parser = BtmgmtParser()
    parser.feed_text(text)
    return list(parser.devices.values())


def adapter_index(adapter: str) -> int:
    """``hci0`` -> 0."""
    match = re.fullmatch(r"hci(\d+)", adapter)
    if not match:
        raise RunError("%s is not a Bluetooth adapter name (hciN)" % adapter)
    return int(match.group(1))


def btmgmt_command(btmgmt: str, adapter: str) -> List[str]:
    return [btmgmt, "--index", str(adapter_index(adapter)), "find", "-b"]


def named(parser: BtmgmtParser, target: Optional[str]) -> bool:
    """True when the target is known and answered with a name."""
    if target is None:
        return False
    found = parser.get(target)
    return found is not None and found.name is not None


def run_inquiry(argv: Sequence[str], deadline: Deadline, target: Callable[[], Optional[str]],
                popen: Callable = subprocess.Popen,
                debug: Callable[[str], None] = lambda text: None,
                stop: Optional[threading.Event] = None,
                parser: Optional[BtmgmtParser] = None) -> BtmgmtParser:
    """One ``btmgmt find -b``: read until the address ``target()`` names
    answered with a name, the inquiry ended, ``stop`` was set or the deadline
    passed. Every device that answered is in the returned parser."""
    if parser is None:
        parser = BtmgmtParser()
    reader = LineReader(argv, popen).start()
    try:
        while True:
            remaining = deadline.remaining()
            if remaining <= 0 or (stop is not None and stop.is_set()) or named(parser, target()):
                break
            line = reader.read(min(remaining, POLL_SECONDS))
            if line is None:
                if reader.eof:
                    code = reader.wait(deadline.budget(2.0))
                    if code not in (0, None) and not parser.devices:
                        raise RunError(reader.error())
                    break
                continue
            debug("btmgmt: " + line)
            parser.feed(line)
    finally:
        reader.stop()
    return parser


def inquiry(adapter: str, deadline: Deadline, btmgmt: str,
            target: Callable[[], Optional[str]] = lambda: None,
            popen: Callable = subprocess.Popen,
            debug: Callable[[str], None] = lambda text: None,
            stop: Optional[threading.Event] = None) -> BtmgmtParser:
    """Inquiries on ``adapter`` until the target answered with a name, ``stop``
    was set, or the time left is too short for another full inquiry. The
    devices of every inquiry are in the returned parser; a later answer with
    a name replaces an earlier one without."""
    argv = btmgmt_command(btmgmt, adapter)
    parser = BtmgmtParser()
    while True:
        debug("running: " + " ".join(argv))
        run_inquiry(argv, deadline, target, popen, debug, stop, parser)
        if named(parser, target()) or (stop is not None and stop.is_set()):
            return parser
        if deadline.remaining() < INQUIRY_SECONDS:
            return parser


class Inquiry(threading.Thread):
    """The inquiries on their own thread, started before the fox is reset.

    ``set_target`` names the fox's address once the banner has chosen the
    header block; until then every answer is kept and none ends the inquiry.
    ``result`` waits for the thread and returns the parser; an error from
    btmgmt is raised there.
    """

    def __init__(self, adapter: str, deadline: Deadline, btmgmt: str,
                 popen: Callable = subprocess.Popen,
                 debug: Callable[[str], None] = lambda text: None):
        threading.Thread.__init__(self, daemon=True)
        self.adapter = adapter
        self.deadline = deadline
        self.btmgmt = btmgmt
        self.popen = popen
        self.debug = debug
        self.target: Optional[str] = None
        self.parser: Optional[BtmgmtParser] = None
        self.error: Optional[BaseException] = None
        self._stopping = threading.Event()

    def set_target(self, address: str) -> None:
        self.target = address.upper()

    def run(self) -> None:
        try:
            self.parser = inquiry(self.adapter, self.deadline, self.btmgmt, lambda: self.target,
                                  self.popen, self.debug, self._stopping)
        except BaseException as error:
            self.error = error

    def stop(self) -> None:
        self._stopping.set()

    def result(self, deadline: Optional[Deadline] = None) -> BtmgmtParser:
        deadline = deadline or self.deadline
        self.join(max(0.0, deadline.remaining()) + 1.0)
        if self.is_alive():
            self.stop()
            self.join(2.0)
        if self.error is not None:
            if isinstance(self.error, RunError):
                raise self.error
            raise RunError("inquiry on %s failed: %s" % (self.adapter, self.error))
        return self.parser if self.parser is not None else BtmgmtParser()


def parse_info_name(text: str) -> Optional[str]:
    """The ``Name:`` line of ``bluetoothctl info``."""
    for line in text.splitlines():
        match = INFO_NAME.match(line)
        if match:
            return match.group(1)
    return None


def default_run(argv: Sequence[str], timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, check=False, timeout=timeout)


def remote_name(address: str, deadline: Deadline, bluetoothctl: Optional[str],
                run: Callable = default_run, debug: Callable[[str], None] = lambda text: None,
                sleep: Callable[[float], None] = time.sleep) -> Optional[str]:
    """The fox's name from bluetoothd when the inquiry response had none.
    Returns None when bluetoothctl is missing, nothing is cached and no time
    is left for a scan, or the scan did not resolve it."""
    if bluetoothctl is None:
        debug("bluetoothctl not installed, no remote name request")
        return None

    def info() -> Optional[str]:
        try:
            result = run([bluetoothctl, "info", address], timeout=max(1.0, deadline.budget(5.0)))
        except (OSError, subprocess.SubprocessError) as error:
            debug("bluetoothctl info: %s" % error)
            return None
        return parse_info_name(result.stdout or "")

    name = info()
    if name is not None:
        return name
    seconds = deadline.budget(REMOTE_NAME_SCAN_SECONDS)
    if seconds < 2.0:
        return None
    debug("bluetoothctl scan bredr for %.0f s to resolve the name" % seconds)
    try:
        run([bluetoothctl, "--timeout", str(int(seconds)), "scan", "bredr"], timeout=seconds + 5.0)
    except (OSError, subprocess.SubprocessError) as error:
        debug("bluetoothctl scan: %s" % error)
        return None
    return info()


def rows(report: Report, block: Block, readback: Readback, found: Optional[Found],
         name: Optional[str] = None, reason: str = "") -> None:
    """The on-air rows of the Classic fox: MAC_ADDR from the inquiry response
    and NAME from its EIR or from ``name``, the remote name request's answer.
    ``found`` None means no response and ``reason`` says why. The sleep timers
    are the caller's serial-only rows."""
    if found is None and not reason:
        reason = "no inquiry response"
    report.check("MAC_ADDR", block.mac("MAC_ADDR"), readback.upper("address"),
                 found.address if found else None, reason=reason)
    air_name = None
    name_reason = reason
    if found is not None:
        air_name = found.name if found.name is not None else name
        if air_name is None:
            name_reason = "inquiry response without a name and no remote name"
        elif found.name is None:
            name_reason = ""
    report.check("NAME", block.string("NAME"), readback.get("name"), air_name, reason=name_reason)
