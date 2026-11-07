"""flash_verify without a fox, a pio or a sudo: the environment list of every
project, the argument pass-through, the pio command line, the root refusal,
the sudo decision, the port after the flash and a failed pio run. ``Machine``
stands in for the serial ports, the tools on PATH, the user and every command
the script would run."""
import io
import os
import re
import tempfile
import unittest
from unittest import mock

from foxverify import ble, devices, flash
from foxverify.report import EXIT_NO_RUN, RunError
from foxverify.serial_fox import PROJECT_DIRS
from foxverify.tests import REPO
from foxverify.tests.test_devices import CP210X, ESP, NRF, Info

NET_BITS = (1 << 12) | (1 << 13)
ALL_TOOLS = ("pio", "sudo", "btmgmt", "bluetoothctl", "tshark", "ip", "iw")
PIO_OUTPUT = (b"Processing m5atom-easy (platform: espressif32@~6.7.0; board: m5stack-atom)\r\n"
              b"Writing at 0x00010000... (10 %)\rWriting at 0x00014000... (20 %)\r\n"
              b"Hard resetting via RTS pin...\n"
              b"========= [SUCCESS] Took 42.00 seconds =========\n")


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
                 interfaces=(), after_flash=None):
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
        self.events = []
        self.slept = []
        self.now = 1000.0

    def cleanup(self):
        os.rmdir(self.dev)

    def port(self, name, vid, pid, product, serial_number):
        return Info(os.path.join(self.dev, name), vid, pid, product, serial_number)

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
        if argv[1:] == ["-v"]:
            return self.sudo_status
        return self.verify_status

    def popen(self, argv, **kwargs):
        self.events.append(("popen", list(argv)))
        if self.after_flash is not None:
            self.after_flash(self)
        return FakeProcess(self.pio_output, self.pio_status)

    def sleep(self, seconds):
        self.slept.append(seconds)
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
        self.assertEqual(machine.slept, [flash.SETTLE_SECONDS])
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
        self.assertEqual(machine.slept, [])
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
