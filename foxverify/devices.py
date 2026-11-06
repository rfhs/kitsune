"""Classification and autodetection of the devices a verify script uses.

A positional DEVICE argument is a plain name and is classified by what it is:

- ``/sys/class/net/<name>`` exists: a Wi-Fi interface.
- ``hci[0-9]+``: a Bluetooth adapter.
- a serial port whose USB id is ``1915:154A``: the nRF 802.15.4 sniffer.
- any other serial port: the fox.

When no fox is given, the serial ports with an Espressif, Silicon Labs CP210x,
WCH or FTDI vendor id are the candidates. Exactly one is used. None means the
script waits up to ``--wait-for-fox`` seconds for one to appear, because a
native USB board in deep sleep has no serial device, then gives up with "no
ESP32 serial device found". Several are listed with path, VID:PID, product and
serial number and the user is asked to name one. A sniffer is autodetected only
when it is unambiguous: an nRF by USB id, ``hciN`` when there is exactly one
adapter. A Wi-Fi interface is never guessed, because putting the wrong card
into monitor mode takes the laptop offline.

Serial devices are always referred to by their ``/dev/serial/by-id/`` path when
one exists: a native USB board re-enumerates after deep sleep and its raw
``/dev/ttyACMn`` number can change, the by-id link cannot.

``python3 -m foxverify.devices`` lists what the rules see on this machine.
"""
from __future__ import annotations

import os
import re
import sys
import time
from typing import Callable, Iterable, List, NamedTuple, Optional, Sequence

from .report import Deadline, RunError

WIFI = "wifi"
HCI = "hci"
SNIFFER = "sniffer"
FOX = "fox"

NRF_SNIFFER_ID = (0x1915, 0x154A)
# Vendor ids of the USB serial bridges and native USB stacks the foxes use:
# Espressif (native USB, also the Arduino Nano ESP32 in TinyUSB mode), Silicon
# Labs CP210x, WCH CH910x and FTDI.
FOX_VENDOR_IDS = {
    0x303A: "Espressif",
    0x10C4: "Silicon Labs",
    0x1A86: "WCH",
    0x0403: "FTDI",
}

NET_DIR = "/sys/class/net"
BLUETOOTH_DIR = "/sys/class/bluetooth"
BY_ID_DIR = "/dev/serial/by-id"
DEV_DIR = "/dev"

NO_FOX = "no ESP32 serial device found"

_HCI = re.compile(r"hci[0-9]+")


class Port(NamedTuple):
    """What the device rules need to know about one serial port."""

    device: str
    vid: Optional[int]
    pid: Optional[int]
    product: Optional[str]
    serial_number: Optional[str]

    def usb_id(self) -> str:
        if self.vid is None or self.pid is None:
            return "no USB id"
        return "%04X:%04X" % (self.vid, self.pid)

    def describe(self) -> str:
        """Path, VID:PID, product and serial number on one line."""
        return "%s  %s  %s  %s" % (self.device, self.usb_id(),
                                   self.product or "unknown product",
                                   self.serial_number or "no serial number")

    def is_sniffer(self) -> bool:
        return (self.vid, self.pid) == NRF_SNIFFER_ID

    def is_fox_candidate(self) -> bool:
        return self.vid in FOX_VENDOR_IDS


class Device(NamedTuple):
    kind: str
    path: str
    port: Optional[Port]


def list_ports(comports: Optional[Callable[[], Iterable]] = None) -> List[Port]:
    """Every serial port pyserial knows, as ``Port`` records."""
    if comports is None:
        from serial.tools.list_ports import comports as pyserial_comports
        comports = pyserial_comports
    ports = []
    for info in comports():
        ports.append(Port(info.device, getattr(info, "vid", None), getattr(info, "pid", None),
                          getattr(info, "product", None), getattr(info, "serial_number", None)))
    return sorted(ports, key=lambda p: p.device)


def by_id_path(device: str, by_id_dir: str = BY_ID_DIR) -> str:
    """The ``/dev/serial/by-id/`` link for ``device`` when one exists, else ``device``."""
    try:
        names = sorted(os.listdir(by_id_dir))
    except OSError:
        return device
    target = os.path.realpath(device)
    for name in names:
        link = os.path.join(by_id_dir, name)
        if os.path.realpath(link) == target:
            return link
    return device


def _same_port(a: str, b: str) -> bool:
    return os.path.realpath(a) == os.path.realpath(b)


def find_port(device: str, ports: Sequence[Port]) -> Optional[Port]:
    for port in ports:
        if _same_port(port.device, device):
            return port
    return None


def classify(name: str, ports: Optional[Sequence[Port]] = None, net_dir: str = NET_DIR,
             by_id_dir: str = BY_ID_DIR, dev_dir: str = DEV_DIR,
             exists: Callable[[str], bool] = os.path.exists) -> Device:
    """Apply the device rules to one positional argument."""
    if "/" not in name and exists(os.path.join(net_dir, name)):
        return Device(WIFI, name, None)
    if _HCI.fullmatch(name):
        return Device(HCI, name, None)
    path = name
    if "/" not in name and not exists(name) and exists(os.path.join(dev_dir, name)):
        path = os.path.join(dev_dir, name)
    if ports is None:
        ports = list_ports()
    port = find_port(path, ports)
    if port is None and not exists(path):
        raise RunError("%s: not a network interface, a Bluetooth adapter or a serial port" % name)
    path = by_id_path(path, by_id_dir)
    if port is not None and port.is_sniffer():
        return Device(SNIFFER, path, port)
    return Device(FOX, path, port)


