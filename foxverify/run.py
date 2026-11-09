"""One verify run: the shared command line, the fox's serial readback and the
on-air checks of each project.

``main(project)`` is what the four ``<project>/verify`` scripts call. The
command line is the same for all of them::

    ./verify [DEVICE ...] [--serial-only] [--no-reset] [--timeout 60]
             [--wait-for-fox 30] [-v]

A run keeps one ``Deadline`` on the monotonic clock from launch; every wait
below takes what is left of it. The steps are the same for every project:

1. Read ``src/current_conf.h`` and classify the devices (``devices``).
2. Check the tools and privileges the sniffer needs, before the fox is
   touched, so a missing tool exits 2 without a reset.
3. For Classic and iBeacon start the inquiry or scan, with every ``MAC_ADDR``
   in the header as a candidate; the fox is only on the air for a short
   window per wake and the first one must not be missed.
4. Reset the fox and read its banner and readback lines (``serial_fox``).
5. Pick the header block the banner names. A serial MAC that differs from
   the block's MAC means the fox was built from another header: that row
   FAILs and nothing else is checked.
6. The on-air rows for the project, then the rows the air does not decide
   (PSK, MAX_CLIENTS, TXPOWER with the median RSSI heard, EXT_PAN_ID) and
   the two timers: measured on the air when ``--timeout`` covers one cycle
   plus the boot allowance (``cycle``), ``serial only`` with a note naming
   the ``--timeout`` that would measure them otherwise.
7. The table, the ``first transmission`` line, the notes and the summary;
   exit 0, 1 on any FAIL, 2 when the run could not happen.

Without a sniffer, or with ``--serial-only``, the on-air rows are
``unverified`` with that reason and a note says so.

``--transcript FILE`` (hidden) or ``FOXVERIFY_TRANSCRIPT=FILE`` replays a
recorded transcript instead of a serial port: the run is serial-only and the
deadline runs on a clock the replay advances, so a run never waits. The
end-to-end tests use it; so can anyone with a saved transcript and no fox.
``--header FILE`` (hidden) checks against another header than
``src/current_conf.h``.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from typing import Callable, List, Optional, TextIO

from . import conf, cycle, devices, privileges, serial_fox
from .conf import Block, ConfError
from .report import Deadline, Report, RunError
from .serial_fox import PROJECT_DIRS, Readback

# The frame granularity of each radio in seconds: the longest normal spacing
# between two frames from the fox, which bounds how late the last frame of a
# wake can be heard after the radio stopped. Wi-Fi AP beacons come every
# 102.4 ms and iBeacon advertisements every 20-40 ms; Classic inquiry
# responses come every 1-3 s while the host inquires. A Wi-Fi client's probe
# bursts are spaced as the station chooses, so their granularity is observed
# (None), and a Zigbee fox's is its PACKET_INTERVAL.
GRANULARITY = {"classic_discoverable": 3.0, "iBeacon": 1.0, "AP": 1.0, "CLIENT": None}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSCRIPT_ENV = "FOXVERIFY_TRANSCRIPT"
DEFAULT_TIMEOUT = 60.0
DEFAULT_WAIT_FOR_FOX = 30.0
SERIAL_ONLY = "serial-only run"
INTERRUPTED = 130
# Seconds a run waits for a stopped inquiry or scan thread to end, so btmgmt
# is terminated and the BLE scanner stopped before the script exits.
STOP_SECONDS = 3.0

DESCRIPTION = {
    "classic_discoverable": "Verify a Bluetooth Classic fox: its serial readback against "
                            "src/current_conf.h, then its name and address on the air with a "
                            "btmgmt inquiry on hciN.",
    "iBeacon": "Verify an iBeacon fox: its serial readback against src/current_conf.h, then "
               "its address, UUID, major, minor, signal power and name on the air with an "
               "active BLE scan on hciN.",
    "wifi_ap_client": "Verify a Wi-Fi fox: its serial readback against src/current_conf.h, then "
                      "its beacons (AP) or probe requests (client) on the air with tshark on a "
                      "monitor mode interface such as wlan1.",
    "zigbee_coordinator": "Verify a Zigbee fox: its serial readback against src/current_conf.h, "
                          "then its Link Status frames on the air with an nRF52840 sniffer and "
                          "tshark.",
}

EPILOG = """\
DEVICE is a plain name: a network interface (wlan1), a Bluetooth adapter
(hci0) or a serial port (/dev/ttyACM1). A serial port with the nRF52840
sniffer's USB id is the 802.15.4 sniffer, any other serial port is the fox.
Without a fox the one ESP32 serial device is used; without a sniffer the
nRF sniffer or the only hciN adapter is used. A Wi-Fi interface is never
guessed. Exit 0 when nothing FAILed, 1 on any FAIL, 2 when the run could
not happen."""


def parse_args(project: str, argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="verify", description=DESCRIPTION.get(project),
                                     epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("devices", nargs="*", metavar="DEVICE",
                        help="the fox's serial port and the sniffer, in any order")
    parser.add_argument("--serial-only", action="store_true",
                        help="check the serial readback only and leave every radio alone")
    parser.add_argument("--no-reset", action="store_true",
                        help="do not reset the fox; wait for its own wake cycle instead")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, metavar="SECONDS",
                        help="hard limit for the whole run (default %d)" % DEFAULT_TIMEOUT)
    parser.add_argument("--wait-for-fox", type=float, default=DEFAULT_WAIT_FOR_FOX, metavar="SECONDS",
                        help="how long to wait for an ESP32 serial device to appear when none is "
                             "given, for a native USB board in deep sleep (default %d)"
                        % DEFAULT_WAIT_FOR_FOX)
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show every serial line, sniffer frame and command")
    parser.add_argument("--transcript", metavar="FILE", help=argparse.SUPPRESS)
    parser.add_argument("--header", metavar="FILE", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be more than 0 seconds")
    if args.wait_for_fox < 0:
        parser.error("--wait-for-fox must be 0 or more seconds")
    if args.transcript is None:
        args.transcript = os.environ.get(TRANSCRIPT_ENV) or None
    return args


def header_macs(text: str) -> List[str]:
    """Every MAC_ADDR in the header, one per block, for the scans that start
    before the banner has chosen the block."""
    macs: List[str] = []
    for values in conf.blocks(text).values():
        if "MAC_ADDR" not in values:
            continue
        try:
            mac = Block(values).mac("MAC_ADDR")
        except ConfError:
            continue
        if mac not in macs:
            macs.append(mac)
    return macs


class Run:
    """One run of one project's verify script. A subclass names the sniffer
    kind it wants autodetected and the on-air steps."""

    want_sniffer = False
    want_hci = False

    def __init__(self, project: str, args: argparse.Namespace, out: TextIO = sys.stdout):
        self.project = project
        self.args = args
        self.replay = args.transcript
        self.clock: Callable[[], float] = serial_fox.FakeClock() if self.replay else time.monotonic
        self.deadline = Deadline(args.timeout, self.clock)
        self.report = Report(self.deadline, out, args.verbose)
        self.header_path = args.header or os.path.join(REPO, PROJECT_DIRS[project], "src", "current_conf.h")
        self.serial_only = bool(args.serial_only or self.replay)
        self.air_reason = "--serial-only" if args.serial_only else SERIAL_ONLY
        self.source = None
        # The wall clock the sniffers stamp frames with, and the wait between
        # polls of a scan thread; a replay moves its own clock instead.
        self.wall: Callable[[], float] = self.clock if self.replay else time.time
        self.sleep: Callable[[float], None] = self.clock.advance if self.replay else time.sleep
        # Paths of the tools start_air found, for the project's rows.
        self.tshark: Optional[str] = None
        self.bluetoothctl: Optional[str] = None
        # The frames heard from the fox and the serial follower, set by plan()
        # when a sniffer listens; the reason the timer rows stay serial only.
        self.cycle: Optional[cycle.Cycle] = None
        self.follower: Optional[serial_fox.Follower] = None
        self.timer_reason = ""

    # The steps shared by every project.

    def run(self) -> int:
        header_text = self.load_header()
        selection = self.select_devices()
        air = None
        if not self.serial_only:
            air = self.start_air(selection, header_macs(header_text))
        try:
            readback = self.read_fox(selection)
            block = serial_fox.block_for(readback, self.project, header_text)
            listen = air
            if readback.halted():
                # The fox stopped its radio and sits on the fatal LED, so
                # there is nothing to hear.
                self.report.note("the fox refused to run: " + "; ".join(readback.problems))
                self.air_reason = "the fox halted"
                listen = None
            if not self.header_matches(block, readback):
                return self.report.emit()
            if listen is not None:
                self.plan(block, readback)
            self.rows(block, readback, listen)
            self.serial_rows(block, readback)
            if self.cycle is not None:
                self.report.line(cycle.first_transmission_line(self.cycle, self.args.no_reset))
        finally:
            self.stop_air(air)
            if self.source is not None:
                self.source.close()
        return self.report.emit()

    def plan(self, block: Block, readback: Readback) -> None:
        """Decide whether the sniffer listens through the first sleep to
        measure the timers: only when the fox was reset by this run and
        ``--timeout`` covers TIME_TO_WAKE + TIME_TO_SLEEP + BOOT_ALLOWANCE.
        Either way the frames heard feed the first transmission line and the
        median RSSI."""
        measure = False
        wake = block.integer("TIME_TO_WAKE") if "TIME_TO_WAKE" in block else None
        sleep = block.integer("TIME_TO_SLEEP") if "TIME_TO_SLEEP" in block else None
        if self.args.no_reset:
            self.timer_reason = "--no-reset"
        elif wake is not None and sleep is not None:
            if cycle.fits(wake, sleep, self.args.timeout):
                measure = True
            else:
                self.report.note(cycle.budget_note(wake, sleep, self.args.timeout))
        # A Bluetooth scan runs from before the reset; a Wi-Fi or Zigbee
        # capture starts after the readback has named the channel.
        listen_time = readback.reset_time if self.want_hci else None
        self.cycle = cycle.Cycle(readback.reset_time, self.granularity(block, readback), measure, wake,
                                 clock=self.wall, listen_time=listen_time, radio_time=readback.banner_time)
        if measure:
            self.follower = serial_fox.Follower(self.source, self.wall, self.random_channel(block, readback),
                                               self.report.debug)

    def granularity(self, block: Block, readback: Readback) -> Optional[float]:
        return GRANULARITY[self.project]

    def random_channel(self, block: Block, readback: Readback) -> bool:
        """True when the fox picks a channel at every wake, so wake 2 may be
        on another channel than wake 1."""
        return False

    def measuring(self) -> bool:
        return self.cycle is not None and self.cycle.measure

    def load_header(self) -> str:
        try:
            return conf.load(self.header_path)
        except OSError as error:
            raise RunError("cannot read %s: %s" % (self.header_path, error.strerror or error))

    def select_devices(self, **kwargs) -> Optional[devices.Selection]:
        """The devices of this run; ``kwargs`` reach ``devices.select`` so a
        caller can stand in for the serial ports and the device tree."""
        if self.replay:
            return None
        try:
            return devices.select(self.args.devices, self.args.wait_for_fox, self.deadline,
                                  want_sniffer=self.want_sniffer and not self.serial_only,
                                  want_hci=self.want_hci and not self.serial_only,
                                  say=self.report.say, **kwargs)
        except ImportError:
            raise RunError("pyserial is not installed (Debian/Ubuntu: python3-serial, "
                           "Arch: python-pyserial, Gentoo: dev-python/pyserial)")

    def read_fox(self, selection: Optional[devices.Selection]) -> Readback:
        if self.replay:
            self.report.say("replaying %s" % self.replay)
            try:
                self.source = serial_fox.TranscriptSource.from_file(self.replay, clock=self.clock)
            except OSError as error:
                raise RunError("cannot read %s: %s" % (self.replay, error.strerror or error))
        else:
            fox = selection.fox
            self.report.say("fox: %s" % fox.path)
            try:
                self.source = serial_fox.SerialSource(fox.path)
            except (OSError, ValueError) as error:
                raise RunError("cannot open %s: %s" % (fox.path, error))
        return serial_fox.read_fox(self.source, self.deadline, reset=not self.args.no_reset,
                                   say=self.report.say, debug=self.report.debug, wall=self.wall)

    def header_matches(self, block: Block, readback: Readback) -> bool:
        """True when the fox's address is the block's MAC_ADDR. Otherwise the
        MAC_ADDR row FAILs: a fox that halted on its own address check says
        so in its note, any other fox was built from a different header."""
        header_mac = block.mac("MAC_ADDR")
        serial_mac = readback.upper("address")
        if serial_fox.same_mac(header_mac, serial_mac):
            return True
        self.report.check("MAC_ADDR", header_mac, serial_mac, None)
        if not readback.halted():
            self.report.note(serial_fox.DIFFERENT_HEADER)
        return False

    def serial_row(self, block: Block, readback: Readback, name: str, field: str,
                   address: bool = False, reason: str = "", air: Optional[str] = None) -> None:
        """A row for a value only the serial readback can confirm. ``address``
        compares colon separated hex without regard to case; ``reason`` says
        why the air cannot, and ``air`` is shown without deciding anything."""
        if name not in block:
            return
        serial = readback.upper(field) if address else readback.get(field)
        self.report.check(name, block.display(name), serial, air, on_air=False, reason=reason)

    def timers(self, block: Block, readback: Readback) -> None:
        """The TIME_TO_WAKE and TIME_TO_SLEEP rows: measured on the air when
        the run listened through the first sleep, serial only otherwise."""
        if self.measuring():
            cycle.rows(self.report, block, readback, self.cycle, self.random_channel(block, readback))
            return
        self.serial_row(block, readback, "TIME_TO_WAKE", "time_to_wake", reason=self.timer_reason)
        self.serial_row(block, readback, "TIME_TO_SLEEP", "time_to_sleep", reason=self.timer_reason)

    def tx_power(self, block: Block, readback: Readback) -> None:
        """The TXPOWER row, with the median RSSI of the frames heard in its
        air column: a signal strength at an unknown distance does not confirm
        a transmit power, so the verdict stays serial only."""
        rssi = self.cycle.rssi_text() if self.cycle is not None else None
        self.serial_row(block, readback, "TXPOWER", "tx_power", air=rssi)

    def poll_scan(self, scan, mac: str, goal: Callable[[], bool]) -> None:
        """Wait for a scan thread to reach ``goal``, taking the frames it heard
        from the fox into the cycle, and on through the first sleep when the
        cycle is being measured. The thread is stopped afterwards and what it
        heard in the meantime taken too."""
        def read(timeout: float):
            self.sleep(timeout)
            return scan.take_heard(mac)

        cycle.listen(self.cycle, self.deadline, read, goal, self.follower, debug=self.report.debug)
        scan.stop()
        scan.join(STOP_SECONDS)
        if self.cycle is not None:
            for frame in scan.take_heard(mac):
                self.cycle.feed(frame)

    def no_sniffer(self, text: str) -> None:
        self.report.note(text + ", " + SERIAL_ONLY)

    def check_privileges(self, selection: devices.Selection) -> None:
        """What a run checks before it touches a radio: every tool the on-air
        step runs is installed and the privilege it needs is held."""
        what = self.check_tools(selection)
        if what is not None:
            privileges.require_net_admin(what)

    # The project specific steps.

    def check_tools(self, selection: devices.Selection,
                    which: Callable[[str], Optional[str]] = shutil.which) -> Optional[str]:
        """Check that the tools the on-air step runs with these devices are
        installed, raising ``RunError`` for a missing one, and return what
        needs root or CAP_NET_ADMIN, None when nothing does. ``verify``
        requires that privilege itself; ``flash_verify`` runs ``verify``
        through sudo for it. A run without a sniffer needs nothing."""
        return None

    def start_air(self, selection: devices.Selection, candidates: List[str]):
        """Check tools and privileges and start anything that must run before
        the reset. Returns the handle ``rows`` and ``stop_air`` get, None for
        a serial-only run."""
        raise NotImplementedError

    def stop_air(self, air) -> None:
        pass

    def rows(self, block: Block, readback: Readback, air) -> None:
        raise NotImplementedError

    def serial_rows(self, block: Block, readback: Readback) -> None:
        self.timers(block, readback)


class ClassicRun(Run):
    want_hci = True

    def check_tools(self, selection, which=shutil.which):
        if selection.hci is None:
            return None
        privileges.require_tools(["btmgmt"], which)
        return "btmgmt"

    def start_air(self, selection, candidates):
        from . import btclassic
        if selection.hci is None:
            self.no_sniffer("no Bluetooth adapter given and not exactly one found")
            return None
        self.check_privileges(selection)
        btmgmt = shutil.which("btmgmt")
        self.bluetoothctl = shutil.which("bluetoothctl")
        self.report.debug("inquiry on %s for %s" % (selection.hci.path, ", ".join(candidates)))
        scan = btclassic.Inquiry(selection.hci.path, self.deadline, btmgmt, debug=self.report.debug,
                                 clock=self.wall)
        scan.start()
        return scan

    def stop_air(self, scan) -> None:
        if scan is not None:
            scan.stop()
            scan.join(STOP_SECONDS)

    def rows(self, block, readback, scan):
        from . import btclassic
        if scan is None:
            btclassic.rows(self.report, block, readback, None, reason=self.air_reason)
            return
        mac = block.mac("MAC_ADDR")
        # Back to back inquiries are asked for before the target is named, so
        # the thread never ends its loop between the two.
        scan.keep_going = self.measuring()
        scan.set_target(mac)
        self.poll_scan(scan, mac, lambda: scan.named(mac) or not scan.is_alive())
        found = scan.result(self.deadline).get(mac)
        name = None
        if found is not None and found.name is None:
            name = btclassic.remote_name(mac, self.deadline, self.bluetoothctl, debug=self.report.debug)
        btclassic.rows(self.report, block, readback, found, name,
                       reason="no inquiry response from %s before the deadline" % mac)


class IBeaconRun(Run):
    want_hci = True

    def check_tools(self, selection, which=shutil.which):
        # bleak is the scanner here and the only thing the step can lack;
        # BlueZ over D-Bus needs no privilege.
        if selection.hci is not None:
            from . import ble
            ble.import_bleak()
        return None

    def start_air(self, selection, candidates):
        from . import ble
        if selection.hci is None:
            self.no_sniffer("no Bluetooth adapter given and not exactly one found")
            return None
        self.check_privileges(selection)
        self.report.debug("active scan on %s for %s" % (selection.hci.path, ", ".join(candidates)))
        scan = ble.BleScan(selection.hci.path, candidates, self.deadline, debug=self.report.debug,
                           clock=self.wall)
        scan.start()
        return scan

    def stop_air(self, scan) -> None:
        if scan is not None:
            scan.stop()
            scan.join(STOP_SECONDS)

    def rows(self, block, readback, scan):
        from . import ble
        if scan is None:
            ble.rows(self.report, block, readback, None, reason=self.air_reason)
            return
        mac = block.mac("MAC_ADDR")
        scan.keep_scanning = self.measuring()
        scan.set_target(mac)
        self.poll_scan(scan, mac, lambda: scan.complete(mac) or not scan.is_alive())
        seen = scan.result(self.deadline).get(mac)
        ble.rows(self.report, block, readback, seen,
                 reason="%s not seen by the scan before the deadline" % mac)

    def serial_rows(self, block, readback):
        self.timers(block, readback)
        self.tx_power(block, readback)


class WifiRun(Run):
    def check_tools(self, selection, which=shutil.which):
        if selection.wifi is None:
            return None
        privileges.require_tools(["ip", "iw", "tshark"], which)
        return "monitor mode"

    def start_air(self, selection, candidates):
        if selection.wifi is None:
            self.no_sniffer("no Wi-Fi interface given (name one, for example wlan1)")
            return None
        self.check_privileges(selection)
        self.tshark = shutil.which("tshark")
        return selection.wifi.path

    def granularity(self, block, readback):
        return GRANULARITY[readback.banner.mode]

    def random_channel(self, block, readback):
        # Only an AP picks a channel; a client probes on every channel and
        # its card hops anyway.
        return "CHANNEL" in block and block.integer("CHANNEL") == 0 and readback.banner.mode == "AP"

    def rows(self, block, readback, interface):
        from . import wifi
        mode = readback.banner.mode
        if interface is None:
            if mode == "AP":
                wifi.ap_rows(self.report, block, readback, None, self.air_reason)
            else:
                wifi.client_rows(self.report, block, readback, None, self.air_reason)
            return
        mac = block.mac("MAC_ADDR")
        if mode == "AP":
            channel = wifi.ap_channel(block, readback)
            if channel is None:
                wifi.ap_rows(self.report, block, readback, None, "the fox did not print its channel")
                return
            self.report.say("listening for beacons from %s on channel %d with %s%s" % (
                mac, channel, interface, " through the first sleep" if self.measuring() else ""))
            with wifi.monitor_mode(interface):
                beacon = wifi.observe_ap(interface, mac, channel, self.deadline, self.tshark,
                                         debug=self.report.debug, cycle=self.cycle, follower=self.follower,
                                         random_channel=self.random_channel(block, readback))
            wifi.ap_rows(self.report, block, readback, beacon,
                         "no beacon from %s on channel %d before the deadline" % (mac, channel))
        else:
            channels = wifi.probe_channels(block)
            self.report.say("listening for probe requests from %s on channel%s %s with %s%s" % (
                mac, "s" if len(channels) > 1 else "", ",".join(str(c) for c in channels), interface,
                " through the first sleep" if self.measuring() else ""))
            with wifi.monitor_mode(interface):
                probes = wifi.observe_client(interface, mac, block.string("FSSID"), channels,
                                             self.deadline, self.tshark, debug=self.report.debug,
                                             cycle=self.cycle, follower=self.follower)
            wifi.client_rows(self.report, block, readback, probes,
                             "no probe request from %s before the deadline" % mac)

    def serial_rows(self, block, readback):
        self.serial_row(block, readback, "PSK", "psk")
        self.serial_row(block, readback, "MAX_CLIENTS", "max_clients")
        self.timers(block, readback)
        self.tx_power(block, readback)


class ZigbeeRun(Run):
    want_sniffer = True

    def check_tools(self, selection, which=shutil.which):
        if selection.sniffer is None:
            return None
        privileges.require_tools(["tshark"], which)
        return None

    def start_air(self, selection, candidates):
        if selection.sniffer is None:
            self.no_sniffer("no nRF52840 sniffer given and not exactly one found")
            return None
        self.check_privileges(selection)
        self.tshark = shutil.which("tshark")
        return selection.sniffer.path

    def granularity(self, block, readback):
        return float(block.integer("PACKET_INTERVAL"))

    def random_channel(self, block, readback):
        return block.integer("CHANNEL") == 0

    def rows(self, block, readback, sniffer):
        from . import zigbee
        if sniffer is None:
            zigbee.rows(self.report, block, readback, None, reason=self.air_reason)
            return
        channel = readback.integer("channel")
        if channel is None:
            zigbee.rows(self.report, block, readback, None, reason="the fox did not print its channel")
            return
        pan_id = readback.integer("pan_id")
        interval = block.integer("PACKET_INTERVAL")
        interval_reason = zigbee.interval_fits(interval, self.deadline.remaining())
        want = 1 if interval_reason else 2
        self.report.say("listening on channel %d with %s for %s%s" % (
            channel, sniffer, "one Link Status frame" if want == 1 else "two Link Status frames",
            " and through the first sleep" if self.measuring() else ""))
        observation = zigbee.observe(sniffer, channel, self.deadline, self.tshark, pan_id, want,
                                     debug=self.report.debug, cycle=self.cycle, follower=self.follower,
                                     random_channel=self.random_channel(block, readback),
                                     mac=block.mac("MAC_ADDR"))
        zigbee.rows(self.report, block, readback, observation, interval_reason,
                    reason="no frame from a coordinator on channel %d before the deadline" % channel)

    def serial_rows(self, block, readback):
        from . import zigbee
        self.serial_row(block, readback, "EXT_PAN_ID", "ext_pan_id", address=True,
                        reason=zigbee.EXT_PAN_ID_REASON)
        self.timers(block, readback)
        self.tx_power(block, readback)


RUNS = {
    "classic_discoverable": ClassicRun,
    "iBeacon": IBeaconRun,
    "wifi_ap_client": WifiRun,
    "zigbee_coordinator": ZigbeeRun,
}


def main(project: str, argv: Optional[List[str]] = None, out: TextIO = sys.stdout,
         err: TextIO = sys.stderr) -> int:
    """Run the verify script of ``project``; the exit code is returned."""
    args = parse_args(project, argv)
    try:
        return RUNS[project](project, args, out).run()
    except RunError as error:
        out.flush()
        err.write("%s\n" % error)
        return error.exit_code
    except KeyboardInterrupt:
        out.flush()
        err.write("interrupted\n")
        return INTERRUPTED
