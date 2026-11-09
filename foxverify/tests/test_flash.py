"""flash_verify without a fox, a pio or a sudo: the environment list of every
project, the argument pass-through, the pio command line, the root refusal,
the sudo decision, the bootloader entry and its undo, the port after the
flash and a failed pio run. ``Machine`` stands in for the serial ports, the
tools on PATH, the user, every command the script would run and the
``serial.Serial`` the bootloader entry opens."""
import io
import os
import re
import tempfile
import unittest
from unittest import mock

import serial

from foxverify import ble, bootloader, devices, flash
from foxverify.report import EXIT_NO_RUN, RunError
from foxverify.serial_fox import PROJECT_DIRS, RESET_PULSE_SECONDS
from foxverify.tests import REPO
from foxverify.tests.test_devices import CP210X, ESP, NANO, NRF, OTHER, Info

NET_BITS = (1 << 12) | (1 << 13)
ALL_TOOLS = ("pio", "sudo", "btmgmt", "bluetoothctl", "tshark", "ip", "iw")
PIO_OUTPUT = (b"Processing m5atom-easy (platform: espressif32@~6.7.0; board: m5stack-atom)\r\n"
              b"Writing at 0x00010000... (10 %)\rWriting at 0x00014000... (20 %)\r\n"
              b"Hard resetting via RTS pin...\n"
              b"========= [SUCCESS] Took 42.00 seconds =========\n")
# What the ROM prints at 115200 after a reset into download mode, on an ESP32
# behind a UART bridge and on an ESP32-S3 through its USB-Serial-JTAG port,
# and what it prints when it boots the application instead.
ROM_ESP32 = (b"ets Jul 29 2019 12:21:46\r\n\r\nrst:0x1 (POWERON_RESET),boot:0x3 "
             b"(DOWNLOAD_BOOT(UART0/UART1/SDIO_REI_REO_V2))\r\nwaiting for download\r\n")
ROM_ESP32S3 = (b"ESP-ROM:esp32s3-20210327\r\nBuild:Mar 27 2021\r\nrst:0x1 (POWERON),boot:0x0 "
               b"(DOWNLOAD(USB/UART0))\r\nwaiting for download\r\n")
ROM_APP = b"ESP-ROM:esp32s3-20210327\r\nBuild:Mar 27 2021\r\nrst:0x1 (POWERON),boot:0x8 (SPI_FAST_FLASH_BOOT)\r\n"
# esptool's sequences as a port sees them, from esptool/reset.py: every DTR and
# RTS write in order, with the DTR rewrite after each RTS write, and the sleeps
# between them. The port is open with both lines asserted when they start.
CLASSIC_RESET = [("dtr", False), ("rts", True), ("dtr", False), ("sleep", 0.1),
                 ("dtr", True), ("rts", False), ("dtr", True), ("sleep", 0.05),
                 ("dtr", False)]
USB_JTAG_RESET = [("rts", False), ("dtr", True), ("dtr", False), ("sleep", 0.1),
                  ("dtr", True), ("rts", False), ("dtr", True), ("sleep", 0.1),
                  ("rts", True), ("dtr", True), ("dtr", False), ("rts", True), ("dtr", False), ("sleep", 0.1),
                  ("dtr", False), ("rts", False), ("dtr", False)]
HARD_RESET = [("dtr", False), ("rts", True), ("sleep", RESET_PULSE_SECONDS), ("rts", False),
              ("sleep", RESET_PULSE_SECONDS), ("dtr", True), ("rts", True)]


