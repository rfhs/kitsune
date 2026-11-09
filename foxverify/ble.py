"""The iBeacon fox on the air: an active BLE scan with bleak and the payload decode.

The fox advertises ``ADV_TYPE_SCAN_IND``: the manufacturer data with the
iBeacon payload is in the advertisement, the device name only in the scan
response, so a passive sniffer never sees the name and the laptop's adapter
runs an active scan instead. ``BleScan`` runs that scan on its own thread so
the caller can start it before resetting the fox and read the result after
the serial readback; a MEDIUM or HARD fox is only on the air for a few seconds
in each cycle and the first window must not be missed. Before the banner has
chosen the header block the fox's address is not known, so the scan is given
every ``MAC_ADDR`` in the header and keeps what it sees of each; the caller
names the one that matters with ``set_target`` and the scan ends once that
address was seen with both its payload and its name.

bleak is imported inside the functions that need it so the serial-only path
and the tests work without it, and a missing import gives the package and venv
hint instead of a traceback. BlueZ caches the name and the manufacturer data
of a device it has seen, so the fox's cached device object is removed over
D-Bus (``org.bluez.Adapter1.RemoveDevice``) before the scan; without that a
reflashed fox could be reported with its old name.

iBeacon payload, after the Apple company id 0x004C: type 0x02, length 0x15,
the 16 byte proximity UUID, major and minor as 16 bit big endian, and the
signal power as a signed byte, so 0xC5 is -59 dBm. Bluedroid sends a
``DEVICE_NAME`` of up to 29 characters complete; the header guard keeps the
names in that range, and ``expected_name`` says what a longer one would look
like on the air.

Every advertisement or scan response from a candidate address is also logged
as ``cycle.Heard`` with its RSSI, and ``BleScan.take_heard`` hands the run
what arrived for the fox; with ``keep_scanning`` the scan goes on after the
fox is complete so the run can hear it through its first sleep into wake 2.
"""
from __future__ import annotations

import asyncio
import struct
import threading
import time
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Union

from .conf import Block
from .cycle import Heard, HeardLog
from .report import Deadline, Report, RunError
from .serial_fox import Readback

APPLE_COMPANY_ID = 0x004C
IBEACON_TYPE = 0x02
IBEACON_LENGTH = 0x15
# The longest complete name Bluedroid fits into the 31 byte scan response.
NAME_LIMIT = 29

BLEAK_MISSING = (
    "bleak is not installed. Debian/Ubuntu: apt install python3-bleak; Arch: pacman -S python-bleak; "
    "Gentoo: dev-python/bleak from the GURU overlay, or a venv: "
    "python3 -m venv --system-site-packages .venv && .venv/bin/pip install bleak, "
    "then run .venv/bin/python3 ./verify")


def import_bleak():
    """The bleak module, or ``RunError`` with the install hint."""
    try:
        import bleak
    except ImportError:
        raise RunError(BLEAK_MISSING)
    return bleak


class IBeacon(NamedTuple):
    uuid: str
    major: int
    minor: int
    signal_power: int


def format_uuid(raw: bytes) -> str:
    text = raw.hex().upper()
    return "-".join((text[0:8], text[8:12], text[12:16], text[16:20], text[20:32]))


def decode_ibeacon(data: bytes) -> Optional[IBeacon]:
    """The iBeacon fields from manufacturer data; ``data`` may start with the
    company id (the 25 byte block the firmware prints) or follow it (the 23
    bytes bleak hands over). None when it is not an iBeacon payload."""
    if len(data) == 25 and data[:2] == b"\x4c\x00":
        data = data[2:]
    if len(data) != 23 or data[0] != IBEACON_TYPE or data[1] != IBEACON_LENGTH:
        return None
    uuid = format_uuid(data[2:18])
    major, minor, power = struct.unpack(">HHb", data[18:23])
    return IBeacon(uuid, major, minor, power)


def expected_name(name: str) -> str:
    """The name an active scan reads back for ``name``: the text itself up to
    29 characters, the first 29 as a short name beyond that."""
    return name[:NAME_LIMIT]


def device_path(adapter: str, address: str) -> str:
    """The BlueZ object path of a device: ``/org/bluez/hci0/dev_F2_82_42_D0_84_BC``."""
    return "/org/bluez/%s/dev_%s" % (adapter, address.upper().replace(":", "_"))


