"""End-to-end serial-only runs of every project's verify through transcript
replay: the table rows, the notes, the exit codes and the not-a-fox outcomes.
The header is named explicitly and is the frozen copy under fixtures/headers/,
so neither a concurrent qa script that repoints current_conf.h nor the yearly
roll of 9999demo.h can change what a test sees. LiveDemoTest is the one place
the live demo header is used, with a transcript built from its own values."""
import io
import os
import tempfile
import unittest
from unittest import mock

from foxverify import run, serial_fox
from foxverify.report import EXIT_FAIL, EXIT_NO_RUN, EXIT_OK
from foxverify.tests import REPO, fixture, frozen_header, frozen_text, read_fixture

PROJECT_DIRS = serial_fox.PROJECT_DIRS

# transcript -> (project, rows expected with their verdicts, in table order)
RUNS = {
    "classic_easy": ("classic_discoverable", [
        ("MAC_ADDR", "unverified"), ("NAME", "unverified"),
        ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only")]),
    "classic_hard": ("classic_discoverable", [
        ("MAC_ADDR", "unverified"), ("NAME", "unverified"),
        ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only")]),
    "ibeacon_easy": ("iBeacon", [
        ("MAC_ADDR", "unverified"), ("DEVICE_NAME", "unverified"), ("BEACON_UUID", "unverified"),
        ("MAJOR", "unverified"), ("MINOR", "unverified"), ("SIGNAL_POWER", "unverified"),
        ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only"), ("TXPOWER", "serial only")]),
    "ibeacon_medium": ("iBeacon", [
        ("MAC_ADDR", "unverified"), ("DEVICE_NAME", "unverified"), ("BEACON_UUID", "unverified"),
        ("MAJOR", "unverified"), ("MINOR", "unverified"), ("SIGNAL_POWER", "unverified"),
        ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only"), ("TXPOWER", "serial only")]),
    "ibeacon_hard": ("iBeacon", [
        ("MAC_ADDR", "unverified"), ("DEVICE_NAME", "unverified"), ("BEACON_UUID", "unverified"),
        ("MAJOR", "unverified"), ("MINOR", "unverified"), ("SIGNAL_POWER", "unverified"),
        ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only"), ("TXPOWER", "serial only")]),
    "wifi_easy_ap": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("FSSID", "unverified"),
        ("SSID_HIDDEN", "unverified"), ("SECURITY", "unverified"),
        ("PSK", "serial only"), ("MAX_CLIENTS", "serial only"), ("TIME_TO_WAKE", "serial only"),
        ("TIME_TO_SLEEP", "serial only"), ("TXPOWER", "serial only")]),
    "wifi_hard_ap": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("FSSID", "unverified"),
        ("SSID_HIDDEN", "unverified"), ("SECURITY", "unverified"),
        ("PSK", "serial only"), ("MAX_CLIENTS", "serial only"), ("TIME_TO_WAKE", "serial only"),
        ("TIME_TO_SLEEP", "serial only"), ("TXPOWER", "serial only")]),
    "wifi_fiveeasy_ap": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("FSSID", "unverified"),
        ("SSID_HIDDEN", "unverified"), ("SECURITY", "unverified"),
        ("PSK", "serial only"), ("MAX_CLIENTS", "serial only"), ("TIME_TO_WAKE", "serial only"),
        ("TIME_TO_SLEEP", "serial only"), ("TXPOWER", "serial only")]),
    "wifi_fivehard_ap": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("FSSID", "unverified"),
        ("SSID_HIDDEN", "unverified"), ("SECURITY", "unverified"),
        ("PSK", "serial only"), ("MAX_CLIENTS", "serial only"), ("TIME_TO_WAKE", "serial only"),
        ("TIME_TO_SLEEP", "serial only"), ("TXPOWER", "serial only")]),
    "wifi_easy_client": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("FSSID", "unverified"),
        ("PSK", "serial only"), ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only"),
        ("TXPOWER", "serial only")]),
    "wifi_hard_client": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("FSSID", "unverified"),
        ("PSK", "serial only"), ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only"),
        ("TXPOWER", "serial only")]),
    "zigbee_easy": ("zigbee_coordinator", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("PAN_ID", "unverified"),
        ("SHORT_ADDR", "unverified"), ("PACKET_INTERVAL", "unverified"),
        ("EXT_PAN_ID", "serial only"), ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only"),
        ("TXPOWER", "serial only")]),
    "zigbee_hard": ("zigbee_coordinator", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("PAN_ID", "unverified"),
        ("SHORT_ADDR", "unverified"), ("PACKET_INTERVAL", "unverified"),
        ("EXT_PAN_ID", "serial only"), ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only"),
        ("TXPOWER", "serial only")]),
}


def table_rows(text):
    """(value, header, serial, air, verdict word) for every row of the table."""
    rows = []
    for line in text.splitlines():
        if " | " not in line or line.startswith("value "):
            continue
        cells = [cell.strip() for cell in line.split(" | ")]
        rows.append((cells[0], cells[1], cells[2], cells[3], cells[4].split(":")[0]))
    return rows


class Result:
    def __init__(self, code, out, err):
        self.code = code
        self.out = out
        self.err = err
        self.rows = table_rows(out)
        self.verdicts = [(row[0], row[4]) for row in self.rows]
        self.notes = [line[len("note: "):] for line in out.splitlines() if line.startswith("note: ")]
        lines = out.splitlines()
        index = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].startswith(("pass: ", "FAIL: "))), None)
        self.summary = lines[index] if index is not None else ""
        # The suggestion is the one line a run may print after its summary.
        self.suggestion = lines[index + 1] if index is not None and index + 1 < len(lines) else None


def verify(project, transcript, header=None, args=(), env_transcript=False):
    """One main() call with the transcript replayed, stdout and stderr captured."""
    out, err = io.StringIO(), io.StringIO()
    argv = list(args)
    environ = dict(os.environ)
    environ.pop(run.TRANSCRIPT_ENV, None)
    if env_transcript:
        environ[run.TRANSCRIPT_ENV] = transcript
    else:
        argv += ["--transcript", transcript]
    argv += ["--header", header or frozen_header(project)]
    with mock.patch.dict(os.environ, environ, clear=True):
        code = run.main(project, argv, out, err)
    return Result(code, out.getvalue(), err.getvalue())


class SerialOnlyRunTest(unittest.TestCase):
    """Every transcript replays into the expected table and exit 0."""

    def test_every_project_and_difficulty(self):
        for name, (project, expected) in RUNS.items():
            result = verify(project, fixture("transcripts", name + ".log"))
            self.assertEqual(result.code, EXIT_OK, name + "\n" + result.out + result.err)
            self.assertEqual(result.err, "", name)
            self.assertEqual(result.verdicts, expected, name)
            for value, header, serial, air, verdict in result.rows:
                if verdict in ("unverified", "serial only"):
                    self.assertEqual(air, "-", "%s: %s" % (name, value))
                if value != "SECURITY" and header != "random":
                    self.assertEqual(header, serial, "%s: %s" % (name, value))
            self.assertTrue(result.summary.startswith("pass: 0 pass, 0 FAIL, "), result.summary)
            self.assertIn("serial-only run", result.out)
            self.assertIn("replaying ", result.out)
            self.assertIn("Fox: " + project, result.out)

    def test_header_column_values(self):
        result = verify("wifi_ap_client", fixture("transcripts", "wifi_easy_ap.log"))
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["MAC_ADDR"][1:3], ("F2:F4:90:22:0D:0F", "F2:F4:90:22:0D:0F"))
        self.assertEqual(rows["CHANNEL"][1:3], ("1", "1"))
        self.assertEqual(rows["FSSID"][1], "Demo Hiro WiFi AP Easy Fox")
        self.assertEqual(rows["SECURITY"][1:4], ("WPA2-PSK/CCMP", "-", "-"))
        self.assertEqual(rows["PSK"][1:3], ("0123456789", "0123456789"))
        self.assertEqual(rows["TXPOWER"][1:3], ("WIFI_POWER_17dBm", "WIFI_POWER_17dBm"))
        self.assertEqual(rows["TIME_TO_WAKE"][1:3], ("15", "15"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:3], ("5", "5"))
        result = verify("wifi_ap_client", fixture("transcripts", "wifi_hard_ap.log"))
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["CHANNEL"][1:3], ("random", "7"))
        self.assertEqual(rows["CHANNEL"][4], "unverified")
        result = verify("zigbee_coordinator", fixture("transcripts", "zigbee_hard.log"))
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["PAN_ID"][1:3], ("0xDEAD", "0xDEAD"))
        self.assertEqual(rows["SHORT_ADDR"][1:3], ("0x0000", "0x0000"))
        self.assertEqual(rows["EXT_PAN_ID"][1:3], ("F2:A7:19:62:C3:08:BE:35", "F2:A7:19:62:C3:08:BE:35"))
        self.assertEqual(rows["TXPOWER"][1:3], ("20", "20"))
        result = verify("iBeacon", fixture("transcripts", "ibeacon_hard.log"))
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["SIGNAL_POWER"][1:3], ("-59", "-59"))
        self.assertEqual(rows["BEACON_UUID"][1], "DB6A0ED0-1DC3-4348-BD78-E997A0C082A3")
        self.assertEqual(rows["TIME_TO_WAKE"][1:3], ("10", "10"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:3], ("30", "30"))
        self.assertEqual(rows["TXPOWER"][1:], ("ESP_PWR_LVL_N12", "ESP_PWR_LVL_N12", "-", "serial only"))
        self.assertEqual(result.notes, [])

    def test_environment_variable_names_the_transcript(self):
        result = verify("classic_discoverable", fixture("transcripts", "classic_hard.log"), env_transcript=True)
        self.assertEqual(result.code, EXIT_OK, result.out + result.err)
        self.assertEqual(result.verdicts[2], ("TIME_TO_WAKE", "serial only"))

    def test_serial_only_flag_and_no_reset_are_accepted(self):
        result = verify("zigbee_coordinator", fixture("transcripts", "zigbee_easy.log"),
                        args=["--serial-only", "--no-reset", "-v", "--timeout", "30", "--wait-for-fox", "0"])
        self.assertEqual(result.code, EXIT_OK, result.out + result.err)
        self.assertIn("unverified: --serial-only", result.out)
        self.assertIn("serial: Fox: zigbee_coordinator EASY", result.out)
        self.assertTrue(result.summary.endswith("s of 30 s"), result.summary)

    def test_usb_serial_jtag_fox_armed_by_another_program_passes_after_one_more_reset(self):
        """A run over a fake USB-Serial-JTAG port whose chip another program
        left armed for the bootloader: the first reset boots the ROM, whose
        lines are read on the reopened port, the second boots the fox, and
        the run passes with exit 0. The device never sees DTR asserted alone."""
        from foxverify import devices
        from foxverify.tests.test_devices import ESP
        from foxverify.tests.test_serial_fox import ARMED, FakeSerial, JtagChip
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "ttyACM0")
            out = io.StringIO()
            one = run.RUNS["zigbee_coordinator"]("zigbee_coordinator", run.parse_args(
                "zigbee_coordinator", ["--transcript", fixture("transcripts", "zigbee_easy.log"),
                                       "--header", frozen_header("zigbee_coordinator")]), out)
            app = read_fixture("transcripts", "zigbee_easy.log").replace("\n", "\r\n").encode()
            chip = JtagChip(path, one.clock, app, armed=True, away=0.5)
            FakeSerial.instances = []
            FakeSerial.clock = one.clock
            FakeSerial.chip = chip
            self.addCleanup(setattr, FakeSerial, "chip", None)
            self.addCleanup(setattr, FakeSerial, "clock", None)

            def read_fox(selection):
                one.source = serial_fox.SerialSource(path, sleep=chip.sleep, port=devices.Port(path, *ESP))
                return serial_fox.read_fox(one.source, one.deadline, say=one.report.say,
                                           debug=one.report.debug, wall=one.wall)

            one.read_fox = read_fox
            with mock.patch("serial.Serial", FakeSerial):
                code = one.run()
        result = Result(code, out.getvalue(), "")
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertEqual(chip.boots, ["download", "app"])
        self.assertIn(serial_fox.IN_BOOTLOADER + "\n", result.out)
        self.assertEqual(result.verdicts, RUNS["zigbee_easy"][1])
        self.assertEqual(len(FakeSerial.instances), 3)
        for port in FakeSerial.instances:
            self.assertNotIn(ARMED, port.states)
        # The two ports whose device left the bus last saw the reset that took
        # it; the port that read the fox rests where the open left it.
        self.assertEqual([port.states[-1] for port in FakeSerial.instances],
                         [(False, True), (False, True), (True, True)])