class FakeSerial:
    """What ``serial.Serial`` gives the bootloader entry and the hard reset: a
    port that records every line-state write, open and close in the machine's
    ``lines`` log, answers reads with the ROM output the test canned and moves
    the clock on when there is none."""

    machine = None

    def __init__(self):
        self.port = None
        self.baudrate = None
        self.timeout = None
        self._dtr = None
        self._rts = None
        self.data = b""
        self.fail_read = False

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, value):
        self._dtr = value
        self.machine.lines.append(("dtr", value))

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, value):
        self._rts = value
        self.machine.lines.append(("rts", value))

    def open(self):
        machine = self.machine
        if self.port not in {port.device for port in machine.ports} or self.port in machine.unopenable:
            raise serial.SerialException("could not open port %s" % self.port)
        machine.lines.append(("open", self.port))
        machine.timeline.append(("serial", self.port))
        machine.opens += 1
        self.data = machine.rom
        self.fail_read = machine.read_fails_once and machine.opens == 1

    def close(self):
        self.machine.lines.append(("close", self.port))

    @property
    def in_waiting(self):
        return len(self.data)

    def read(self, size=1):
        if self.fail_read:
            self.fail_read = False
            raise serial.SerialException("device reports readiness to read but returned no data")
        if not self.data:
            self.machine.now += self.timeout
            return b""
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


class FakeProcess:
    """What ``Popen`` gives ``stream``: the output, then the exit status."""

    def __init__(self, output, status):
        self.stdout = io.BytesIO(output)
        self.status = status

    def wait(self):
        return self.status

    def kill(self):
        pass


class Machine:
    """The serial ports, the tools, the user and the commands of one test.
    ``after_flash`` runs when pio is started, so a test can make the fox's
    port disappear or come back under another name."""

    def __init__(self, ports=(), tools=ALL_TOOLS, euid=1000, capabilities=0,
                 pio_output=PIO_OUTPUT, pio_status=0, sudo_status=0, verify_status=0,
                 interfaces=(), after_flash=None, rom=ROM_ESP32, unopenable=(), read_fails_once=False):
        self.dev = tempfile.mkdtemp(prefix="foxverify-flash-")
        self.ports = [self.port(*spec) for spec in ports]
        self.tools = set(tools)
        self.euid = euid
        self.capabilities = capabilities
        self.pio_output = pio_output
        self.pio_status = pio_status
        self.sudo_status = sudo_status
        self.verify_status = verify_status
        self.interfaces = set(interfaces)
        self.after_flash = after_flash
        self.rom = rom
        self.unopenable = set(unopenable)
        self.read_fails_once = read_fails_once
        self.events = []
        self.timeline = []
        self.lines = []
        self.opens = 0
        self.slept = []
        self.now = 1000.0

    def cleanup(self):
        for name in os.listdir(self.dev):
            os.remove(os.path.join(self.dev, name))
        os.rmdir(self.dev)

    def port(self, name, vid, pid, product, serial_number):
        return Info(os.path.join(self.dev, name), vid, pid, product, serial_number)

    def serial_class(self):
        """A ``serial.Serial`` stand-in bound to this machine."""
        class Serial(FakeSerial):
            machine = self
        return Serial

    def sessions(self):
        """The line-state writes and sleeps of each port session, open to close."""
        sessions = []
        current = None
        for entry in self.lines:
            if entry[0] == "open":
                current = []
            elif entry[0] == "close":
                sessions.append(current)
                current = None
            elif current is not None:
                current.append(entry)
        return sessions

    def which(self, name):
        return "/usr/bin/" + name if name in self.tools else None

    def comports(self):
        return list(self.ports)

    def exists(self, path):
        if path in {port.device for port in self.ports}:
            return True
        return os.path.basename(path) in self.interfaces and path.startswith(devices.NET_DIR + "/")

    def call(self, argv):
        self.events.append(("call", list(argv)))
        self.timeline.append(("call", list(argv)))
        if argv[1:] == ["-v"]:
            return self.sudo_status
        return self.verify_status

    def popen(self, argv, **kwargs):
        self.events.append(("popen", list(argv)))
        self.timeline.append(("popen", list(argv)))
        if self.after_flash is not None:
            self.after_flash(self)
        return FakeProcess(self.pio_output, self.pio_status)

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.lines.append(("sleep", seconds))
        self.now += seconds

    def clock(self):
        return self.now

    def stand_ins(self):
        return dict(which=self.which, euid=lambda: self.euid, capabilities=lambda: self.capabilities,
                    comports=self.comports, exists=self.exists, call=self.call, popen=self.popen,
                    sleep=self.sleep, clock=self.clock)

    def commands(self, kind):
        return [argv for what, argv in self.events if what == kind]