class Seen(NamedTuple):
    """What the scan collected about the fox."""

    address: str
    name: Optional[str]
    beacon: Optional[IBeacon]
    rssi: Optional[int]
    time: float

    def complete(self) -> bool:
        return self.beacon is not None and self.name is not None


async def remove_cached_device(adapter: str, address: str,
                               debug: Callable[[str], None] = lambda text: None) -> bool:
    """Ask bluetoothd to forget the fox so the scan reports fresh data. A
    device BlueZ never saw is not an error; a missing D-Bus library or a
    refused call is noted and the scan goes ahead."""
    try:
        from dbus_fast import BusType, Message, MessageType
        from dbus_fast.aio import MessageBus
    except ImportError:
        debug("dbus_fast not available, cached device not removed")
        return False
    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    except Exception as error:
        debug("system bus: %s" % error)
        return False
    try:
        reply = await bus.call(Message(destination="org.bluez", path="/org/bluez/" + adapter,
                                       interface="org.bluez.Adapter1", member="RemoveDevice",
                                       signature="o", body=[device_path(adapter, address)]))
        if reply.message_type == MessageType.ERROR:
            debug("RemoveDevice: %s" % reply.error_name)
            return False
        debug("removed cached BlueZ device for %s" % address)
        return True
    finally:
        bus.disconnect()


def merge(seen: Optional[Seen], address: str, name: Optional[str], payload: Optional[bytes],
          rssi: Optional[int], now: float) -> Seen:
    """Fold one advertisement or scan response into what is known. bleak
    reports the two separately at first, so the name and the beacon arrive in
    different callbacks and each keeps the other's value."""
    beacon = decode_ibeacon(payload) if payload is not None else None
    if seen is not None:
        name = name if name is not None else seen.name
        beacon = beacon if beacon is not None else seen.beacon
        rssi = rssi if rssi is not None else seen.rssi
    return Seen(address.upper(), name, beacon, rssi, now)


def address_set(addresses: Union[str, Iterable[str]]) -> frozenset:
    """Upper case addresses from one address or several."""
    if isinstance(addresses, str):
        addresses = [addresses]
    return frozenset(address.upper() for address in addresses)


def target_complete(seen: Dict[str, Seen], target: Optional[str]) -> bool:
    """True when the target is known and was seen with payload and name."""
    return target is not None and target in seen and seen[target].complete()


async def scan_async(adapter: str, addresses: Union[str, Iterable[str]], deadline: Deadline,
                     remove_cached: bool = True, debug: Callable[[str], None] = lambda text: None,
                     stop: Optional[threading.Event] = None,
                     target: Callable[[], Optional[str]] = lambda: None,
                     seen: Optional[Dict[str, Seen]] = None, heard: Optional[HeardLog] = None,
                     keep: Callable[[], bool] = lambda: False,
                     clock: Callable[[], float] = time.time) -> Dict[str, Seen]:
    """Active scan on ``adapter`` collecting what is seen of each address in
    ``addresses`` until the address ``target()`` names was seen with both
    its payload and its name and ``keep()`` is false, ``stop`` is set, or the
    deadline passes. Returns what was seen, keyed by upper case address, in
    ``seen`` when the caller gave the dict; every packet from a candidate
    goes into ``heard`` as well."""
    bleak = import_bleak()
    want = address_set(addresses)
    if remove_cached:
        for address in sorted(want):
            await remove_cached_device(adapter, address, debug)
    loop = asyncio.get_running_loop()
    done = asyncio.Event()
    if seen is None:
        seen = {}

    def finished() -> bool:
        return target_complete(seen, target()) and not keep()

    def callback(device, advertisement) -> None:
        address = device.address.upper()
        if address not in want:
            return
        now = clock()
        payload = advertisement.manufacturer_data.get(APPLE_COMPANY_ID)
        seen[address] = merge(seen.get(address), address, advertisement.local_name, payload,
                              advertisement.rssi, now)
        if heard is not None:
            heard.add(address, now, advertisement.rssi)
        debug("seen %s name %r beacon %s rssi %s" % (address, seen[address].name, seen[address].beacon,
                                                     seen[address].rssi))
        if finished():
            loop.call_soon_threadsafe(done.set)

    scanner = bleak.BleakScanner(detection_callback=callback, adapter=adapter, scanning_mode="active")
    await scanner.start()
    try:
        while not done.is_set() and not finished():
            remaining = deadline.remaining()
            if remaining <= 0 or (stop is not None and stop.is_set()):
                break
            try:
                await asyncio.wait_for(done.wait(), min(remaining, 0.25))
            except asyncio.TimeoutError:
                pass
            if done.is_set() and not finished():
                done.clear()
    finally:
        await scanner.stop()
    return seen