class NotAFoxTest(unittest.TestCase):
    def test_empty_transcript_is_no_output(self):
        result = verify("iBeacon", fixture("transcripts", "empty.log"))
        self.assertEqual(result.code, EXIT_NO_RUN)
        self.assertEqual(result.err, serial_fox.NO_OUTPUT + "\n")
        self.assertEqual(result.err.rstrip("\n"), "no output at 115200 after reset; not a fox or wrong device")
        self.assertIn("press its reset button", result.out)
        self.assertEqual(result.rows, [])

    def test_rom_boot_without_banner(self):
        for name in ("rom_boot_only", "old_build_no_banner"):
            result = verify("classic_discoverable", fixture("transcripts", name + ".log"))
            self.assertEqual(result.code, EXIT_NO_RUN, name)
            self.assertEqual(result.err.rstrip("\n"),
                             "device boots but does not identify as a fox; other firmware, "
                             "or a kitsune build older than the banner", name)
            self.assertEqual(result.rows, [], name)

    def test_wrong_project_names_the_other_script(self):
        cases = [
            ("wifi_ap_client", "zigbee_easy", "this is a zigbee_coordinator fox; run zigbee/zigbee_coordinator/verify"),
            ("classic_discoverable", "ibeacon_medium", "this is a iBeacon fox; run bluetooth/iBeacon/verify"),
            ("iBeacon", "classic_hard", "this is a classic_discoverable fox; run bluetooth/classic_discoverable/verify"),
            ("zigbee_coordinator", "wifi_easy_client", "this is a wifi_ap_client fox; run wifi/wifi_ap_client/verify"),
        ]
        for project, name, text in cases:
            result = verify(project, fixture("transcripts", name + ".log"))
            self.assertEqual(result.code, EXIT_NO_RUN, name)
            self.assertEqual(result.err.rstrip("\n"), text)
            self.assertEqual(result.rows, [])

    def test_missing_block_is_named(self):
        header = frozen_text("classic_discoverable").replace("#if defined(HARD)", "#if defined(NEVER)")
        with tempfile.NamedTemporaryFile("w", suffix=".h", delete=False) as handle:
            handle.write(header)
        self.addCleanup(os.unlink, handle.name)
        result = verify("classic_discoverable", fixture("transcripts", "classic_hard.log"), header=handle.name)
        self.assertEqual(result.code, EXIT_NO_RUN)
        self.assertEqual(result.err.rstrip("\n"),
                         "src/current_conf.h has no HARD block; the fox was built with -D HARD")

    def test_unreadable_header_and_transcript(self):
        result = verify("iBeacon", fixture("transcripts", "ibeacon_easy.log"), header="/nonexistent/current_conf.h")
        self.assertEqual(result.code, EXIT_NO_RUN)
        self.assertIn("cannot read /nonexistent/current_conf.h", result.err)
        result = verify("iBeacon", "/nonexistent/transcript.log")
        self.assertEqual(result.code, EXIT_NO_RUN)
        self.assertIn("cannot read /nonexistent/transcript.log", result.err)


class DifferentHeaderTest(unittest.TestCase):
    def test_serial_mac_differs_from_the_header(self):
        header = frozen_text("classic_discoverable").replace(
            "{0xF2, 0x81, 0x5A, 0xC1, 0xA3, 0x26}", "{0xF2, 0x81, 0x5A, 0xC1, 0xA3, 0x2A}")
        with tempfile.NamedTemporaryFile("w", suffix=".h", delete=False) as handle:
            handle.write(header)
        self.addCleanup(os.unlink, handle.name)
        result = verify("classic_discoverable", fixture("transcripts", "classic_easy.log"), header=handle.name)
        self.assertEqual(result.code, EXIT_FAIL)
        self.assertEqual(result.err, "")
        self.assertEqual(result.rows, [("MAC_ADDR", "F2:81:5A:C1:A3:2A", "F2:81:5A:C1:A3:26", "-", "FAIL")])
        self.assertEqual(result.notes, ["fox was built from a different conference header than src/current_conf.h"])
        self.assertTrue(result.summary.startswith("FAIL: 0 pass, 1 FAIL"))

    def test_fox_that_halted_on_its_address(self):
        result = verify("classic_discoverable", fixture("transcripts", "classic_easy_mismatch.log"))
        self.assertEqual(result.code, EXIT_FAIL)
        self.assertEqual(result.rows, [("MAC_ADDR", "F2:81:5A:C1:A3:26", "F2:81:5A:C1:A3:28", "-", "FAIL")])
        self.assertEqual(result.notes, ["the fox refused to run: Device address != Requested address"])

    def test_fox_that_halted_on_its_pan_id(self):
        result = verify("zigbee_coordinator", fixture("transcripts", "zigbee_easy_mismatch.log"))
        self.assertEqual(result.code, EXIT_FAIL)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["PAN_ID"][1:], ("0x1337", "0x1234", "-", "FAIL"))
        self.assertEqual(rows["MAC_ADDR"][4], "unverified")
        self.assertEqual(rows["SHORT_ADDR"][2:], ("-", "-", "FAIL"))
        self.assertIn("FAIL: not printed on serial", result.out)
        self.assertEqual(rows["TIME_TO_WAKE"][4], "serial only")
        self.assertEqual(result.notes, ["the fox refused to run: Operating PAN ID != Requested PAN ID"])

    def test_fox_whose_radio_start_failed(self):
        """The start failure is printed before the banner, which rfhsfatal()
        prints on its own: the run reports a halted fox with the reason and
        exits 1, not a device that is not a fox."""
        result = verify("zigbee_coordinator", fixture("transcripts", "zigbee_start_failed.log"))
        self.assertEqual(result.code, EXIT_FAIL, result.out + result.err)
        self.assertEqual(result.err, "")
        self.assertIn("Fox: zigbee_coordinator EASY", result.out)
        self.assertEqual(result.rows, [("MAC_ADDR", "F2:5A:3C:91:0E:7B:44:D8", "-", "-", "FAIL")])
        self.assertIn("FAIL: not printed on serial", result.out)
        self.assertEqual(result.notes, ["the fox refused to run: Error starting Zigbee"])
        self.assertTrue(result.summary.startswith("FAIL: 0 pass, 1 FAIL, 0 serial only, 0 unverified"), result.summary)

    def test_changed_serial_only_value_fails(self):
        header = frozen_text("wifi_ap_client").replace("#define TIME_TO_WAKE 15", "#define TIME_TO_WAKE 20", 1)
        with tempfile.NamedTemporaryFile("w", suffix=".h", delete=False) as handle:
            handle.write(header)
        self.addCleanup(os.unlink, handle.name)
        result = verify("wifi_ap_client", fixture("transcripts", "wifi_easy_ap.log"), header=handle.name)
        self.assertEqual(result.code, EXIT_FAIL)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("20", "15", "-", "FAIL"))
        self.assertEqual(rows["TIME_TO_SLEEP"][4], "serial only")


def live_demo(project):
    return os.path.join(REPO, PROJECT_DIRS[project], "src", "conferences", "9999demo.h")


SETTING_UP = {"classic_discoverable": "Bluetooth Classic", "iBeacon": "iBeacon",
              "AP": "WiFi AP", "CLIENT": "WiFi Client", "zigbee_coordinator": "Zigbee Coordinator"}


def transcript_for(project, difficulty, mode, block):
    """The lines a fox built from ``block`` prints, in the firmware's formats
    and order, so a header can be replayed against itself: the boot lines of
    rfhsboot(), the MAC set, the banner, the timers, the device address first
    of the readbacks, then the radio's values and "Awake and screaming". A
    random CHANNEL or PAN_ID is printed as a fixed stand-in for what the fox
    would have picked. A Wi-Fi AP or Zigbee fox names its channel on the
    Starting on channel line before its radio starts and reads it back after
    the banner."""
    lines = ["Initializing...", "ESP32 boot count: 0", "Sleep stats: 0s since cold boot, 0s since last wakeup",
             "Setting up %s..." % SETTING_UP[mode or project], "MAC address set successfully"]
    channel = None
    if project == "wifi_ap_client" and mode == "AP":
        channel = block.integer("CHANNEL") or 6
    elif project == "zigbee_coordinator":
        channel = block.integer("CHANNEL") or 11
    if channel is not None:
        lines.append("Starting on channel %d" % channel)
    if project == "wifi_ap_client":
        lines.append("Set power status: ok")
    lines += ["Fox: %s %s%s" % (project, difficulty, " " + mode if mode else ""),
              "Time to wake: %ss" % block.display("TIME_TO_WAKE"),
              "Time to sleep: %ss" % block.display("TIME_TO_SLEEP"),
              "Device address: " + block.mac("MAC_ADDR")]
    if project == "classic_discoverable":
        lines += ["Device name: " + block.string("NAME")]
    elif project == "iBeacon":
        power = block.integer("SIGNAL_POWER")
        # The ESP_PWR_LVL_* name spells out its dBm: N12 is -12, P9 is +9.
        tx_power = block.identifier("TXPOWER")
        dbm = int(tx_power[len("ESP_PWR_LVL_"):].replace("N", "-").replace("P", ""))
        lines += ["Device name: " + block.string("DEVICE_NAME"), "Beacon UUID: " + block.string("BEACON_UUID"),
                  "Major: 0x%04X (%d)" % (block.integer("MAJOR"), block.integer("MAJOR")),
                  "Minor: 0x%04X (%d)" % (block.integer("MINOR"), block.integer("MINOR")),
                  "Signal power: %d" % (power - 256 if power > 127 else power),
                  "Tx power: %s (%d dBm)" % (tx_power, dbm)]
    elif project == "wifi_ap_client" and mode == "AP":
        lines += ["Operating channel: %d" % channel,
                  "Operating SSID: " + block.string("FSSID"), "Operating PSK: " + block.string("PSK"),
                  "Hidden SSID: " + block.display("SSID_HIDDEN"), "Max clients: " + block.display("MAX_CLIENTS"),
                  "Tx power: " + block.identifier("TXPOWER")]
    elif project == "wifi_ap_client":
        lines += ["Operating SSID: " + block.string("FSSID"), "Operating PSK: " + block.string("PSK"),
                  "Tx power: " + block.identifier("TXPOWER")]
    else:
        lines += ["Operating channel: %d" % channel,
                  "Operating PAN ID: 0x%04X" % (0x1234 if block.is_bare_zero("PAN_ID") else block.integer("PAN_ID")),
                  "Extended PAN ID: " + block.mac("EXT_PAN_ID"), "Short address: 0x0000",
                  "Packet interval: %ss" % block.display("PACKET_INTERVAL"),
                  "Tx power: %s dBm" % block.display("TXPOWER")]
    return "\n".join(lines) + "\nAwake and screaming\n"