def ini_environments(project):
    """The ``[env:...]`` names of a project's platformio.ini, read without flash.py."""
    with open(os.path.join(REPO, PROJECT_DIRS[project], "platformio.ini"), "r", encoding="utf-8") as handle:
        return re.findall(r"^\[env:(.+)\]$", handle.read(), re.MULTILINE)


def verify_path(project):
    return os.path.join(REPO, PROJECT_DIRS[project], "verify")


class FlashTestCase(unittest.TestCase):
    def machine(self, **kwargs):
        machine = Machine(**kwargs)
        self.addCleanup(machine.cleanup)
        return machine

    def run_flash(self, project, argv, machine):
        out = io.StringIO()
        err = io.StringIO()
        with mock.patch("serial.Serial", machine.serial_class()):
            code = flash.main(project, argv, out, err, **machine.stand_ins())
        return code, out.getvalue(), err.getvalue()


class EnvironmentTest(FlashTestCase):
    def test_every_environment_of_every_project_is_accepted(self):
        for project, project_dir in PROJECT_DIRS.items():
            names = ini_environments(project)
            self.assertTrue(names, project)
            self.assertEqual(flash.environments(os.path.join(REPO, project_dir, "platformio.ini")), names)
            for name in names:
                flash.check_environment(os.path.join(REPO, project_dir), name)
        self.assertIn("m5atom-easy", ini_environments("iBeacon"))
        self.assertIn("seeed-xiao-esp32c5-hard-coordinator", ini_environments("zigbee_coordinator"))

    def test_unknown_environment_lists_the_project_s_environments(self):
        with self.assertRaises(RunError) as caught:
            flash.check_environment(os.path.join(REPO, PROJECT_DIRS["wifi_ap_client"]), "nonsense")
        text = str(caught.exception)
        self.assertEqual(caught.exception.exit_code, EXIT_NO_RUN)
        self.assertIn("nonsense is not an environment of wifi/wifi_ap_client", text)
        for name in ini_environments("wifi_ap_client"):
            self.assertIn("\n  " + name, text)

    def test_unknown_environment_exits_2_before_anything_runs(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X])
        code, out, err = self.run_flash("iBeacon", ["nonsense", "--serial-only"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn("nonsense is not an environment of bluetooth/iBeacon", err)
        self.assertIn("\n  m5atom-easy\n", err)
        self.assertEqual(machine.events, [])

    def test_missing_pio_exits_2_with_the_install_pointer(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], tools=("sudo",))
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(err.strip(), flash.NO_PIO)
        self.assertIn("pip install -U platformio", err)
        self.assertEqual(machine.events, [])


class ArgumentTest(FlashTestCase):
    def test_pass_through_keeps_the_order_and_adds_the_port(self):
        self.assertEqual(flash.verify_argv(["wlan1", "--timeout", "20", "-v"], ["wlan1"], "/dev/fox"),
                         ["/dev/fox", "wlan1", "--timeout", "20", "-v"])
        self.assertEqual(flash.verify_argv(["--serial-only", "wlan1", "-v"], ["wlan1"], "/dev/fox"),
                         ["--serial-only", "/dev/fox", "wlan1", "-v"])
        self.assertEqual(flash.verify_argv(["--no-reset", "-v"], [], "/dev/fox"),
                         ["--no-reset", "-v", "/dev/fox"])
        self.assertEqual(flash.verify_argv([], [], "/dev/fox"), ["/dev/fox"])
        self.assertEqual(flash.verify_argv(["/dev/fox", "wlan1", "-v"], ["/dev/fox", "wlan1"], None),
                         ["/dev/fox", "wlan1", "-v"])

    def test_pio_command_line(self):
        self.assertEqual(flash.pio_argv("/usr/bin/pio", "/repo/wifi/wifi_ap_client", "m5atom-easy-ap", "/dev/fox"),
                         ["/usr/bin/pio", "run", "--project-dir", "/repo/wifi/wifi_ap_client",
                          "-e", "m5atom-easy-ap", "-t", "upload", "--upload-port", "/dev/fox"])

    def test_every_argument_reaches_verify_after_the_flash(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], interfaces=["wlan1"])
        fox = machine.ports[0].device
        code, out, err = self.run_flash(
            "wifi_ap_client", ["m5atom-easy-ap", "wlan1", "--timeout", "20", "--wait-for-fox", "5", "-v"],
            machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        project_dir = os.path.join(REPO, "wifi/wifi_ap_client")
        self.assertEqual(machine.events, [
            ("call", ["/usr/bin/sudo", "-v"]),
            ("popen", flash.pio_argv("/usr/bin/pio", project_dir, "m5atom-easy-ap", fox)),
            ("call", ["/usr/bin/sudo", verify_path("wifi_ap_client"), fox, "wlan1",
                      "--timeout", "20", "--wait-for-fox", "5", "-v"]),
        ])
        self.assertIn("project wifi/wifi_ap_client, environment m5atom-easy-ap, conference %s\n"
                      % flash.conference(project_dir), out)
        self.assertIn("fox on %s; verify runs through sudo for monitor mode\n" % fox, out)
        self.assertIn("Hard resetting via RTS pin...", out)

    def test_verify_s_exit_code_is_the_script_s(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], verify_status=1)
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only"], machine)
        self.assertEqual(code, 1)
        self.assertEqual(machine.commands("call")[-1],
                         [verify_path("iBeacon"), "--serial-only", machine.ports[0].device])

    def test_bad_verify_option_fails_before_the_build(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X])
        with mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                self.run_flash("iBeacon", ["m5atom-easy", "--bogus"], machine)
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(machine.events, [])

    def test_conference_is_the_target_of_the_link(self):
        project_dir = os.path.join(REPO, PROJECT_DIRS["zigbee_coordinator"])
        self.assertEqual(flash.conference(project_dir), os.readlink(os.path.join(project_dir, "src", "current_conf.h")))
        self.assertTrue(flash.conference(project_dir).startswith("conferences/"))


