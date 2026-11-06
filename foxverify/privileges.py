"""Tool and privilege checks a verify script runs before it touches a radio.

Monitor mode, a live ``tshark`` capture and ``btmgmt`` need root or the
CAP_NET_ADMIN and CAP_NET_RAW capabilities; bleak talks to BlueZ over D-Bus
and pyserial opens a device node, so neither needs any of that. The checks
raise ``RunError`` (exit 2) naming the missing tool or privilege and never try
to gain it: the user decides whether to run the script under ``sudo``.

A Debian ``tshark`` whose ``dumpcap`` carries file capabilities and is
executable by the user (the ``wireshark`` group) captures without root, so
``can_capture`` accepts that case as well.
"""
from __future__ import annotations

import os
import shutil
from typing import Callable, Iterable, Optional

from .report import RunError

CAP_NET_ADMIN = 12
CAP_NET_RAW = 13

# Package names per distribution for the message when a tool is missing.
PACKAGES = {
    "tshark": "Debian/Ubuntu: tshark, Arch: wireshark-cli, Gentoo: net-analyzer/wireshark",
    "iw": "Debian/Ubuntu and Arch: iw, Gentoo: net-wireless/iw",
    "ip": "Debian/Ubuntu: iproute2, Arch: iproute2, Gentoo: sys-apps/iproute2",
    "btmgmt": "Debian/Ubuntu: bluez, Arch: bluez-utils, Gentoo: net-wireless/bluez",
    "bluetoothctl": "Debian/Ubuntu: bluez, Arch: bluez-utils, Gentoo: net-wireless/bluez",
}

NEED_NET_ADMIN = ("%s needs root or the CAP_NET_ADMIN and CAP_NET_RAW capabilities; "
                  "run this script with sudo")


def missing_tool(name: str) -> str:
    hint = PACKAGES.get(name)
    return "%s is not installed%s" % (name, " (%s)" % hint if hint else "")


def require_tool(name: str, which: Callable[[str], Optional[str]] = shutil.which) -> str:
    """The path of ``name`` on PATH, or ``RunError`` with the package hint."""
    path = which(name)
    if path is None:
        raise RunError(missing_tool(name))
    return path


def require_tools(names: Iterable[str], which: Callable[[str], Optional[str]] = shutil.which) -> None:
    missing = [name for name in names if which(name) is None]
    if missing:
        raise RunError("; ".join(missing_tool(name) for name in missing))


def effective_capabilities(status_path: str = "/proc/self/status") -> int:
    """The CapEff mask of this process, 0 when it cannot be read."""
    try:
        with open(status_path, "r", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("CapEff:"):
                    return int(line.split(":", 1)[1].strip(), 16)
    except (OSError, ValueError):
        pass
    return 0


def has_capabilities(mask: int, bits: Iterable[int]) -> bool:
    return all(mask & (1 << bit) for bit in bits)


def has_net_admin(euid: Callable[[], int] = os.geteuid,
                  capabilities: Callable[[], int] = effective_capabilities) -> bool:
    """True for root or a process holding CAP_NET_ADMIN and CAP_NET_RAW."""
    return euid() == 0 or has_capabilities(capabilities(), (CAP_NET_ADMIN, CAP_NET_RAW))


def require_net_admin(what: str, euid: Callable[[], int] = os.geteuid,
                      capabilities: Callable[[], int] = effective_capabilities) -> None:
    if not has_net_admin(euid, capabilities):
        raise RunError(NEED_NET_ADMIN % what)


def file_has_capabilities(path: str, getxattr: Callable[[str, str], bytes] = os.getxattr) -> bool:
    """True when the executable carries file capabilities (``setcap``)."""
    try:
        return bool(getxattr(path, "security.capability"))
    except OSError:
        return False


def can_capture(tshark: str, euid: Callable[[], int] = os.geteuid,
                capabilities: Callable[[], int] = effective_capabilities,
                getxattr: Callable[[str, str], bytes] = os.getxattr,
                access: Callable[[str, int], bool] = os.access) -> bool:
    """True when a live ``tshark`` capture can work for this user: root, the
    capabilities on the process, or a ``dumpcap`` next to ``tshark`` that has
    file capabilities and is executable by the user."""
    if has_net_admin(euid, capabilities):
        return True
    dumpcap = os.path.join(os.path.dirname(tshark), "dumpcap")
    return file_has_capabilities(dumpcap, getxattr) and access(dumpcap, os.X_OK)


def require_capture(tshark: str, **kwargs) -> None:
    if not can_capture(tshark, **kwargs):
        raise RunError(NEED_NET_ADMIN % "a live tshark capture")