class LiveDemoTest(unittest.TestCase):
    """Every block of every project's live 9999demo.h verifies against a
    transcript built from its own values. No value is written down here, so
    the test holds for whatever make_conference rolled into the demo."""

    def test_every_block_of_the_live_demo(self):
        from foxverify import conf
        for project in PROJECT_DIRS:
            with open(live_demo(project), "r", encoding="utf-8") as handle:
                text = handle.read()
            for key in conf.blocks(text):
                tokens = key.split()
                mode = tokens[0] if tokens[0] in ("AP", "CLIENT") else None
                difficulty = [t for t in tokens if t not in ("AP", "CLIENT", "COORDINATOR")][0]
                block = conf.select(text, conf.defined_for(project, difficulty, mode))
                with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as handle:
                    handle.write(transcript_for(project, difficulty, mode, block))
                self.addCleanup(os.unlink, handle.name)
                result = verify(project, handle.name, header=live_demo(project))
                label = "%s %s" % (project, key)
                self.assertEqual(result.code, EXIT_OK, label + "\n" + result.out + result.err)
                self.assertTrue(result.summary.startswith("pass: 0 pass, 0 FAIL, "), label + " " + result.summary)
                self.assertEqual([v for v, _ in result.verdicts],
                                 [v for v, _ in RUNS[self.transcript_name(project, difficulty, mode)][1]], label)
                for value, header, serial, air, verdict in result.rows:
                    if value != "SECURITY" and header != "random":
                        self.assertEqual(header, serial, "%s: %s" % (label, value))
                if "PSK" in block:
                    rows = {row[0]: row for row in result.rows}
                    self.assertEqual(rows["PSK"][1:], (block.string("PSK"), block.string("PSK"), "-", "serial only"), label)

    @staticmethod
    def transcript_name(project, difficulty, mode):
        prefix = {"classic_discoverable": "classic", "iBeacon": "ibeacon",
                  "wifi_ap_client": "wifi", "zigbee_coordinator": "zigbee"}[project]
        return "_".join([prefix, difficulty.lower()] + ([mode.lower()] if mode else []))


class FakeScan:
    """Stands in for btclassic.Inquiry and ble.BleScan: records the target,
    answers result() from a table, and hands out scripted batches of frames
    from take_heard(); ``between(n)`` runs after the n-th batch was taken so
    a test can move the clock and feed the serial follower."""

    def __init__(self, answer, batches=(), between=None):
        self.answer = answer
        self.batches = [list(batch) for batch in batches]
        self.between = between
        self.target = None
        self.stopped = False
        self.joined = False
        self.alive = False
        self.keep_going = False
        self.keep_scanning = False
        self.takes = 0

    def set_target(self, address):
        self.target = address.upper()

    def result(self, deadline=None):
        return self.answer

    def named(self, mac):
        found = self.answer.get(mac.upper())
        return found is not None and found.name is not None

    def complete(self, mac):
        seen = self.answer.get(mac.upper())
        return seen is not None and seen.complete()

    def is_alive(self):
        return self.alive

    def take_heard(self, mac):
        if not self.batches:
            return []
        batch = self.batches.pop(0)
        self.takes += 1
        if self.between is not None:
            self.between(self.takes)
        return batch

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        self.joined = True


def air_run(cls, project, transcript, start_air, header=None, args=(), prepare=None):
    """A replayed run whose on-air step is replaced: ``start_air`` is called
    with the candidate MACs and returns the handle ``rows`` gets; ``prepare``
    gets the Run before it starts."""
    out = io.StringIO()
    argv = list(args) + ["--transcript", transcript, "--header", header or frozen_header(project)]
    one = cls(project, run.parse_args(project, argv), out)
    one.serial_only = False
    one.air_reason = run.SERIAL_ONLY
    handles = []

    def fake_start_air(selection, candidates):
        handle = start_air(candidates)
        handles.append(handle)
        return handle

    one.start_air = fake_start_air
    if prepare is not None:
        prepare(one)
    code = one.run()
    return Result(code, out.getvalue(), ""), handles[0]


WIFI_HEADER_MACS = ["F2:F4:90:22:0D:0F", "F2:72:C1:79:16:1B", "F2:77:20:34:0A:C7", "F2:13:D4:3C:51:4B",
                    "F2:44:5E:10:97:F4", "F2:83:27:31:80:C7"]


def fake_ap_capture(calls, feed, beacon):
    """A stand-in for wifi.ApCapture: its start, wait and close go into
    ``calls`` and ``feed(cycle, follower, random_channel, beacon)`` answers
    the wait."""
    class FakeApCapture:
        def __init__(self, interface, bssids, channel, tshark_path, run=None, popen=None, debug=None):
            calls.append(("capture", interface, list(bssids), channel, tshark_path))
            self.channel = channel

        def retune(self, channel):
            calls.append(("retune", channel))

        def wait(self, bssid, deadline, cycle=None, follower=None, random_channel=False):
            calls.append(("wait", bssid, cycle is not None, follower is not None, random_channel))
            return feed(cycle, follower, random_channel, beacon)

        def close(self):
            calls.append(("closed",))

    return FakeApCapture


def fake_zigbee_capture(calls, collect):
    """A stand-in for zigbee.Capture: its start and close go into ``calls``
    and ``collect(channel, pan_id, want, cycle, follower, random_channel,
    mac)`` answers the read with an Observation."""
    class FakeCapture:
        def __init__(self, sniffer_path, channel, deadline, tshark_path, open_port=None, popen=None, debug=None):
            calls.append(("capture", sniffer_path, channel, tshark_path))
            self.channel = channel

        def collect(self, deadline, pan_id, want_link_status, cycle=None, follower=None, random_channel=False,
                    mac=None):
            return collect(self.channel, pan_id, want_link_status, cycle, follower, random_channel, mac)

        def close(self):
            calls.append(("closed",))

    return FakeCapture


def sleep_line(one, at):
    """Move the replay clock to ``at`` and let the fox's serial say it sleeps,
    which the follower picks up at its next poll."""
    one.clock.now = at
    one.source.items.append((0.0, "Going to sleep\n"))


def elapsed(result):
    """The seconds the summary says the run took on the replay clock."""
    return float(result.summary.rsplit(", ", 1)[1].split(" s of ")[0])


def heard(start, count, spacing, rssi=-50):
    from foxverify.cycle import Heard
    return [Heard(start + i * spacing, rssi) for i in range(count)]