class BleScan(threading.Thread):
    """The active scan on its own thread, started before the fox is reset.

    ``set_target`` names the fox's address once the banner has chosen the
    header block. ``seen`` fills while the scan runs; ``complete(address)``
    says whether an address was seen with payload and name, and
    ``take_heard(address)`` hands over the frames from it since the last
    call. The scan ends when the target is complete unless ``keep_scanning``
    is set, when the deadline passes, or when ``stop`` is called;
    ``result(deadline)`` waits for that and returns what was seen of every
    address. An error in the scan is raised from ``result``.
    """

    def __init__(self, adapter: str, addresses: Union[str, Iterable[str]], deadline: Deadline,
                 remove_cached: bool = True, debug: Callable[[str], None] = lambda text: None,
                 clock: Callable[[], float] = time.time):
        threading.Thread.__init__(self, daemon=True)
        self.adapter = adapter
        self.addresses = address_set(addresses)
        self.deadline = deadline
        self.remove_cached = remove_cached
        self.debug = debug
        self.clock = clock
        self.target: Optional[str] = None
        self.keep_scanning = False
        self.seen: Dict[str, Seen] = {}
        self.heard = HeardLog()
        self.error: Optional[BaseException] = None
        self._stopping = threading.Event()

    def set_target(self, address: str) -> None:
        self.target = address.upper()

    def complete(self, address: str) -> bool:
        return target_complete(self.seen, address.upper())

    def take_heard(self, address: str) -> List[Heard]:
        return self.heard.take(address)

    def start(self) -> None:
        import_bleak()
        threading.Thread.start(self)

    def run(self) -> None:
        try:
            asyncio.run(scan_async(self.adapter, self.addresses, self.deadline, self.remove_cached,
                                   self.debug, self._stopping, lambda: self.target, self.seen,
                                   self.heard, lambda: self.keep_scanning, self.clock))
        except BaseException as error:
            self.error = error

    def stop(self) -> None:
        self._stopping.set()

    def result(self, deadline: Optional[Deadline] = None) -> Dict[str, Seen]:
        deadline = deadline or self.deadline
        self.join(max(0.0, deadline.remaining()) + 1.0)
        if self.is_alive():
            self.stop()
            self.join(2.0)
        if self.error is not None:
            if isinstance(self.error, RunError):
                raise self.error
            raise RunError("BLE scan on %s failed: %s" % (self.adapter, self.error))
        return self.seen


def rows(report: Report, block: Block, readback: Readback, seen: Optional[Seen],
         reason: str = "") -> None:
    """The on-air rows of the iBeacon fox: MAC_ADDR, DEVICE_NAME, BEACON_UUID,
    MAJOR, MINOR and SIGNAL_POWER. ``seen`` None means the fox was not heard
    and ``reason`` says why. The timers and TXPOWER are the caller's
    serial-only rows."""
    if seen is None and not reason:
        reason = "not seen by the scan"
    beacon = seen.beacon if seen else None
    beacon_reason = reason if beacon is not None or seen is None else "seen without an iBeacon payload"

    report.check("MAC_ADDR", block.mac("MAC_ADDR"), readback.upper("address"),
                 seen.address if seen else None, reason=reason)

    name = block.string("DEVICE_NAME")
    name_reason = reason if seen is None else "seen without a scan response carrying the name"
    report.check("DEVICE_NAME", name, readback.get("name"), seen.name if seen else None,
                 reason=name_reason)

    report.check("BEACON_UUID", block.string("BEACON_UUID").upper(), readback.upper("uuid"),
                 beacon.uuid if beacon else None, reason=beacon_reason)
    report.check("MAJOR", block.integer("MAJOR"), readback.integer("major"),
                 beacon.major if beacon else None, reason=beacon_reason)
    report.check("MINOR", block.integer("MINOR"), readback.integer("minor"),
                 beacon.minor if beacon else None, reason=beacon_reason)
    power = block.integer("SIGNAL_POWER")
    if power > 127:
        power -= 256
    report.check("SIGNAL_POWER", power, readback.integer("signal_power"),
                 beacon.signal_power if beacon else None, reason=beacon_reason)