class RootTest(FlashTestCase):
    def test_root_is_refused_before_anything_runs(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], euid=0)
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(err.strip(), flash.ROOT_REFUSED)
        self.assertIn("Run it as yourself", err)
        self.assertEqual(out, "")
        self.assertEqual(machine.events, [])


class SudoTest(FlashTestCase):
    def test_classic_with_an_adapter_needs_root(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X])
        fox = machine.ports[0].device
        code, out, err = self.run_flash("classic_discoverable", ["m5atom-hard", "hci0"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual([what for what, argv in machine.events], ["call", "popen", "call"])
        self.assertEqual(machine.events[0], ("call", ["/usr/bin/sudo", "-v"]))
        self.assertEqual(machine.events[2],
                         ("call", ["/usr/bin/sudo", verify_path("classic_discoverable"), fox, "hci0"]))
        self.assertIn("verify runs through sudo for btmgmt", out)

    def test_capabilities_make_sudo_unnecessary(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], capabilities=NET_BITS)
        code, out, err = self.run_flash("classic_discoverable", ["m5atom-hard", "hci0"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.commands("call"),
                         [[verify_path("classic_discoverable"), machine.ports[0].device, "hci0"]])
        self.assertNotIn("sudo", out)

    def test_zigbee_needs_tshark_but_no_root(self):
        machine = self.machine(ports=[("ttyACM0",) + ESP, ("ttyACM1",) + NRF])
        fox = machine.ports[0].device
        code, out, err = self.run_flash("zigbee_coordinator", ["seeed-xiao-esp32c5-easy-coordinator"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.commands("call"), [[verify_path("zigbee_coordinator"), fox]])
        self.assertNotIn("sudo", out)
        machine = self.machine(ports=[("ttyACM0",) + ESP, ("ttyACM1",) + NRF], tools=("pio", "sudo"))
        code, out, err = self.run_flash("zigbee_coordinator", ["seeed-xiao-esp32c5-easy-coordinator"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn("tshark is not installed", err)
        self.assertEqual(machine.events, [])

    def test_ibeacon_needs_no_root(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X])
        with mock.patch.object(ble, "import_bleak", lambda: None):
            code, out, err = self.run_flash("iBeacon", ["m5atom-medium", "hci0"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.commands("call"), [[verify_path("iBeacon"), machine.ports[0].device, "hci0"]])
        self.assertNotIn("sudo", out)

    def test_missing_bleak_fails_before_the_build(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X])
        with mock.patch.object(ble, "import_bleak", side_effect=RunError(ble.BLEAK_MISSING)):
            code, out, err = self.run_flash("iBeacon", ["m5atom-medium", "hci0"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn("bleak is not installed", err)
        self.assertEqual(machine.events, [])

    def test_serial_only_needs_neither_tools_nor_root(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], tools=("pio",))
        code, out, err = self.run_flash("classic_discoverable", ["m5atom-easy", "hci0", "--serial-only"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.commands("call"),
                         [[verify_path("classic_discoverable"), machine.ports[0].device, "hci0", "--serial-only"]])

    def test_missing_tool_fails_before_the_build(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], tools=("pio", "sudo", "ip", "iw"),
                               interfaces=["wlan1"])
        code, out, err = self.run_flash("wifi_ap_client", ["m5atom-easy-ap", "wlan1"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn("tshark is not installed", err)
        self.assertEqual(machine.events, [])

    def test_failed_sudo_stops_before_the_build(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], sudo_status=1)
        code, out, err = self.run_flash("classic_discoverable", ["m5atom-hard", "hci0"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(err.strip(), flash.SUDO_FAILED % "btmgmt")
        self.assertEqual(machine.events, [("call", ["/usr/bin/sudo", "-v"])])

    def test_missing_sudo_is_said(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], tools=("pio", "btmgmt"))
        code, out, err = self.run_flash("classic_discoverable", ["m5atom-hard", "hci0"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(err.strip(), flash.NO_SUDO % "btmgmt")
        self.assertEqual(machine.events, [])


class PortTest(FlashTestCase):
    def test_autodetected_port_that_survives_the_flash_is_passed_on(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X])
        fox = machine.ports[0].device
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.commands("popen")[0][-1], fox)
        self.assertEqual(machine.commands("call"), [[verify_path("iBeacon"), "--serial-only", fox]])
        self.assertEqual(machine.slept[-1], flash.SETTLE_SECONDS)
        self.assertEqual(machine.slept.count(flash.SETTLE_SECONDS), 1)
        self.assertNotIn("is gone after the flash", out)

    def test_port_gone_after_the_flash_is_found_again(self):
        def re_enumerate(machine):
            machine.ports = [machine.port("ttyACM3", 0x303A, 0x0002, "Espressif Device", "F4:12:FA:00:11:22")]

        machine = self.machine(ports=[("ttyACM0",) + ESP], after_flash=re_enumerate)
        before = os.path.join(machine.dev, "ttyACM0")
        after = os.path.join(machine.dev, "ttyACM3")
        code, out, err = self.run_flash("iBeacon", ["m5atoms3-easy", "--serial-only", "--wait-for-fox", "10"],
                                        machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.commands("popen")[0][-1], before)
        self.assertEqual(machine.commands("call"),
                         [[verify_path("iBeacon"), "--serial-only", "--wait-for-fox", "10", after]])
        self.assertIn("%s is gone after the flash; looking for the fox again" % before, out)

    def test_port_that_takes_time_to_come_back_is_waited_for(self):
        def re_enumerate(machine):
            machine.ports = []
            machine.returns_at = machine.now + 4.0

        machine = self.machine(ports=[("ttyACM0",) + ESP], after_flash=re_enumerate)
        after = machine.port("ttyACM3", *ESP)

        def comports():
            if getattr(machine, "returns_at", None) is not None and machine.now >= machine.returns_at:
                machine.ports = [after]
            return list(machine.ports)

        machine.comports = comports
        code, out, err = self.run_flash("iBeacon", ["m5atoms3-easy", "--serial-only", "--wait-for-fox", "10"],
                                        machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.commands("call")[0][-1], after.device)
        self.assertIn("waiting up to", out)
        self.assertGreaterEqual(machine.now, machine.returns_at)
        self.assertGreater(machine.now, 1000.0 + flash.SETTLE_SECONDS)

    def test_port_that_never_comes_back_exits_2(self):
        machine = self.machine(ports=[("ttyACM0",) + ESP],
                               after_flash=lambda machine: setattr(machine, "ports", []))
        code, out, err = self.run_flash("iBeacon", ["m5atoms3-easy", "--serial-only", "--wait-for-fox", "3"],
                                        machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(err.strip(), devices.NO_FOX)
        self.assertEqual(machine.commands("call"), [])

    def test_fox_the_user_named_is_passed_on_as_given(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X, ("ttyUSB1",) + CP210X],
                               after_flash=lambda machine: setattr(machine, "ports", []))
        fox = machine.ports[1].device
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "-v", fox, "--serial-only"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.commands("popen")[0][-1], fox)
        self.assertEqual(machine.commands("call"), [[verify_path("iBeacon"), "-v", fox, "--serial-only"]])
        self.assertNotIn(flash.SETTLE_SECONDS, machine.slept)
        self.assertNotIn("is gone", out)

    def test_no_fox_exits_2_before_the_build(self):
        machine = self.machine()
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only", "--wait-for-fox", "0"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(err.strip(), devices.NO_FOX)
        self.assertEqual(machine.events, [])

    def test_several_foxes_exit_2_before_the_build(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X, ("ttyACM0",) + ESP])
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn("2 ESP32 serial devices found", err)
        self.assertEqual(machine.events, [])

    def test_transcript_cannot_be_flashed(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X])
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--transcript", "/dev/null"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(err.strip(), flash.NOTHING_TO_FLASH)
        self.assertEqual(machine.events, [])


class BootloaderTest(FlashTestCase):
    """The fox is put into the ROM bootloader as soon as its port is known, with
    esptool's sequence for its USB stack, and is reset back into its
    application when the upload never happens."""

    def test_uart_bridge_gets_esptool_s_classic_reset_and_is_confirmed(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], rom=ROM_ESP32)
        fox = machine.ports[0].device
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.sessions(), [CLASSIC_RESET])
        self.assertEqual(machine.lines[:3], [("dtr", True), ("rts", True), ("open", fox)])
        self.assertIn(bootloader.IN_BOOTLOADER % fox + "\n", out)
        self.assertNotIn(bootloader.NOT_CONFIRMED, out)
        self.assertNotIn(bootloader.RELEASED % fox, out)
        self.assertEqual(machine.timeline[0], ("serial", fox))

    def test_usb_serial_jtag_gets_esptool_s_usb_jtag_reset(self):
        machine = self.machine(ports=[("ttyACM0",) + ESP], rom=ROM_ESP32S3)
        fox = machine.ports[0].device
        code, out, err = self.run_flash("iBeacon", ["m5atoms3-easy", "--serial-only"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual(machine.sessions(), [USB_JTAG_RESET])
        self.assertIn(bootloader.IN_BOOTLOADER % fox + "\n", out)
        self.assertEqual(machine.commands("popen")[0][-1], fox)

    def test_confirmation_requires_waiting_for_download(self):
        machine = self.machine(ports=[("ttyACM0",) + ESP], rom=ROM_APP)
        code, out, err = self.run_flash("iBeacon", ["m5atoms3-easy", "--serial-only"], machine)
        self.assertEqual(code, 0, err)
        self.assertIn(bootloader.NOT_CONFIRMED + "\n", out)
        self.assertNotIn("in the bootloader", out)
        self.assertEqual(len(machine.commands("popen")), 1)
        self.assertEqual(machine.sessions()[0], USB_JTAG_RESET)
        self.assertGreaterEqual(machine.now, 1000.0 + bootloader.CONFIRM_SECONDS)

    def test_fox_that_drops_off_the_bus_is_opened_again_and_read_on(self):
        machine = self.machine(ports=[("ttyACM0",) + ESP], rom=ROM_ESP32S3, read_fails_once=True)
        fox = machine.ports[0].device
        with open(fox, "w"):
            pass
        code, out, err = self.run_flash("iBeacon", ["m5atoms3-easy", "--serial-only"], machine)
        self.assertEqual(code, 0, err)
        self.assertIn(bootloader.IN_BOOTLOADER % fox + "\n", out)
        self.assertEqual(machine.opens, 2)
        self.assertEqual(machine.sessions(), [USB_JTAG_RESET, []])

    def test_port_that_cannot_be_opened_falls_back_and_is_not_held(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], pio_status=1)
        fox = machine.ports[0].device
        machine.unopenable.add(fox)
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn(bootloader.NOT_CONFIRMED + "\n", out)
        self.assertEqual(machine.sessions(), [])
        self.assertNotIn(bootloader.RELEASED % fox, out)
        self.assertNotIn(bootloader.NOT_RELEASED % fox, out)
        self.assertEqual(len(machine.commands("popen")), 1)

    def test_entry_happens_before_sudo_and_before_pio(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], interfaces=["wlan1"])
        fox = machine.ports[0].device
        code, out, err = self.run_flash("wifi_ap_client", ["m5atom-easy-ap", "wlan1"], machine)
        self.assertEqual(code, 0, err)
        self.assertEqual([what for what, detail in machine.timeline], ["serial", "call", "popen", "call"])
        self.assertEqual(machine.timeline[1], ("call", ["/usr/bin/sudo", "-v"]))
        self.assertLess(out.index(bootloader.IN_BOOTLOADER % fox), out.index("project wifi/wifi_ap_client"))

    def test_failed_build_resets_the_fox_into_its_application(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], pio_status=1)
        fox = machine.ports[0].device
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(machine.sessions(), [CLASSIC_RESET, HARD_RESET])
        self.assertIn(bootloader.RELEASED % fox + "\n", out)
        self.assertEqual(machine.commands("call"), [])

    def test_failed_check_and_failed_sudo_reset_the_fox(self):
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], tools=("pio", "sudo", "ip", "iw"),
                               interfaces=["wlan1"])
        fox = machine.ports[0].device
        code, out, err = self.run_flash("wifi_ap_client", ["m5atom-easy-ap", "wlan1"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn("tshark is not installed", err)
        self.assertEqual(machine.sessions(), [CLASSIC_RESET, HARD_RESET])
        self.assertIn(bootloader.RELEASED % fox + "\n", out)
        self.assertEqual(machine.events, [])
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], sudo_status=1)
        code, out, err = self.run_flash("classic_discoverable", ["m5atom-hard", "hci0"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(machine.sessions(), [CLASSIC_RESET, HARD_RESET])
        self.assertEqual(machine.events, [("call", ["/usr/bin/sudo", "-v"])])

    def test_ctrl_c_during_the_build_resets_the_fox(self):
        def interrupt(machine):
            raise KeyboardInterrupt

        machine = self.machine(ports=[("ttyACM0",) + ESP], rom=ROM_ESP32S3, after_flash=interrupt)
        fox = machine.ports[0].device
        code, out, err = self.run_flash("iBeacon", ["m5atoms3-easy", "--serial-only"], machine)
        self.assertEqual(code, 130)
        self.assertEqual(err.strip(), "interrupted")
        self.assertEqual(machine.sessions(), [USB_JTAG_RESET, HARD_RESET])
        self.assertIn(bootloader.RELEASED % fox + "\n", out)

    def test_fox_gone_at_the_reset_is_said(self):
        def unplug(machine):
            machine.unopenable.add(machine.ports[0].device)

        machine = self.machine(ports=[("ttyUSB0",) + CP210X], pio_status=1, after_flash=unplug)
        fox = machine.ports[0].device
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertEqual(machine.sessions(), [CLASSIC_RESET])
        self.assertIn(bootloader.NOT_RELEASED % fox + "\n", out)

    def test_unknown_usb_id_is_skipped_with_the_reason(self):
        machine = self.machine(ports=[("ttyUSB1",) + OTHER, ("ttyS0", None, None, None, None)], pio_status=1)
        fox = machine.ports[0].device
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", fox, "--serial-only"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn(bootloader.UNKNOWN_SKIPPED % (fox, "USB id 1234:5678") + "\n", out)
        self.assertEqual(machine.sessions(), [])
        self.assertNotIn(bootloader.RELEASED % fox, out)
        self.assertEqual(len(machine.commands("popen")), 1)
        bare = machine.ports[1].device
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", bare, "--serial-only"], machine)
        self.assertIn(bootloader.UNKNOWN_SKIPPED % (bare, "no USB id") + "\n", out)
        self.assertEqual(machine.sessions(), [])

    def test_nano_is_flashed_the_old_way(self):
        """dfu-util flashes the Nano through its running application, so there is
        nothing to hold; the Arduino id still finds the fox."""
        machine = self.machine(ports=[("ttyACM0",) + NANO], pio_status=1)
        fox = machine.ports[0].device
        code, out, err = self.run_flash("iBeacon", ["arduino-nano-esp32-easy", "--serial-only"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn(bootloader.NANO_SKIPPED % fox + "\n", out)
        self.assertEqual(machine.sessions(), [])
        self.assertNotIn(bootloader.RELEASED % fox, out)
        self.assertEqual(machine.commands("popen")[0][-1], fox)

    def test_usb_stack_by_id(self):
        self.assertEqual(bootloader.usb_stack(devices.Port("/dev/a", *CP210X)), bootloader.UART_BRIDGE)
        self.assertEqual(bootloader.usb_stack(devices.Port("/dev/a", 0x1A86, 0x55D4, None, None)),
                         bootloader.UART_BRIDGE)
        self.assertEqual(bootloader.usb_stack(devices.Port("/dev/a", 0x0403, 0x6001, None, None)),
                         bootloader.UART_BRIDGE)
        self.assertEqual(bootloader.usb_stack(devices.Port("/dev/a", *ESP)), bootloader.USB_SERIAL_JTAG)
        self.assertEqual(bootloader.usb_stack(devices.Port("/dev/a", *NANO)), bootloader.TINYUSB)
        self.assertIsNone(bootloader.usb_stack(devices.Port("/dev/a", 0x303A, 0x0002, None, None)))
        self.assertIsNone(bootloader.usb_stack(devices.Port("/dev/a", *OTHER)))
        self.assertIsNone(bootloader.usb_stack(devices.Port("/dev/a", None, None, None, None)))
        self.assertIsNone(bootloader.usb_stack(None))


class PioTest(FlashTestCase):
    def test_failed_pio_exits_2_with_its_last_lines(self):
        output = b"".join(b"line %d\n" % n for n in range(1, 31)) + b"*** [upload] Error 2\n"
        machine = self.machine(ports=[("ttyUSB0",) + CP210X], pio_output=output, pio_status=1)
        code, out, err = self.run_flash("iBeacon", ["m5atom-easy", "--serial-only"], machine)
        self.assertEqual(code, EXIT_NO_RUN)
        self.assertIn("pio run exited with status 1; its last lines:", err)
        self.assertIn("\n  *** [upload] Error 2", err)
        self.assertIn("\n  line 17\n", err)
        self.assertNotIn("line 16", err)
        self.assertIn("line 1\n", out)
        self.assertIn("*** [upload] Error 2\n", out)
        self.assertEqual(machine.commands("call"), [])

    def test_stream_copies_the_output_and_splits_the_tail_on_every_line_end(self):
        def popen(argv, **kwargs):
            return FakeProcess(PIO_OUTPUT, 3)

        out = io.StringIO()
        status, tail = flash.stream(["pio"], out, popen)
        self.assertEqual(status, 3)
        self.assertEqual(out.getvalue(), PIO_OUTPUT.decode("utf-8"))
        self.assertEqual(tail, ["Processing m5atom-easy (platform: espressif32@~6.7.0; board: m5stack-atom)",
                                "Writing at 0x00010000... (10 %)", "Writing at 0x00014000... (20 %)",
                                "Hard resetting via RTS pin...",
                                "========= [SUCCESS] Took 42.00 seconds ========="])


if __name__ == "__main__":
    unittest.main()