class AirRunTest(unittest.TestCase):
    """The on-air step of each project with the sniffer modules faked: the
    scan gets the block's MAC as its target once the banner is in, the rows
    pass or fail on what the air reported, and the timers are measured on the
    frames heard when --timeout covers a cycle."""

    def test_classic_pass_is_serial_only_for_the_timers_at_60(self):
        from foxverify import btclassic
        parser = btclassic.BtmgmtParser()
        parser.feed_text("hci0 dev_found: F2:F6:6D:BC:2A:80 type BR/EDR rssi -61 flags 0x0000\n"
                         "name Demo Case BTC Hard Fox\n")
        scan = FakeScan(parser, [heard(1002.0, 3, 1.0, -61)])
        seen = []
        result, handle = air_run(run.ClassicRun, "classic_discoverable", fixture("transcripts", "classic_hard.log"),
                                 lambda candidates: seen.append(candidates) or scan)
        self.assertEqual(seen, [["F2:81:5A:C1:A3:26", "F2:F6:6D:BC:2A:80"]])
        self.assertEqual(scan.target, "F2:F6:6D:BC:2A:80")
        self.assertFalse(scan.keep_going)
        self.assertTrue(scan.stopped and scan.joined)
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertEqual(result.verdicts, [("MAC_ADDR", "pass"), ("NAME", "pass"),
                                           ("TIME_TO_WAKE", "serial only"), ("TIME_TO_SLEEP", "serial only")])
        self.assertEqual(result.notes, [])
        self.assertIn("TIME_TO_WAKE and TIME_TO_SLEEP serial only (--timeout 60 is under the 125 s needed to "
                      "measure the cycle time: two cycles of 60 s plus the 5 s boot allowance)\n", result.out)
        self.assertIn("first transmission: 2.0 s after reset\n", result.out)
        self.assertNotIn("first wake:", result.out)
        self.assertTrue(result.summary.startswith("pass: 2 pass, 0 FAIL, 2 serial only, 0 unverified"))
        self.assertEqual(result.suggestion, "run with --timeout 125 to measure the cycle time")
        # The run ended as soon as the identity rows were in, not at the
        # deadline: the replay clock shows under a second of the 60.
        self.assertTrue(result.summary.endswith(" s of 60 s"), result.summary)
        self.assertLess(elapsed(result), 1.0)

    def test_classic_first_boot_at_65_with_inquiries_back_to_back(self):
        from foxverify import btclassic
        parser = btclassic.BtmgmtParser()
        parser.feed_text("hci0 dev_found: F2:F6:6D:BC:2A:80 type BR/EDR rssi -61 flags 0x0000\n"
                         "name Demo Case BTC Hard Fox\n")
        runs = []
        # Wake 1: responses from 2 s to 30 s after the reset at 1000; the fox
        # says it sleeps at 32.5 s; wake 2 answers at 62.5 s, which ends the
        # run at once.
        scan = FakeScan(parser, [heard(1002.0, 15, 2.0, -61), heard(1062.5, 1, 1.0, -63)],
                        between=lambda n: sleep_line(runs[0], 1032.5) if n == 1 else None)
        result, _ = air_run(run.ClassicRun, "classic_discoverable", fixture("transcripts", "classic_hard.log"),
                            lambda candidates: scan, args=["--timeout", "65"], prepare=runs.append)
        self.assertTrue(scan.keep_going)
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertIn("judging the first boot with wider tolerances (--timeout 65 covers one cycle of 60 s plus the "
                      "5 s boot allowance; two cycles need 125)\n", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("30", "30", "first boot: on the air 28.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("30", "30", "first boot: off the air 32.5 s", "pass"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("60", "-", "first boot: 62.5 s", "pass"))
        self.assertEqual([v for v, _ in result.verdicts], ["MAC_ADDR", "NAME", "TIME_TO_WAKE", "TIME_TO_SLEEP", "CYCLE_TIME"])
        self.assertEqual(result.notes, [])
        self.assertIn("first transmission: 2.0 s after reset\n", result.out)
        self.assertNotIn("first wake:", result.out)
        self.assertTrue(result.summary.startswith("pass: 5 pass, 0 FAIL, 0 serial only, 0 unverified"), result.summary)
        self.assertTrue(result.summary.endswith("s of 65 s"), result.summary)
        self.assertEqual(result.suggestion, "run with --timeout 125 for the exact cycle time; this run judged the "
                                            "first boot with wider tolerances")
        # Both batches were taken and the loop ended at wake 2's first frame.
        self.assertEqual(scan.takes, 2)

    def test_classic_two_cycles_at_125(self):
        """Wake 2 and wake 3 heard: the three rows judge wake 2's span and
        the period to wake 3 exactly, wake 1 goes into the first wake line,
        and nothing is suggested."""
        from foxverify import btclassic
        parser = btclassic.BtmgmtParser()
        parser.feed_text("hci0 dev_found: F2:F6:6D:BC:2A:80 type BR/EDR rssi -61 flags 0x0000\n"
                         "name Demo Case BTC Hard Fox\n")
        runs = []

        def between(n):
            if n == 1:
                sleep_line(runs[0], 1032.5)
            elif n == 2:
                # Wake 2's sleep line, then wake 3's boot lines, each taken by
                # one poll of the follower before wake 3's first response.
                sleep_line(runs[0], 1092.5)
                runs[0].source.items.append((0.0, "Initializing...\n"))
                runs[0].source.items.append((0.0, "Last cycle: 60.0s, target 60s\n"))

        scan = FakeScan(parser, [heard(1002.0, 15, 2.0, -61), heard(1062.5, 15, 2.0, -63), [], [],
                                 heard(1122.5, 1, 1.0, -62)], between=between)
        result, _ = air_run(run.ClassicRun, "classic_discoverable", fixture("transcripts", "classic_hard.log"),
                            lambda candidates: scan, args=["--timeout", "125"], prepare=runs.append)
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertIn("measuring the cycle time from wake 2 and wake 3 (--timeout 125 covers two cycles of 60 s plus "
                      "the 5 s boot allowance)\n", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("30", "30", "on the air 28.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("30", "30", "off the air 32.0 s", "pass"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("60", "60.0", "60.0 s", "pass"))
        self.assertIn("first transmission: 2.0 s after reset\n", result.out)
        self.assertIn("first wake: on the air 28.0 s, then off the air 32.5 s, cycle time 62.5 s\n", result.out)
        self.assertTrue(result.summary.startswith("pass: 5 pass, 0 FAIL, 0 serial only, 0 unverified"), result.summary)
        self.assertTrue(result.summary.endswith("s of 125 s"), result.summary)
        self.assertIsNone(result.suggestion)
        self.assertEqual(scan.takes, 5)

    def test_classic_no_answer_and_wrong_name(self):
        from foxverify import btclassic
        result, _ = air_run(run.ClassicRun, "classic_discoverable", fixture("transcripts", "classic_hard.log"),
                            lambda candidates: FakeScan(btclassic.BtmgmtParser()))
        self.assertEqual(result.code, EXIT_OK)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["MAC_ADDR"][4], "unverified")
        self.assertIn("no inquiry response from F2:F6:6D:BC:2A:80 before the deadline", result.out)
        self.assertIn("first transmission: none heard before the deadline\n", result.out)
        parser = btclassic.BtmgmtParser()
        parser.feed_text("hci0 dev_found: F2:F6:6D:BC:2A:80 type BR/EDR rssi -61 flags 0x0000\nname Other\n")
        result, _ = air_run(run.ClassicRun, "classic_discoverable", fixture("transcripts", "classic_hard.log"),
                            lambda candidates: FakeScan(parser))
        self.assertEqual(result.code, EXIT_FAIL)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["MAC_ADDR"][4], "pass")
        self.assertEqual(rows["NAME"][3:], ("Other", "FAIL"))

    def test_classic_remote_name_fallback(self):
        from foxverify import btclassic
        parser = btclassic.BtmgmtParser()
        parser.feed_text("hci0 dev_found: F2:F6:6D:BC:2A:80 type BR/EDR rssi -61 flags 0x0000\n")
        asked = []

        def remote_name(address, deadline, bluetoothctl, run=None, debug=None, sleep=None):
            asked.append((address, bluetoothctl))
            return "Demo Case BTC Hard Fox"

        def start_air(candidates):
            return FakeScan(parser)

        with mock.patch.object(btclassic, "remote_name", remote_name):
            out = io.StringIO()
            one = run.ClassicRun("classic_discoverable", run.parse_args(
                "classic_discoverable", ["--transcript", fixture("transcripts", "classic_hard.log"),
                                         "--header", frozen_header("classic_discoverable")]), out)
            one.serial_only = False
            one.bluetoothctl = "/usr/bin/bluetoothctl"
            one.start_air = lambda selection, candidates: start_air(candidates)
            code = one.run()
        self.assertEqual(code, EXIT_OK, out.getvalue())
        self.assertEqual(asked, [("F2:F6:6D:BC:2A:80", "/usr/bin/bluetoothctl")])
        self.assertEqual(table_rows(out.getvalue())[1][4], "pass")

    def test_ibeacon_medium_is_measured_at_60(self):
        from foxverify import ble
        payload = bytes.fromhex("0215" "162EEB7B743C47E99414BBD6149B4E40" "0005" "0058" "C5")
        seen = {"F2:63:89:10:8D:1D": ble.Seen("F2:63:89:10:8D:1D", "Demo Cath BLE Medium Fox",
                                              ble.decode_ibeacon(payload), -50, 1.0)}
        runs = []

        def between(n):
            if n == 1:
                sleep_line(runs[0], 1006.7)
            elif n == 2:
                sleep_line(runs[0], 1016.7)

        # 5/5, two cycles in 60 s: advertisements from 1.5 s to 6.5 s after
        # the reset, the sleep line at 6.7 s, wake 2 from 11.5 s to 16.5 s,
        # the sleep line at 16.7 s, wake 3 at 21.5 s.
        scan = FakeScan(seen, [heard(1001.5, 51, 0.1, -50), heard(1011.5, 51, 0.1, -50), heard(1021.5, 2, 0.1, -52)],
                        between=between)
        result, _ = air_run(run.IBeaconRun, "iBeacon", fixture("transcripts", "ibeacon_medium.log"),
                            lambda candidates: scan, prepare=runs.append)
        self.assertEqual(scan.target, "F2:63:89:10:8D:1D")
        self.assertTrue(scan.keep_scanning)
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertIn("measuring the cycle time from wake 2 and wake 3 (--timeout 60 covers two cycles of 10 s plus "
                      "the 5 s boot allowance)\n", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("5", "5", "on the air 5.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("5", "5", "off the air 5.0 s", "pass"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("10", "-", "10.0 s", "pass"))
        self.assertEqual(rows["TXPOWER"][1:], ("ESP_PWR_LVL_N0", "ESP_PWR_LVL_N0", "median -50 dBm over 104 frames",
                                               "serial only"))
        self.assertIn("first transmission: 1.5 s after reset\n", result.out)
        self.assertIn("first wake: on the air 5.0 s, then off the air 5.0 s, cycle time 11.5 s\n", result.out)
        self.assertEqual([v for v, _ in result.verdicts],
                         ["MAC_ADDR", "DEVICE_NAME", "BEACON_UUID", "MAJOR", "MINOR", "SIGNAL_POWER",
                          "TIME_TO_WAKE", "TIME_TO_SLEEP", "CYCLE_TIME", "TXPOWER"])
        self.assertTrue(result.summary.startswith("pass: 9 pass, 0 FAIL, 1 serial only, 0 unverified"), result.summary)
        self.assertIsNone(result.suggestion)
        wrong = seen["F2:63:89:10:8D:1D"]._replace(beacon=ble.decode_ibeacon(payload)._replace(major=6))
        result, _ = air_run(run.IBeaconRun, "iBeacon", fixture("transcripts", "ibeacon_medium.log"),
                            lambda candidates: FakeScan({"F2:63:89:10:8D:1D": wrong}))
        self.assertEqual(result.code, EXIT_FAIL)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["MAJOR"][1:], ("5", "5", "6", "FAIL"))
        result, _ = air_run(run.IBeaconRun, "iBeacon", fixture("transcripts", "ibeacon_medium.log"),
                            lambda candidates: FakeScan({}))
        # Never heard at all: every on-air row is unverified, nothing FAILs.
        self.assertEqual(result.code, EXIT_OK)
        self.assertIn("unverified: F2:63:89:10:8D:1D not seen by the scan before the deadline", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][3:], ("-", "unverified"))
        self.assertIn("unverified: no frame from the fox", result.out)
        self.assertEqual(rows["TXPOWER"][3:], ("-", "serial only"))

    def test_ibeacon_no_reset_keeps_the_timers_serial_only(self):
        from foxverify import ble
        payload = bytes.fromhex("0215" "162EEB7B743C47E99414BBD6149B4E40" "0005" "0058" "C5")
        seen = {"F2:63:89:10:8D:1D": ble.Seen("F2:63:89:10:8D:1D", "Demo Cath BLE Medium Fox",
                                              ble.decode_ibeacon(payload), -50, 1.0)}
        scan = FakeScan(seen, [heard(1001.5, 3, 0.1, -50)])
        result, _ = air_run(run.IBeaconRun, "iBeacon", fixture("transcripts", "ibeacon_medium.log"),
                            lambda candidates: scan, args=["--no-reset"])
        self.assertFalse(scan.keep_scanning)
        self.assertEqual(result.code, EXIT_OK, result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][3:], ("-", "serial only"))
        self.assertIn("TIME_TO_WAKE  | 5", result.out)
        self.assertIn("| serial only: --no-reset", result.out)
        self.assertIn("first transmission: not measured (--no-reset)\n", result.out)
        self.assertEqual(result.notes, [])
        self.assertEqual(rows["TXPOWER"][3], "median -50 dBm over 3 frames")

    def test_fox_whose_stack_has_no_reset_keeps_the_timers_serial_only(self):
        """The Nano's TinyUSB cannot reset the fox: the run says so, waits for
        the fox's own wake, and the timers stay serial only with that reason
        rather than --no-reset."""
        from foxverify import ble
        payload = bytes.fromhex("0215" "162EEB7B743C47E99414BBD6149B4E40" "0005" "0058" "C5")
        seen = {"F2:63:89:10:8D:1D": ble.Seen("F2:63:89:10:8D:1D", "Demo Cath BLE Medium Fox",
                                              ble.decode_ibeacon(payload), -50, 1.0)}
        scan = FakeScan(seen, [heard(1001.5, 3, 0.1, -50)])

        def prepare(one):
            read_fox = one.read_fox

            def without_reset(selection):
                with mock.patch.object(serial_fox.TranscriptSource, "reset", lambda self, wall=None: None):
                    return read_fox(selection)

            one.read_fox = without_reset

        result, _ = air_run(run.IBeaconRun, "iBeacon", fixture("transcripts", "ibeacon_medium.log"),
                            lambda candidates: scan, prepare=prepare)
        self.assertFalse(scan.keep_scanning)
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertIn(serial_fox.NO_SERIAL_RESET + "\n", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][3:], ("-", "serial only"))
        self.assertIn("| serial only: the fox was not reset", result.out)
        self.assertIn("first transmission: not measured (the fox was not reset)\n", result.out)
        self.assertEqual(result.notes, [])
        self.assertEqual(rows["TXPOWER"][3], "median -50 dBm over 3 frames")

    def wifi_ap(self, feed, args=(), transcript="wifi_easy_ap.log", header=None, prepare=None):
        """A Wi-Fi AP run whose ApCapture is replaced: ``calls`` records the
        monitor mode, the capture's start (interface, BSSIDs, channel, tshark)
        and its wait, which ``feed(cycle, follower, random_channel, beacon)``
        answers with the beacon. ``transcript`` is a fixture name or a path."""
        from foxverify import tshark, wifi
        from foxverify.tests import read_fixture
        beacon = wifi.parse_beacon(tshark.parse_line(read_fixture("tshark", "ap_beacons.tsv").splitlines()[0],
                                                     wifi.AP_FIELDS))
        calls = []
        capture = fake_ap_capture(calls, feed, beacon)
        path = transcript if os.path.isabs(transcript) else fixture("transcripts", transcript)

        from contextlib import contextmanager

        @contextmanager
        def monitor_mode(name, *a, **kw):
            calls.append(("monitor", name))
            yield wifi.InterfaceState(name, "managed", True)
            calls.append(("restored", name))

        with mock.patch.object(wifi, "ApCapture", capture), mock.patch.object(wifi, "monitor_mode", monitor_mode):
            out = io.StringIO()
            one = run.WifiRun("wifi_ap_client", run.parse_args(
                "wifi_ap_client", list(args) + ["--transcript", path,
                                                "--header", header or frozen_header("wifi_ap_client")]), out)
            one.serial_only = False
            one.tshark = "/usr/bin/tshark"
            one.start_air = lambda selection, candidates: "wlan1"
            if prepare is not None:
                prepare(one)
            code = one.run()
        return Result(code, out.getvalue(), ""), calls, one

    def test_wifi_easy_ap_measures_the_cycle_at_60(self):
        def feed(cycle, follower, random_channel, beacon):
            # 15/5 with a 1.5 s boot, two cycles in 60 s: beacons for 15 s,
            # the sleep line, wake 2's first beacon 20 s after wake 1's and
            # its own 15 s of beacons, wake 3's first beacon 20 s later.
            self.assertEqual(cycle.tier, "two cycles")
            self.assertTrue(follower.reopen)
            for frame in heard(1001.5, 147, 0.1024, -42):
                cycle.feed(frame)
            cycle.mark_sleep(1016.7)
            for frame in heard(1021.5, 147, 0.1024, -42):
                cycle.feed(frame)
            cycle.mark_sleep(1036.7)
            cycle.feed(heard(1041.5, 1, 1.0, -44)[0])
            return beacon

        result, calls, one = self.wifi_ap(feed, args=["-v"])
        self.assertEqual(result.code, EXIT_OK, result.out)
        # The capture started on the Starting on channel line, before the
        # banner chose the block, so it is filtered to every header MAC.
        self.assertEqual(calls, [("monitor", "wlan1"), ("capture", "wlan1", WIFI_HEADER_MACS, 1, "/usr/bin/tshark"),
                                 ("wait", "F2:F4:90:22:0D:0F", True, True, False), ("closed",), ("restored", "wlan1")])
        self.assertEqual(one.tuned.label, "Starting on channel")
        self.assertIn("tuning wlan1 to channel 1 on the fox's Starting on channel line\n", result.out)
        self.assertEqual(one.cycle.listen_time, one.tuned.when)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual([rows[v][4] for v in ("MAC_ADDR", "CHANNEL", "FSSID", "SSID_HIDDEN", "SECURITY")], ["pass"] * 5)
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("15", "15", "on the air 15.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("5", "5", "off the air 5.0 s", "pass"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("20", "-", "20.0 s", "pass"))
        self.assertEqual(rows["TXPOWER"][1:], ("WIFI_POWER_17dBm", "WIFI_POWER_17dBm", "median -42 dBm over 295 frames",
                                               "serial only"))
        self.assertEqual(rows["PSK"][4], "serial only")
        self.assertIn("measuring the cycle time from wake 2 and wake 3 (--timeout 60 covers two cycles of 20 s plus "
                      "the 5 s boot allowance)\n", result.out)
        self.assertIn("listening for beacons from F2:F4:90:22:0D:0F on channel 1 with wlan1 through the first two sleeps",
                      result.out)
        self.assertIn("first transmission: 1.5 s after reset\n", result.out)
        self.assertIn("first wake: on the air 15.0 s, then off the air 5.0 s, cycle time 21.5 s\n", result.out)
        self.assertEqual(result.notes, [])
        self.assertTrue(result.summary.startswith("pass: 8 pass, 0 FAIL, 3 serial only, 0 unverified"), result.summary)
        self.assertIsNone(result.suggestion)
        self.assertEqual([v for v, _ in result.verdicts],
                         ["MAC_ADDR", "CHANNEL", "FSSID", "SSID_HIDDEN", "SECURITY", "PSK", "MAX_CLIENTS",
                          "TIME_TO_WAKE", "TIME_TO_SLEEP", "CYCLE_TIME", "TXPOWER"])

    def test_wifi_easy_ap_judges_the_first_boot_at_30(self):
        """15/5 at --timeout 30: one cycle fits, two (45 s) do not, so the
        three rows judge wake 1 with the first-boot rules and the run says
        what --timeout gives the exact figures."""
        def feed(cycle, follower, random_channel, beacon):
            self.assertEqual(cycle.tier, "one cycle")
            self.assertTrue(follower.reopen)
            for frame in heard(1001.5, 147, 0.1024, -42):
                cycle.feed(frame)
            cycle.mark_sleep(1016.7)
            cycle.feed(heard(1021.5, 1, 1.0, -44)[0])
            return beacon

        result, calls, one = self.wifi_ap(feed, args=["--timeout", "30"])
        self.assertEqual(result.code, EXIT_OK, result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("15", "15", "first boot: on the air 15.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("5", "5", "first boot: off the air 5.0 s", "pass"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("20", "-", "first boot: 21.5 s", "pass"))
        self.assertIn("judging the first boot with wider tolerances (--timeout 30 covers one cycle of 20 s plus the "
                      "5 s boot allowance; two cycles need 45)\n", result.out)
        self.assertIn("with wlan1 through the first sleep\n", result.out)
        self.assertNotIn("first wake:", result.out)
        self.assertTrue(result.summary.startswith("pass: 8 pass, 0 FAIL, 3 serial only, 0 unverified"), result.summary)
        self.assertEqual(result.suggestion, "run with --timeout 45 for the exact cycle time; this run judged the "
                                            "first boot with wider tolerances")

    def test_wifi_easy_ap_timers_stay_serial_only_when_the_budget_is_short(self):
        def feed(cycle, follower, random_channel, beacon):
            self.assertFalse(cycle.measure)
            self.assertIsNone(follower)
            cycle.feed(heard(1001.5, 1, 1.0, -42)[0])
            return beacon

        result, calls, one = self.wifi_ap(feed, args=["--timeout", "24"])
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertEqual(calls[2], ("wait", "F2:F4:90:22:0D:0F", True, False, False))
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("15", "15", "-", "serial only"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("5", "5", "-", "serial only"))
        self.assertNotIn("CYCLE_TIME", result.out)
        self.assertEqual(rows["TXPOWER"][3], "median -42 dBm over 1 frame")
        self.assertEqual(result.notes, [])
        self.assertIn("TIME_TO_WAKE and TIME_TO_SLEEP serial only (--timeout 24 is under the 45 s needed to "
                      "measure the cycle time: two cycles of 20 s plus the 5 s boot allowance)\n", result.out)
        self.assertIn("first transmission: 1.5 s after reset\n", result.out)
        self.assertNotIn("through the first", result.out)
        self.assertTrue(result.summary.startswith("pass: 5 pass, 0 FAIL, 5 serial only, 0 unverified"), result.summary)
        self.assertEqual(result.suggestion, "run with --timeout 45 to measure the cycle time")

    def wifi_transcript(self, text):
        """A temporary transcript file with ``text``."""
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as handle:
            handle.write(text)
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_wifi_early_line_starts_the_capture_before_the_readback_is_complete(self):
        """The lines arrive 0.1 s apart on the replay clock: the capture starts
        the moment Starting on channel is read, before the banner and the
        Operating channel readback, and the first transmission counts from
        there."""
        from foxverify.tests.test_serial_fox import timed
        text = read_fixture("transcripts", "wifi_easy_ap.log")
        moments = {}

        def prepare(one):
            one.source = serial_fox.TranscriptSource([], clock=one.clock)
            one.read_fox = lambda selection: serial_fox.read_fox(
                serial_fox.TranscriptSource(timed(text, first=1.0, step=0.1), clock=one.clock), one.deadline,
                wall=one.wall, on_field=one.on_field)
            original = one.start_capture

            def start_capture(channel):
                moments["tuned"] = one.clock.now
                original(channel)

            one.start_capture = start_capture

        def feed(cycle, follower, random_channel, beacon):
            self.assertIsNone(follower)
            moments["wait"] = cycle.clock()
            cycle.feed(heard(1004.5, 1, 1.0, -42)[0])
            return beacon

        result, calls, one = self.wifi_ap(feed, args=["--timeout", "24", "-v"], prepare=prepare)
        self.assertEqual(result.code, EXIT_OK, result.out)
        # The first line is due 1.0 s after the reset at 1000 and the rest
        # 0.1 s apart, so the early line is due at its index in the fixture.
        lines = text.splitlines()
        self.assertAlmostEqual(moments["tuned"], 1001.0 + 0.1 * lines.index("Starting on channel 1"), delta=0.01)
        self.assertAlmostEqual(one.tuned.when, moments["tuned"])
        self.assertLess(one.tuned.when, one.cycle.radio_time)
        self.assertGreater(moments["wait"], one.cycle.radio_time)
        self.assertEqual(one.tuned.label, "Starting on channel")
        self.assertEqual(one.cycle.listen_time, one.tuned.when)
        self.assertEqual(calls[:2], [("monitor", "wlan1"), ("capture", "wlan1", WIFI_HEADER_MACS, 1, "/usr/bin/tshark")])
        self.assertIn("tuning wlan1 to channel 1 on the fox's Starting on channel line\n", result.out)
        self.assertIn("first transmission: 4.5 s after reset\n", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["CHANNEL"][1:], ("1", "1", "1", "pass"))

    def test_wifi_without_the_early_line_tunes_on_the_readback(self):
        """A host that missed the Starting on channel line: the capture starts
        after the readback, on the Operating channel line, as before."""
        text = read_fixture("transcripts", "wifi_easy_ap.log").replace("Starting on channel 1\n", "")
        self.assertNotIn("Starting on channel", text)

        def feed(cycle, follower, random_channel, beacon):
            cycle.feed(heard(1001.5, 1, 1.0, -42)[0])
            return beacon

        result, calls, one = self.wifi_ap(feed, args=["--timeout", "24", "-v"], transcript=self.wifi_transcript(text))
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertEqual(calls, [("monitor", "wlan1"), ("capture", "wlan1", WIFI_HEADER_MACS, 1, "/usr/bin/tshark"),
                                 ("wait", "F2:F4:90:22:0D:0F", True, False, False), ("closed",), ("restored", "wlan1")])
        self.assertEqual(one.tuned.label, "Operating channel")
        self.assertIn("tuning wlan1 to channel 1 on the fox's Operating channel line\n", result.out)
        self.assertNotIn("Starting on channel", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["CHANNEL"][1:], ("1", "1", "1", "pass"))

    def test_wifi_early_line_and_readback_disagreeing_fails_the_channel_row(self):
        """The capture follows the early line; a readback that then names
        another channel FAILs the CHANNEL row with both values shown."""
        text = read_fixture("transcripts", "wifi_easy_ap.log").replace("Starting on channel 1\n", "Starting on channel 6\n")

        def feed(cycle, follower, random_channel, beacon):
            cycle.feed(heard(1001.5, 1, 1.0, -42)[0])
            return beacon

        result, calls, one = self.wifi_ap(feed, args=["--timeout", "24"], transcript=self.wifi_transcript(text))
        self.assertEqual(result.code, EXIT_FAIL, result.out)
        self.assertEqual(calls[1][3], 6)
        self.assertIn("listening for beacons from F2:F4:90:22:0D:0F on channel 6 with wlan1", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["CHANNEL"][1:], ("1", "1 (Starting on channel 6)", "1", "FAIL"))
        self.assertEqual(rows["MAC_ADDR"][4], "pass")
        self.assertTrue(result.summary.startswith("FAIL: 4 pass, 1 FAIL"), result.summary)

    def test_wifi_client_never_tunes_early(self):
        """A client fox prints no Starting on channel line and its Setting up
        line names the client, so nothing starts before the readback."""
        from foxverify import wifi
        from contextlib import contextmanager

        @contextmanager
        def monitor_mode(name, *args, **kwargs):
            yield wifi.InterfaceState(name, "managed", True)

        def observe_client(interface, mac, ssid, channels, deadline, tshark_path, run=None, popen=None,
                           dwell=None, debug=None, cycle=None, follower=None):
            cycle.feed(heard(1001.0, 1, 1.0, -38)[0])
            return wifi.Probes(mac, 2, [None, ssid], [6], 1.0)

        with mock.patch.object(wifi, "observe_client", observe_client), \
                mock.patch.object(wifi, "monitor_mode", monitor_mode), \
                mock.patch.object(wifi, "ApCapture", side_effect=AssertionError("a client has no capture to start")):
            out = io.StringIO()
            one = run.WifiRun("wifi_ap_client", run.parse_args(
                "wifi_ap_client", ["--transcript", fixture("transcripts", "wifi_easy_client.log"),
                                   "--header", frozen_header("wifi_ap_client")]), out)
            one.serial_only = False
            one.tshark = "tshark"
            one.start_air = lambda selection, candidates: "wlan1"
            code = one.run()
        self.assertEqual(code, EXIT_OK, out.getvalue())
        self.assertIsNone(one.tuned)
        self.assertIsNone(one.capture)

    def test_wifi_first_transmission_over_the_allowance(self):
        def feed(cycle, follower, random_channel, beacon):
            for frame in heard(1006.2, 147, 0.1024, -42):
                cycle.feed(frame)
            cycle.mark_sleep(1021.4)
            cycle.feed(heard(1026.2, 1, 1.0, -44)[0])
            return beacon

        result, calls, one = self.wifi_ap(feed, args=["--timeout", "30"])
        self.assertIn("first transmission: 6.2 s after reset, over the 5 s boot allowance\n", result.out)
        self.assertEqual(result.code, EXIT_OK, result.out)

    def test_wifi_wake_2_not_heard_is_a_fail(self):
        def feed(cycle, follower, random_channel, beacon):
            for frame in heard(1001.5, 147, 0.1024, -42):
                cycle.feed(frame)
            cycle.mark_sleep(1016.7)
            return beacon

        result, calls, one = self.wifi_ap(feed, args=["--timeout", "30"])
        self.assertEqual(result.code, EXIT_FAIL, result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][4], "pass")
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("5", "5", "wake 2 not heard before the deadline", "FAIL"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("20", "-", "wake 2 not heard before the deadline", "FAIL"))
        self.assertTrue(result.summary.startswith("FAIL: 6 pass, 2 FAIL, 3 serial only, 0 unverified"), result.summary)

    def test_wifi_wake_3_not_heard_is_a_fail(self):
        def feed(cycle, follower, random_channel, beacon):
            for frame in heard(1001.5, 147, 0.1024, -42):
                cycle.feed(frame)
            cycle.mark_sleep(1016.7)
            for frame in heard(1021.5, 147, 0.1024, -42):
                cycle.feed(frame)
            cycle.mark_sleep(1036.7)
            return beacon

        result, calls, one = self.wifi_ap(feed)
        self.assertEqual(result.code, EXIT_FAIL, result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("15", "15", "on the air 15.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("5", "5", "wake 3 not heard before the deadline", "FAIL"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("20", "-", "wake 3 not heard before the deadline", "FAIL"))
        self.assertIn("first wake: on the air 15.0 s, then off the air 5.0 s, cycle time 21.5 s\n", result.out)
        self.assertTrue(result.summary.startswith("FAIL: 6 pass, 2 FAIL, 3 serial only, 0 unverified"), result.summary)

    def test_wifi_random_channel_wake_2(self):
        """The HARD AP picks a channel every wake: observe_ap is told so and
        gets the follower; a retune without a frame and a channel never read
        from serial are both FAILs with their texts."""
        def retuned_but_silent(cycle, follower, random_channel, beacon):
            self.assertTrue(random_channel)
            self.assertTrue(follower.reopen)
            # 30/45 at --timeout 90: one cycle (80 s) fits, two (155 s) do not.
            self.assertEqual(cycle.tier, "one cycle")
            for frame in heard(1001.5, 293, 0.1024, -61):
                cycle.feed(frame)
            cycle.mark_sleep(1031.7)
            cycle.retunes[2] = (9, 1079.0)
            return beacon._replace(bssid="F2:72:C1:79:16:1B", ds_channel=7, ht_channel=7, frequency=2442,
                                   ssid="Demo YT WiFi AP Hard Fox")

        result, calls, one = self.wifi_ap(retuned_but_silent, args=["--timeout", "90"], transcript="wifi_hard_ap.log")
        self.assertEqual(result.code, EXIT_FAIL, result.out)
        self.assertEqual(calls[1][2:4], (WIFI_HEADER_MACS, 7))
        self.assertEqual(calls[2][1], "F2:72:C1:79:16:1B")
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["CHANNEL"][1:], ("random", "7", "7", "pass"))
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("30", "30", "first boot: on the air 29.9 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:],
                         ("45", "45", "wake 2 not heard on channel 9 after retuning at +79.0 s", "FAIL"))
        self.assertEqual(rows["CYCLE_TIME"][1:],
                         ("75", "-", "wake 2 not heard on channel 9 after retuning at +79.0 s", "FAIL"))
        self.assertEqual(result.suggestion, "run with --timeout 155 for the exact cycle time; this run judged the "
                                            "first boot with wider tolerances")

        def channel_never_seen(cycle, follower, random_channel, beacon):
            for frame in heard(1001.5, 293, 0.1024, -61):
                cycle.feed(frame)
            cycle.mark_sleep(1031.7)
            return beacon._replace(bssid="F2:72:C1:79:16:1B", ds_channel=7, ht_channel=7, frequency=2442,
                                   ssid="Demo YT WiFi AP Hard Fox")

        result, calls, one = self.wifi_ap(channel_never_seen, args=["--timeout", "90"], transcript="wifi_hard_ap.log")
        self.assertEqual(result.code, EXIT_FAIL, result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_SLEEP"][1:],
                         ("45", "45", "wake 2 not heard: its channel was not seen on serial", "FAIL"))

    def test_wifi_random_channel_follower_reopens_and_retunes_through_the_real_loop(self):
        """The real wait_for_beacon loop against a fake tshark reader and the
        replay's own serial source at --timeout 160, two cycles of the 30/45
        HARD AP: the port vanishes at each sleep and comes back for the next
        wake, whose channel line retunes the card; wake 3's Last cycle line
        fills CYCLE_TIME's serial column and the run ends at wake 3's first
        beacon."""
        from foxverify import wifi
        from foxverify.tests import read_fixture
        from foxverify.tests.fakes import FakeReader
        from foxverify.tests.test_serial_fox import Vanishing
        line = read_fixture("tshark", "ap_beacons.tsv").splitlines()[1]
        runs = []

        def beacon_line(when):
            """A beacon from the HARD fox on channel 7, visible SSID."""
            cells = line.split("\t")
            cells[0] = "%.6f" % when
            cells[4] = "Demo YT WiFi AP Hard Fox"
            cells[5] = cells[6] = "7"
            cells[7] = "2442"
            return "\t".join(cells)

        class VanishingTwice(Vanishing):
            """Gone at ``gone_at`` and again at ``again_at``, each time for
            ``away`` seconds."""

            def __init__(self, items, clock, gone_at, away, again_at):
                Vanishing.__init__(self, items, clock, gone_at, away)
                self.away = away
                self.again_at = again_at

            def read(self, timeout):
                if self.vanished and not self.gone and self.again_at is not None and self.clock() >= self.again_at:
                    self.gone = True
                    self.back_at = self.again_at + self.away
                    self.again_at = None
                    raise serial_fox.PortGone("gone again")
                return Vanishing.read(self, timeout)

        tuned = []

        class RealLoopCapture:
            """wifi.ApCapture over a fake tshark reader, its wait the real loop."""

            def __init__(self, interface, bssids, channel, tshark_path, run=None, popen=None, debug=None):
                one = runs[0]
                clock = one.clock
                self.debug = debug
                # Beacons every 0.5 s for 30 s from 1.5 s after the reset; wake
                # 2 and wake 3 each begin 75 s after the wake before.
                items = [(1001.5 - clock.now, beacon_line(1001.5))] + [(0.5, beacon_line(1001.5 + 0.5 * i)) for i in range(1, 61)]
                items += [(45.0, beacon_line(1076.5))] + [(0.5, beacon_line(1076.5 + 0.5 * i)) for i in range(1, 61)]
                items += [(45.0, beacon_line(1151.5)), (0.5, beacon_line(1152.0))]
                self.reader = FakeReader(wifi.AP_FIELDS, items, clock)
                tuned.append(channel)

            def wait(self, bssid, deadline, cycle=None, follower=None, random_channel=False):
                return wifi.wait_for_beacon(self.reader, bssid, deadline, self.debug, cycle=cycle, follower=follower,
                                            retune=tuned.append if random_channel else None)

            def close(self):
                pass

        def prepare(one):
            runs.append(one)
            # Wake 2's lines once the port is back, its early channel line
            # caught before its banner, its sleep line after its last beacon
            # at 1106.5, then wake 3's lines after the second reopen, with
            # the early line missed and only the readback naming its channel.
            lines = [(1075.0 - 1000.0, "Initializing...\n"), (0.1, "Starting on channel 9\n"),
                     (0.2, "Fox: wifi_ap_client HARD AP\n"), (1.0, "Operating channel: 9\n"),
                     (1106.7 - 1076.3, "Going to sleep\n"),
                     (1150.0 - 1106.7, "Initializing...\n"), (0.1, "Last cycle: 75.0s, target 75s\n"),
                     (0.1, "Fox: wifi_ap_client HARD AP\n"), (0.1, "Operating channel: 4\n")]
            one.source = VanishingTwice(lines, one.clock, gone_at=1031.8, away=40.0, again_at=1107.3)
            # The readback is replayed without the hook, so wake 1's capture
            # starts after it, on the Operating channel line.
            one.read_fox = lambda selection: serial_fox.read_fox(
                serial_fox.TranscriptSource.from_file(fixture("transcripts", "wifi_hard_ap.log"), clock=one.clock),
                one.deadline, wall=one.wall)

        from contextlib import contextmanager

        @contextmanager
        def monitor_mode(name, *a, **kw):
            yield wifi.InterfaceState(name, "managed", True)

        with mock.patch.object(wifi, "ApCapture", RealLoopCapture), mock.patch.object(wifi, "monitor_mode", monitor_mode):
            out = io.StringIO()
            one = run.WifiRun("wifi_ap_client", run.parse_args(
                "wifi_ap_client", ["--timeout", "160", "-v", "--transcript", fixture("transcripts", "wifi_hard_ap.log"),
                                   "--header", frozen_header("wifi_ap_client")]), out)
            one.serial_only = False
            one.tshark = "tshark"
            one.start_air = lambda selection, candidates: "wlan1"
            prepare(one)
            code = one.run()
        text = out.getvalue()
        self.assertEqual(code, EXIT_OK, text)
        self.assertEqual(tuned, [7, 9, 4])
        self.assertEqual(one.tuned.label, "Operating channel")
        self.assertIn("tuning wlan1 to channel 7 on the fox's Operating channel line\n", text)
        rows = {row[0]: row for row in table_rows(text)}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("30", "30", "on the air 30.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("45", "45", "off the air 45.0 s", "pass"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("75", "75.0", "75.0 s", "pass"))
        self.assertEqual(one.source.reopens, 2)
        self.assertEqual((one.cycle.retunes[2][0], one.cycle.retunes[3][0]), (9, 4))
        # Wake 2 was retuned on its early line, before its readback arrived.
        self.assertLess(one.cycle.retunes[2][1], 1076.3)
        self.assertEqual(len(one.cycle.sleep_times), 2)
        self.assertIn("first wake: on the air 30.0 s, then off the air 45.0 s, cycle time 76.5 s\n", text)
        self.assertIn("wake 2 is on channel 9 by its Starting on channel line, retuning", text)
        self.assertIn("wake 3 is on channel 4 by its Operating channel line, retuning", text)
        self.assertLess(one.clock.now, 1153.0)

    def test_wifi_client_hops_the_header_channels(self):
        from foxverify import wifi
        from contextlib import contextmanager
        calls = []

        def observe_client(interface, mac, ssid, channels, deadline, tshark_path, run=None, popen=None,
                           dwell=None, debug=None, cycle=None, follower=None):
            calls.append((interface, mac, ssid, list(channels), cycle.measure, follower is None))
            cycle.feed(heard(1001.0, 1, 1.0, -38)[0])
            return wifi.Probes(mac, 2, [None, ssid], [6], 1.0)

        @contextmanager
        def monitor_mode(name, *args, **kwargs):
            yield wifi.InterfaceState(name, "managed", True)

        with mock.patch.object(wifi, "observe_client", observe_client), mock.patch.object(wifi, "monitor_mode", monitor_mode):
            out = io.StringIO()
            one = run.WifiRun("wifi_ap_client", run.parse_args(
                "wifi_ap_client", ["--transcript", fixture("transcripts", "wifi_hard_client.log"),
                                   "--header", frozen_header("wifi_ap_client")]), out)
            one.serial_only = False
            one.tshark = "tshark"
            one.start_air = lambda selection, candidates: "wlan1"
            code = one.run()
        self.assertEqual(code, EXIT_OK, out.getvalue())
        # 300/0 needs 305 s: not measured at 60, no follower.
        self.assertEqual(calls, [("wlan1", "F2:83:27:31:80:C7", "Demo Mr Lee WiFi Client Hard Fox", list(range(1, 12)),
                                  False, True)])
        rows = {row[0]: row for row in table_rows(out.getvalue())}
        self.assertEqual(rows["MAC_ADDR"][4], "pass")
        self.assertEqual(rows["FSSID"][4], "pass")
        self.assertEqual(rows["TXPOWER"][3], "median -38 dBm over 1 frame")
        self.assertIn("TIME_TO_WAKE and TIME_TO_SLEEP serial only (--timeout 60 is under the 605 s needed to "
                      "measure the cycle time: two cycles of 300 s plus the 5 s boot allowance)\n", out.getvalue())
        self.assertNotIn("note:", out.getvalue())
        self.assertIn("hopping 11 channels at 3 s each, a 33 s sweep; a client scans every channel for its "
                      "network about every 1 s\n", out.getvalue())
        self.assertTrue(out.getvalue().endswith("run with --timeout 605 to measure the cycle time\n"), out.getvalue())

    def test_zigbee_pass_and_interval_budget(self):
        from foxverify import tshark, zigbee
        from foxverify.tests import read_fixture
        frames = read_fixture("tshark", "zigbee_frames.tsv").splitlines()
        link = [zigbee.parse_frame(tshark.parse_line(frames[i], zigbee.FIELDS)) for i in (2, 3)]
        calls = []

        def collect(channel, pan_id, want_link_status, cycle, follower, random_channel, mac):
            calls.append(("collect", channel, pan_id, want_link_status, cycle.measure, follower is None,
                          random_channel, mac))
            for frame in link[:want_link_status]:
                cycle.feed(frame.heard())
            return zigbee.Observation(link[:want_link_status], link[:want_link_status])

        with mock.patch.object(zigbee, "Capture", fake_zigbee_capture(calls, collect)):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", fixture("transcripts", "zigbee_easy.log"),
                                lambda candidates: "/dev/ttyACM3", args=["-v"],
                                prepare=lambda one: setattr(one, "tshark", "/usr/bin/tshark"))
            self.assertEqual(result.code, EXIT_OK, result.out)
            # The capture started on the Starting on channel line and was read
            # once the readback named the PAN ID and the block the MAC.
            self.assertEqual(calls, [("capture", "/dev/ttyACM3", 15, "/usr/bin/tshark"),
                                     ("collect", 15, 0x1337, 2, False, True, False, "F2:5A:3C:91:0E:7B:44:D8"),
                                     ("closed",)])
            self.assertIn("tuning /dev/ttyACM3 to channel 15 on the fox's Starting on channel line\n", result.out)
            self.assertEqual([v for _, v in result.verdicts],
                             ["pass"] * 5 + ["serial only"] * 4)
            self.assertIn("listening on channel 15 with /dev/ttyACM3 for two Link Status frames\n", result.out)
            rows = {row[0]: row for row in result.rows}
            self.assertEqual(rows["TXPOWER"][1:], ("20", "20", "median -46 dBm over 2 frames", "serial only"))
            self.assertEqual(rows["EXT_PAN_ID"][1:], ("F2:5A:3C:91:0E:7B:44:D8", "F2:5A:3C:91:0E:7B:44:D8", "-", "serial only"))
            self.assertIn("| serial only: unable to trigger\n", result.out)
            self.assertNotIn("beacon", result.out)
            self.assertEqual(result.notes, [])
            self.assertIn("TIME_TO_WAKE and TIME_TO_SLEEP serial only (--timeout 60 is under the 605 s needed to "
                          "measure the cycle time: two cycles of 300 s plus the 5 s boot allowance)\n", result.out)
            self.assertEqual(result.suggestion, "run with --timeout 605 to measure the cycle time")
            # The run ended with the identity rows, long before the deadline.
            self.assertTrue(result.summary.endswith(" s of 60 s"), result.summary)
            self.assertLess(elapsed(result), 5.0)
            del calls[:]
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", fixture("transcripts", "zigbee_easy.log"),
                                lambda candidates: "/dev/ttyACM3", args=["--timeout", "3"])
            self.assertEqual(calls[1][3], 1)
            self.assertIn("for one Link Status frame", result.out)
            rows = {row[0]: row for row in result.rows}
            self.assertEqual(rows["PACKET_INTERVAL"][4], "unverified")
            self.assertIn("two Link Status frames need up to 4 s, 2 s left", result.out)
            self.assertEqual(rows["MAC_ADDR"][4], "pass")
            self.assertEqual(result.code, EXIT_OK)

    def test_zigbee_time_to_sleep_zero_measured_at_305(self):
        from foxverify import tshark, zigbee
        from foxverify.tests import read_fixture
        frames = read_fixture("tshark", "zigbee_frames.tsv").splitlines()
        link = [zigbee.parse_frame(tshark.parse_line(frames[i], zigbee.FIELDS)) for i in (2, 3)]

        def collect(channel, pan_id, want_link_status, cycle, follower, random_channel, mac):
            self.assertEqual(cycle.tier, "one cycle")
            self.assertIsNotNone(follower)
            self.assertTrue(follower.reopen)
            # The owner's first boot: the capture starts 15 s after the reset
            # at 1000 and hears the fox at once, every second to 300 s; the
            # fox reboots at once and is back 1.8 s later.
            cycle.listen_time = 1015.0
            for frame in heard(1015.0, 286, 1.0, -45):
                cycle.feed(frame)
            cycle.mark_sleep(1300.4)
            cycle.feed(heard(1301.8, 1, 1.0, -45)[0])
            return zigbee.Observation(link, link)

        with mock.patch.object(zigbee, "Capture", fake_zigbee_capture([], collect)):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", fixture("transcripts", "zigbee_easy.log"),
                                lambda candidates: "/dev/ttyACM3", args=["--timeout", "305"])
        self.assertEqual(result.code, EXIT_OK, result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("300", "300", "first boot: on the air 285.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("0", "0", "first boot: off the air 1.8 s", "pass"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("300", "-", "first boot: 301.8 s", "pass"))
        self.assertEqual(rows["EXT_PAN_ID"][4], "serial only")
        self.assertEqual([v for v, _ in result.verdicts],
                         ["MAC_ADDR", "CHANNEL", "PAN_ID", "SHORT_ADDR", "PACKET_INTERVAL", "EXT_PAN_ID",
                          "TIME_TO_WAKE", "TIME_TO_SLEEP", "CYCLE_TIME", "TXPOWER"])
        self.assertIn("judging the first boot with wider tolerances (--timeout 305 covers one cycle of 300 s plus the "
                      "5 s boot allowance; two cycles need 605)\n", result.out)
        self.assertIn("for two Link Status frames and through the first sleep\n", result.out)
        self.assertIn("first transmission: by 15.0 s after reset (the sniffer started listening at 15.0 s; "
                      "the radio was up at", result.out)
        self.assertNotIn("first wake:", result.out)
        self.assertEqual(result.notes, [])
        self.assertEqual(result.suggestion, "run with --timeout 605 for the exact cycle time; this run judged the "
                                            "first boot with wider tolerances")

    def test_zigbee_time_to_sleep_zero_two_cycles_at_605(self):
        """The owner's board at --timeout 605: wake 1 goes into the first wake
        line, wake 2 is on the air the full 300 s, wake 3 comes 302.1 s after
        wake 2's first frame, within TIME_TO_WAKE + 5 + 3 for a TIME_TO_SLEEP
        0 fox, and the run ends there."""
        from foxverify import tshark, zigbee
        from foxverify.tests import read_fixture
        frames = read_fixture("tshark", "zigbee_frames.tsv").splitlines()
        link = [zigbee.parse_frame(tshark.parse_line(frames[i], zigbee.FIELDS)) for i in (2, 3)]

        def collect(channel, pan_id, want_link_status, cycle, follower, random_channel, mac):
            self.assertEqual(cycle.tier, "two cycles")
            self.assertTrue(follower.reopen)
            cycle.listen_time = 1015.0
            for frame in heard(1015.0, 286, 1.0, -45):
                cycle.feed(frame)
            cycle.mark_sleep(1300.4)
            for frame in heard(1301.8, 301, 1.0, -45):
                cycle.feed(frame)
            cycle.mark_sleep(1602.1)
            cycle.feed(heard(1603.9, 1, 1.0, -45)[0])
            return zigbee.Observation(link, link)

        with mock.patch.object(zigbee, "Capture", fake_zigbee_capture([], collect)):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", fixture("transcripts", "zigbee_easy.log"),
                                lambda candidates: "/dev/ttyACM3", args=["--timeout", "605"])
        self.assertEqual(result.code, EXIT_OK, result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("300", "300", "on the air 300.0 s", "pass"))
        self.assertEqual(rows["TIME_TO_SLEEP"][1:], ("0", "0", "off the air 2.1 s", "pass"))
        self.assertEqual(rows["CYCLE_TIME"][1:], ("300", "-", "302.1 s", "pass"))
        self.assertIn("measuring the cycle time from wake 2 and wake 3 (--timeout 605 covers two cycles of 300 s plus "
                      "the 5 s boot allowance)\n", result.out)
        self.assertIn("for two Link Status frames and through the first two sleeps\n", result.out)
        self.assertIn("first wake: on the air 285.0 s, then off the air 1.8 s, cycle time 301.8 s\n", result.out)
        self.assertTrue(result.summary.startswith("pass: 8 pass, 0 FAIL, 2 serial only, 0 unverified"), result.summary)
        self.assertIsNone(result.suggestion)

    def test_halted_fox_is_not_listened_for(self):
        """The fox named its channel, so the capture started, and then halted
        on its readback: nothing is read from the capture and it is closed."""
        from foxverify import zigbee
        calls = []

        def collect(*args):
            raise AssertionError("collect must not run")

        with mock.patch.object(zigbee, "Capture", fake_zigbee_capture(calls, collect)):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", fixture("transcripts", "zigbee_easy_mismatch.log"),
                                lambda candidates: "/dev/ttyACM3")
        self.assertEqual(result.code, EXIT_FAIL)
        self.assertEqual([call[0] for call in calls], ["capture", "closed"])
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["PAN_ID"][4], "FAIL")
        self.assertEqual(rows["MAC_ADDR"][4:], ("unverified",))
        self.assertIn("unverified: the fox halted", result.out)
        self.assertNotIn("first transmission", result.out)
        self.assertEqual(len(result.notes), 1)

    def test_zigbee_without_a_channel_on_serial(self):
        from foxverify import zigbee
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as handle:
            handle.write("Fox: zigbee_coordinator EASY\nDevice address: F2:5A:3C:91:0E:7B:44:D8\n")
        self.addCleanup(os.unlink, handle.name)
        with mock.patch.object(zigbee, "Capture", side_effect=AssertionError("no capture without a channel")):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", handle.name, lambda candidates: "/dev/ttyACM3")
        self.assertEqual(result.code, EXIT_FAIL)
        self.assertIn("unverified: the fox did not print its channel", result.out)
        self.assertIn("FAIL: not printed on serial", result.out)

    def zigbee_transcript(self, text):
        """A temporary transcript file with ``text``."""
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as handle:
            handle.write(text)
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_zigbee_without_the_early_line_tunes_on_the_readback(self):
        """A native USB host that missed the Starting on channel line: the
        capture starts after the readback, on the Operating channel line, as
        it did before the early line existed."""
        from foxverify import tshark, zigbee
        from foxverify.tests import read_fixture
        frames = read_fixture("tshark", "zigbee_frames.tsv").splitlines()
        link = [zigbee.parse_frame(tshark.parse_line(frames[i], zigbee.FIELDS)) for i in (2, 3)]
        text = read_fixture("transcripts", "zigbee_easy.log").replace("Starting on channel 15\n", "")
        self.assertNotIn("Starting on channel", text)
        calls = []

        def collect(channel, pan_id, want_link_status, cycle, follower, random_channel, mac):
            calls.append(("collect", channel, pan_id, mac))
            for frame in link:
                cycle.feed(frame.heard())
            return zigbee.Observation(link, link)

        with mock.patch.object(zigbee, "Capture", fake_zigbee_capture(calls, collect)):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", self.zigbee_transcript(text),
                                lambda candidates: "/dev/ttyACM3", args=["-v"],
                                prepare=lambda one: setattr(one, "tshark", "/usr/bin/tshark"))
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertEqual(calls, [("capture", "/dev/ttyACM3", 15, "/usr/bin/tshark"),
                                 ("collect", 15, 0x1337, "F2:5A:3C:91:0E:7B:44:D8"), ("closed",)])
        self.assertIn("tuning /dev/ttyACM3 to channel 15 on the fox's Operating channel line\n", result.out)
        self.assertNotIn("Starting on channel", result.out)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["CHANNEL"][1:], ("15", "15", "15", "pass"))

    def test_zigbee_early_line_and_readback_disagreeing_fails_the_channel_row(self):
        """A fox that named one channel and read back another: the capture is
        on the early channel and the CHANNEL row FAILs showing both."""
        from foxverify import tshark, zigbee
        from foxverify.tests import read_fixture
        frames = read_fixture("tshark", "zigbee_frames.tsv").splitlines()
        link = [zigbee.parse_frame(tshark.parse_line(frames[i], zigbee.FIELDS)) for i in (2, 3)]
        text = read_fixture("transcripts", "zigbee_easy.log").replace("Starting on channel 15\n", "Starting on channel 20\n")
        calls = []

        def collect(channel, pan_id, want_link_status, cycle, follower, random_channel, mac):
            calls.append(("collect", channel))
            return zigbee.Observation(link, link)

        with mock.patch.object(zigbee, "Capture", fake_zigbee_capture(calls, collect)):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", self.zigbee_transcript(text),
                                lambda candidates: "/dev/ttyACM3")
        self.assertEqual(result.code, EXIT_FAIL, result.out)
        self.assertEqual(calls[0][2], 20)
        self.assertEqual(calls[1], ("collect", 20))
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["CHANNEL"][1:], ("15", "15 (Starting on channel 20)", "15", "FAIL"))
        self.assertIn("listening on channel 20 with /dev/ttyACM3", result.out)
        self.assertTrue(result.summary.startswith("FAIL: 4 pass, 1 FAIL"), result.summary)