def fox_candidates(ports: Sequence[Port]) -> List[Port]:
    return [port for port in ports if port.is_fox_candidate()]


def several_foxes(candidates: Sequence[Port], by_id_dir: str = BY_ID_DIR) -> RunError:
    lines = ["%d ESP32 serial devices found, pass the fox's path:" % len(candidates)]
    for port in candidates:
        lines.append("  " + port._replace(device=by_id_path(port.device, by_id_dir)).describe())
    return RunError("\n".join(lines))


def autodetect_fox(wait_seconds: float, deadline: Optional[Deadline] = None,
                   comports: Optional[Callable[[], Iterable]] = None,
                   sleep: Callable[[float], None] = time.sleep,
                   clock: Callable[[], float] = time.monotonic,
                   say: Callable[[str], None] = lambda text: None,
                   by_id_dir: str = BY_ID_DIR, poll: float = 0.5) -> Device:
    """The one fox candidate, waiting up to ``wait_seconds`` (and never past
    ``deadline``) for a sleeping native USB board to enumerate."""
    until = clock() + max(0.0, wait_seconds)
    if deadline is not None:
        until = min(until, deadline.at)
    announced = False
    while True:
        candidates = fox_candidates(list_ports(comports))
        if len(candidates) == 1:
            port = candidates[0]
            return Device(FOX, by_id_path(port.device, by_id_dir), port)
        if len(candidates) > 1:
            raise several_foxes(candidates, by_id_dir)
        now = clock()
        if now >= until:
            raise RunError(NO_FOX)
        if not announced:
            say("no ESP32 serial device yet, waiting up to %.0f s for one to appear"
                % (until - now))
            announced = True
        sleep(min(poll, until - now))


def autodetect_sniffer(ports: Sequence[Port], by_id_dir: str = BY_ID_DIR) -> Optional[Device]:
    """The nRF sniffer when exactly one is plugged in."""
    sniffers = [port for port in ports if port.is_sniffer()]
    if len(sniffers) != 1:
        return None
    return Device(SNIFFER, by_id_path(sniffers[0].device, by_id_dir), sniffers[0])


def hci_adapters(bluetooth_dir: str = BLUETOOTH_DIR) -> List[str]:
    try:
        names = os.listdir(bluetooth_dir)
    except OSError:
        return []
    return sorted(name for name in names if _HCI.fullmatch(name))


def autodetect_hci(bluetooth_dir: str = BLUETOOTH_DIR) -> Optional[Device]:
    """The Bluetooth adapter when exactly one exists."""
    adapters = hci_adapters(bluetooth_dir)
    if len(adapters) != 1:
        return None
    return Device(HCI, adapters[0], None)


class Selection(NamedTuple):
    """The devices one run uses; a kind is None when it was neither given nor found."""

    fox: Optional[Device]
    sniffer: Optional[Device]
    hci: Optional[Device]
    wifi: Optional[Device]


def select(names: Sequence[str], wait_for_fox: float, deadline: Optional[Deadline] = None,
           want_sniffer: bool = False, want_hci: bool = False,
           comports: Optional[Callable[[], Iterable]] = None,
           say: Callable[[str], None] = lambda text: None,
           sleep: Callable[[float], None] = time.sleep,
           clock: Callable[[], float] = time.monotonic,
           net_dir: str = NET_DIR, bluetooth_dir: str = BLUETOOTH_DIR,
           by_id_dir: str = BY_ID_DIR, dev_dir: str = DEV_DIR,
           exists: Callable[[str], bool] = os.path.exists) -> Selection:
    """Classify the positional arguments and autodetect what they left out.

    ``want_sniffer`` and ``want_hci`` say which sniffer kind the project uses,
    so only that one is looked for. Two devices of the same kind are an error.
    """
    ports = list_ports(comports)
    found = {}
    for name in names:
        device = classify(name, ports, net_dir, by_id_dir, dev_dir, exists)
        if device.kind in found:
            raise RunError("two %s devices given: %s and %s" % (device.kind, found[device.kind].path,
                                                               device.path))
        found[device.kind] = device
    fox = found.get(FOX)
    if fox is None:
        fox = autodetect_fox(wait_for_fox, deadline, comports, sleep, clock, say, by_id_dir)
    sniffer = found.get(SNIFFER)
    if sniffer is None and want_sniffer:
        sniffer = autodetect_sniffer(ports, by_id_dir)
    hci = found.get(HCI)
    if hci is None and want_hci:
        hci = autodetect_hci(bluetooth_dir)
    return Selection(fox, sniffer, hci, found.get(WIFI))


def main(argv: Optional[List[str]] = None) -> int:
    """List the serial ports, adapters and interfaces the rules see."""
    out = sys.stdout
    ports = list_ports()
    out.write("serial ports:\n")
    for port in ports:
        if port.is_sniffer():
            kind = "nRF 802.15.4 sniffer"
        elif port.is_fox_candidate():
            kind = "fox candidate (%s)" % FOX_VENDOR_IDS[port.vid]
        else:
            kind = "other"
        out.write("  %s  [%s]\n" % (port._replace(device=by_id_path(port.device)).describe(), kind))
    if not ports:
        out.write("  none\n")
    out.write("bluetooth adapters: %s\n" % (", ".join(hci_adapters()) or "none"))
    try:
        interfaces = sorted(os.listdir(NET_DIR))
    except OSError:
        interfaces = []
    wireless = [name for name in interfaces if os.path.isdir(os.path.join(NET_DIR, name, "wireless"))]
    out.write("network interfaces: %s\n" % (", ".join(interfaces) or "none"))
    out.write("wireless interfaces: %s\n" % (", ".join(wireless) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