class CommandLineTest(unittest.TestCase):
    def test_defaults_and_hidden_options(self):
        args = run.parse_args("iBeacon", [])
        self.assertEqual(args.devices, [])
        self.assertEqual(args.timeout, 60.0)
        self.assertEqual(args.wait_for_fox, 30.0)
        self.assertFalse(args.serial_only or args.no_reset or args.verbose)
        self.assertIsNone(args.header)
        args = run.parse_args("iBeacon", ["hci0", "/dev/ttyACM1", "--timeout", "45", "--serial-only"])
        self.assertEqual(args.devices, ["hci0", "/dev/ttyACM1"])
        self.assertEqual(args.timeout, 45.0)
        self.assertTrue(args.serial_only)

    def test_bad_values_are_rejected(self):
        for argv in (["--timeout", "0"], ["--wait-for-fox", "-1"], ["--bogus"]):
            with self.assertRaises(SystemExit) as caught:
                with mock.patch("sys.stderr", io.StringIO()):
                    run.parse_args("iBeacon", argv)
            self.assertEqual(caught.exception.code, 2, argv)

    def test_help_mentions_the_devices_and_exit_codes(self):
        out = io.StringIO()
        with self.assertRaises(SystemExit) as caught:
            with mock.patch("sys.stdout", out):
                run.parse_args("wifi_ap_client", ["--help"])
        self.assertEqual(caught.exception.code, 0)
        text = out.getvalue()
        for word in ("--serial-only", "--no-reset", "--timeout", "--wait-for-fox", "wlan1", "hci0",
                     "/dev/ttyACM1", "Exit 0", "monitor mode"):
            self.assertIn(word, text)
        self.assertNotIn("--transcript", text)
        self.assertNotIn("--header", text)

    def test_default_header_is_the_project_symlink(self):
        for project, directory in PROJECT_DIRS.items():
            one = run.RUNS[project](project, run.parse_args(project, []), io.StringIO())
            self.assertEqual(one.header_path, os.path.join(REPO, directory, "src", "current_conf.h"))
            self.assertFalse(one.serial_only)
            self.assertIs(one.clock, run.time.monotonic)

    def test_header_macs(self):
        macs = run.header_macs(frozen_text("iBeacon"))
        self.assertEqual(macs, ["F2:82:42:D0:84:BC", "F2:63:89:10:8D:1D", "F2:AC:87:05:0A:C7"])
        self.assertEqual(run.header_macs("#define X 1\n"), [])
        self.assertEqual(run.header_macs("#if defined(A)\n#define MAC_ADDR {0x100}\n#endif\n"), [])


class EntryPointTest(unittest.TestCase):
    """The four scripts exist, are executable and run a replay."""

    def test_scripts(self):
        import subprocess
        import sys
        for project, directory in PROJECT_DIRS.items():
            script = os.path.join(REPO, directory, "verify")
            self.assertTrue(os.access(script, os.X_OK), script)
            with open(script, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.readline(), "#!/usr/bin/env python3\n", script)
            transcript = {"classic_discoverable": "classic_easy", "iBeacon": "ibeacon_easy",
                          "wifi_ap_client": "wifi_easy_client", "zigbee_coordinator": "zigbee_easy"}[project]
            result = subprocess.run([sys.executable, script, "--transcript", fixture("transcripts", transcript + ".log"),
                                     "--header", frozen_header(project)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                    check=False, cwd="/")
            self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "", script)
            self.assertIn("MAC_ADDR", result.stdout)


if __name__ == "__main__":
    unittest.main()
