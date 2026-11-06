"""End-to-end serial-only runs of every project's verify through transcript
replay: the table rows, the notes, the exit codes and the not-a-fox outcomes.
The header is named explicitly so a concurrent qa script that repoints
current_conf.h cannot change what a test sees."""
import io
import os
import tempfile
import unittest
from unittest import mock

from foxverify import run, serial_fox
from foxverify.report import EXIT_FAIL, EXIT_NO_RUN, EXIT_OK
from foxverify.tests import REPO, fixture, project_header

PROJECT_DIRS = serial_fox.PROJECT_DIRS

# transcript -> (project, rows expected with their verdicts, in table order)
RUNS = {
    "classic_easy": ("classic_discoverable", [
        ("MAC_ADDR", "unverified"), ("NAME", "unverified"),
        ("TIME_TO_WAKE", "serial"), ("TIME_TO_SLEEP", "serial")]),
    "classic_hard": ("classic_discoverable", [
        ("MAC_ADDR", "unverified"), ("NAME", "unverified"),
        ("TIME_TO_WAKE", "serial"), ("TIME_TO_SLEEP", "serial")]),
    "ibeacon_easy": ("iBeacon", [
        ("MAC_ADDR", "unverified"), ("DEVICE_NAME", "unverified"), ("BEACON_UUID", "unverified"),
        ("MAJOR", "unverified"), ("MINOR", "unverified"), ("SIGNAL_POWER", "unverified")]),
    "ibeacon_medium": ("iBeacon", [
        ("MAC_ADDR", "unverified"), ("DEVICE_NAME", "unverified"), ("BEACON_UUID", "unverified"),
        ("MAJOR", "unverified"), ("MINOR", "unverified"), ("SIGNAL_POWER", "unverified")]),
    "ibeacon_hard": ("iBeacon", [
        ("MAC_ADDR", "unverified"), ("DEVICE_NAME", "unverified"), ("BEACON_UUID", "unverified"),
        ("MAJOR", "unverified"), ("MINOR", "unverified"), ("SIGNAL_POWER", "unverified")]),
    "wifi_easy_ap": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("FSSID", "unverified"),
        ("SSID_HIDDEN", "unverified"), ("SECURITY", "unverified"),
        ("PSK", "serial"), ("MAX_CLIENTS", "serial"), ("TIME_TO_WAKE", "serial"),
        ("TIME_TO_SLEEP", "serial"), ("TXPOWER", "serial")]),
    "wifi_hard_ap": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("FSSID", "unverified"),
        ("SSID_HIDDEN", "unverified"), ("SECURITY", "unverified"),
        ("PSK", "serial"), ("MAX_CLIENTS", "serial"), ("TIME_TO_WAKE", "serial"),
        ("TIME_TO_SLEEP", "serial"), ("TXPOWER", "serial")]),
    "wifi_fiveeasy_ap": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("FSSID", "unverified"),
        ("SSID_HIDDEN", "unverified"), ("SECURITY", "unverified"),
        ("PSK", "serial"), ("MAX_CLIENTS", "serial"), ("TIME_TO_WAKE", "serial"),
        ("TIME_TO_SLEEP", "serial"), ("TXPOWER", "serial")]),
    "wifi_fivehard_ap": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("FSSID", "unverified"),
        ("SSID_HIDDEN", "unverified"), ("SECURITY", "unverified"),
        ("PSK", "serial"), ("MAX_CLIENTS", "serial"), ("TIME_TO_WAKE", "serial"),
        ("TIME_TO_SLEEP", "serial"), ("TXPOWER", "serial")]),
    "wifi_easy_client": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("FSSID", "unverified"),
        ("PSK", "serial"), ("TIME_TO_WAKE", "serial"), ("TIME_TO_SLEEP", "serial"),
        ("TXPOWER", "serial")]),
    "wifi_hard_client": ("wifi_ap_client", [
        ("MAC_ADDR", "unverified"), ("FSSID", "unverified"),
        ("PSK", "serial"), ("TIME_TO_WAKE", "serial"), ("TIME_TO_SLEEP", "serial"),
        ("TXPOWER", "serial")]),
    "zigbee_easy": ("zigbee_coordinator", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("PAN_ID", "unverified"),
        ("SHORT_ADDR", "unverified"), ("PACKET_INTERVAL", "unverified"),
        ("EXT_PAN_ID", "serial"), ("TIME_TO_WAKE", "serial"), ("TIME_TO_SLEEP", "serial"),
        ("TXPOWER", "serial")]),
    "zigbee_hard": ("zigbee_coordinator", [
        ("MAC_ADDR", "unverified"), ("CHANNEL", "unverified"), ("PAN_ID", "unverified"),
        ("SHORT_ADDR", "unverified"), ("PACKET_INTERVAL", "unverified"),
        ("EXT_PAN_ID", "serial"), ("TIME_TO_WAKE", "serial"), ("TIME_TO_SLEEP", "serial"),
        ("TXPOWER", "serial")]),
}


def demo_header(project):
    return os.path.join(REPO, PROJECT_DIRS[project], "src", "conferences", "9999demo.h")


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
        self.summary = out.splitlines()[-1] if out else ""


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
    argv += ["--header", header or demo_header(project)]
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
                if verdict in ("unverified", "serial"):
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
        self.assertEqual(result.notes, ["advertising power -12 dBm (level 0), set in include/rfhsibeacon.h "
                                        "per difficulty, not a conference value"])

    def test_environment_variable_names_the_transcript(self):
        result = verify("classic_discoverable", fixture("transcripts", "classic_hard.log"), env_transcript=True)
        self.assertEqual(result.code, EXIT_OK, result.out + result.err)
        self.assertEqual(result.verdicts[2], ("TIME_TO_WAKE", "serial"))

    def test_serial_only_flag_and_no_reset_are_accepted(self):
        result = verify("zigbee_coordinator", fixture("transcripts", "zigbee_easy.log"),
                        args=["--serial-only", "--no-reset", "-v", "--timeout", "30", "--wait-for-fox", "0"])
        self.assertEqual(result.code, EXIT_OK, result.out + result.err)
        self.assertIn("unverified: --serial-only", result.out)
        self.assertIn("serial: Fox: zigbee_coordinator EASY", result.out)
        self.assertTrue(result.summary.endswith("s of 30 s"), result.summary)


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
        header = project_header("bluetooth/classic_discoverable").replace("#if defined(HARD)", "#if defined(NEVER)")
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
        header = project_header("bluetooth/classic_discoverable").replace(
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
        self.assertEqual(rows["TIME_TO_WAKE"][4], "serial")
        self.assertEqual(len(result.notes), 1)
        self.assertTrue(result.notes[0].startswith("the fox refused to run: Operating PAN ID != Requested PAN ID"))

    def test_changed_serial_only_value_fails(self):
        header = project_header("wifi/wifi_ap_client").replace("#define TIME_TO_WAKE 15", "#define TIME_TO_WAKE 20", 1)
        with tempfile.NamedTemporaryFile("w", suffix=".h", delete=False) as handle:
            handle.write(header)
        self.addCleanup(os.unlink, handle.name)
        result = verify("wifi_ap_client", fixture("transcripts", "wifi_easy_ap.log"), header=handle.name)
        self.assertEqual(result.code, EXIT_FAIL)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["TIME_TO_WAKE"][1:], ("20", "15", "-", "FAIL"))
        self.assertEqual(rows["TIME_TO_SLEEP"][4], "serial")


class FakeScan:
    """Stands in for btclassic.Inquiry and ble.BleScan: records the target and
    answers result() from a table."""

    def __init__(self, answer):
        self.answer = answer
        self.target = None
        self.stopped = False
        self.joined = False

    def set_target(self, address):
        self.target = address.upper()

    def result(self, deadline=None):
        return self.answer

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        self.joined = True


def air_run(cls, project, transcript, start_air, header=None, args=()):
    """A replayed run whose on-air step is replaced: ``start_air`` is called
    with the candidate MACs and returns the handle ``rows`` gets."""
    out = io.StringIO()
    argv = list(args) + ["--transcript", transcript, "--header", header or demo_header(project)]
    one = cls(project, run.parse_args(project, argv), out)
    one.serial_only = False
    one.air_reason = run.SERIAL_ONLY
    handles = []

    def fake_start_air(selection, candidates):
        handle = start_air(candidates)
        handles.append(handle)
        return handle

    one.start_air = fake_start_air
    code = one.run()
    return Result(code, out.getvalue(), ""), handles[0]


class AirRunTest(unittest.TestCase):
    """The on-air step of each project with the sniffer modules faked: the
    scan gets the block's MAC as its target once the banner is in, and the
    rows pass or fail on what the air reported."""

    def test_classic_pass(self):
        from foxverify import btclassic
        parser = btclassic.BtmgmtParser()
        parser.feed_text("hci0 dev_found: F2:F6:6D:BC:2A:80 type BR/EDR rssi -61 flags 0x0000\n"
                         "name Demo Case BTC Hard Fox\n")
        scan = FakeScan(parser)
        seen = []
        result, handle = air_run(run.ClassicRun, "classic_discoverable", fixture("transcripts", "classic_hard.log"),
                                 lambda candidates: seen.append(candidates) or scan)
        self.assertEqual(seen, [["F2:81:5A:C1:A3:26", "F2:F6:6D:BC:2A:80"]])
        self.assertEqual(scan.target, "F2:F6:6D:BC:2A:80")
        self.assertTrue(scan.stopped and scan.joined)
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertEqual(result.verdicts, [("MAC_ADDR", "pass"), ("NAME", "pass"),
                                           ("TIME_TO_WAKE", "serial"), ("TIME_TO_SLEEP", "serial")])
        self.assertTrue(result.summary.startswith("pass: 2 pass, 0 FAIL, 2 serial, 0 unverified"))

    def test_classic_no_answer_and_wrong_name(self):
        from foxverify import btclassic
        result, _ = air_run(run.ClassicRun, "classic_discoverable", fixture("transcripts", "classic_hard.log"),
                            lambda candidates: FakeScan(btclassic.BtmgmtParser()))
        self.assertEqual(result.code, EXIT_OK)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["MAC_ADDR"][4], "unverified")
        self.assertIn("no inquiry response from F2:F6:6D:BC:2A:80 before the deadline", result.out)
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
                                         "--header", demo_header("classic_discoverable")]), out)
            one.serial_only = False
            one.bluetoothctl = "/usr/bin/bluetoothctl"
            one.start_air = lambda selection, candidates: start_air(candidates)
            code = one.run()
        self.assertEqual(code, EXIT_OK, out.getvalue())
        self.assertEqual(asked, [("F2:F6:6D:BC:2A:80", "/usr/bin/bluetoothctl")])
        self.assertEqual(table_rows(out.getvalue())[1][4], "pass")

    def test_ibeacon_pass_and_fail(self):
        from foxverify import ble
        payload = bytes.fromhex("0215" "162EEB7B743C47E99414BBD6149B4E40" "0005" "0058" "C5")
        seen = {"F2:63:89:10:8D:1D": ble.Seen("F2:63:89:10:8D:1D", "Demo Cath BLE Medium Fox",
                                              ble.decode_ibeacon(payload), -50, 1.0)}
        scan = FakeScan(seen)
        result, _ = air_run(run.IBeaconRun, "iBeacon", fixture("transcripts", "ibeacon_medium.log"),
                            lambda candidates: scan)
        self.assertEqual(scan.target, "F2:63:89:10:8D:1D")
        self.assertEqual(result.code, EXIT_OK, result.out)
        self.assertEqual([v for _, v in result.verdicts], ["pass"] * 6)
        wrong = seen["F2:63:89:10:8D:1D"]._replace(beacon=ble.decode_ibeacon(payload)._replace(major=6))
        result, _ = air_run(run.IBeaconRun, "iBeacon", fixture("transcripts", "ibeacon_medium.log"),
                            lambda candidates: FakeScan({"F2:63:89:10:8D:1D": wrong}))
        self.assertEqual(result.code, EXIT_FAIL)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["MAJOR"][1:], ("5", "5", "6", "FAIL"))
        result, _ = air_run(run.IBeaconRun, "iBeacon", fixture("transcripts", "ibeacon_medium.log"),
                            lambda candidates: FakeScan({}))
        self.assertEqual(result.code, EXIT_OK)
        self.assertIn("unverified: F2:63:89:10:8D:1D not seen by the scan before the deadline", result.out)

    def test_wifi_ap_pass(self):
        from foxverify import tshark, wifi
        from foxverify.tests import read_fixture
        beacon = wifi.parse_beacon(tshark.parse_line(read_fixture("tshark", "ap_beacons.tsv").splitlines()[0],
                                                     wifi.AP_FIELDS))
        calls = []

        def observe_ap(interface, bssid, channel, deadline, tshark_path, run=None, popen=None, debug=None):
            calls.append((interface, bssid, channel, tshark_path))
            return beacon

        from contextlib import contextmanager

        @contextmanager
        def monitor_mode(name, *args, **kwargs):
            calls.append(("monitor", name))
            yield wifi.InterfaceState(name, "managed", True)
            calls.append(("restored", name))

        def start_air(candidates):
            return "wlan1"

        with mock.patch.object(wifi, "observe_ap", observe_ap), mock.patch.object(wifi, "monitor_mode", monitor_mode):
            out = io.StringIO()
            one = run.WifiRun("wifi_ap_client", run.parse_args(
                "wifi_ap_client", ["--transcript", fixture("transcripts", "wifi_easy_ap.log"),
                                   "--header", demo_header("wifi_ap_client")]), out)
            one.serial_only = False
            one.tshark = "/usr/bin/tshark"
            one.start_air = lambda selection, candidates: start_air(candidates)
            code = one.run()
        self.assertEqual(code, EXIT_OK, out.getvalue())
        self.assertEqual(calls, [("monitor", "wlan1"), ("wlan1", "F2:F4:90:22:0D:0F", 1, "/usr/bin/tshark"),
                                 ("restored", "wlan1")])
        rows = {row[0]: row for row in table_rows(out.getvalue())}
        self.assertEqual([rows[v][4] for v in ("MAC_ADDR", "CHANNEL", "FSSID", "SSID_HIDDEN", "SECURITY")], ["pass"] * 5)
        self.assertEqual(rows["SECURITY"][3], "WPA2-PSK/CCMP")
        self.assertEqual(rows["PSK"][4], "serial")
        self.assertIn("listening for beacons from F2:F4:90:22:0D:0F on channel 1 with wlan1", out.getvalue())

    def test_wifi_client_hops_the_header_channels(self):
        from foxverify import wifi
        from contextlib import contextmanager
        calls = []

        def observe_client(interface, mac, ssid, channels, deadline, tshark_path, run=None, popen=None,
                           dwell=None, debug=None):
            calls.append((interface, mac, ssid, list(channels)))
            return wifi.Probes(mac, 2, [None, ssid], [6], 1.0)

        @contextmanager
        def monitor_mode(name, *args, **kwargs):
            yield wifi.InterfaceState(name, "managed", True)

        with mock.patch.object(wifi, "observe_client", observe_client), mock.patch.object(wifi, "monitor_mode", monitor_mode):
            out = io.StringIO()
            one = run.WifiRun("wifi_ap_client", run.parse_args(
                "wifi_ap_client", ["--transcript", fixture("transcripts", "wifi_hard_client.log"),
                                   "--header", demo_header("wifi_ap_client")]), out)
            one.serial_only = False
            one.tshark = "tshark"
            one.start_air = lambda selection, candidates: "wlan1"
            code = one.run()
        self.assertEqual(code, EXIT_OK, out.getvalue())
        self.assertEqual(calls, [("wlan1", "F2:83:27:31:80:C7", "Demo Mr Lee WiFi Client Hard Fox", list(range(1, 12)))])
        rows = {row[0]: row for row in table_rows(out.getvalue())}
        self.assertEqual(rows["MAC_ADDR"][4], "pass")
        self.assertEqual(rows["FSSID"][4], "pass")

    def test_zigbee_pass_and_interval_budget(self):
        from foxverify import tshark, zigbee
        from foxverify.tests import read_fixture
        frames = read_fixture("tshark", "zigbee_frames.tsv").splitlines()
        link = [zigbee.parse_frame(tshark.parse_line(frames[i], zigbee.FIELDS)) for i in (2, 3)]
        calls = []

        def observe(sniffer, channel, deadline, tshark_path, pan_id=None, want_link_status=2, **kwargs):
            calls.append((sniffer, channel, tshark_path, pan_id, want_link_status))
            return zigbee.Observation(link[:want_link_status], link[:want_link_status])

        with mock.patch.object(zigbee, "observe", observe):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", fixture("transcripts", "zigbee_easy.log"),
                                lambda candidates: "/dev/ttyACM3")
            self.assertEqual(result.code, EXIT_OK, result.out)
            self.assertEqual(calls, [("/dev/ttyACM3", 15, None, 0x1337, 2)])
            self.assertEqual([v for _, v in result.verdicts],
                             ["pass"] * 5 + ["serial"] * 4)
            self.assertIn("listening on channel 15 with /dev/ttyACM3 for two Link Status frames", result.out)
            del calls[:]
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", fixture("transcripts", "zigbee_easy.log"),
                                lambda candidates: "/dev/ttyACM3", args=["--timeout", "3"])
            self.assertEqual(calls[0][4], 1)
            self.assertIn("for one Link Status frame", result.out)
            rows = {row[0]: row for row in result.rows}
            self.assertEqual(rows["PACKET_INTERVAL"][4], "unverified")
            self.assertIn("two Link Status frames need up to 4 s, 2 s left", result.out)
            self.assertEqual(rows["MAC_ADDR"][4], "pass")
            self.assertEqual(result.code, EXIT_OK)

    def test_halted_fox_is_not_listened_for(self):
        from foxverify import zigbee
        with mock.patch.object(zigbee, "observe", side_effect=AssertionError("observe must not run")):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", fixture("transcripts", "zigbee_easy_mismatch.log"),
                                lambda candidates: "/dev/ttyACM3")
        self.assertEqual(result.code, EXIT_FAIL)
        rows = {row[0]: row for row in result.rows}
        self.assertEqual(rows["PAN_ID"][4], "FAIL")
        self.assertEqual(rows["MAC_ADDR"][4:], ("unverified",))
        self.assertIn("unverified: the fox halted", result.out)

    def test_zigbee_without_a_channel_on_serial(self):
        from foxverify import zigbee
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as handle:
            handle.write("Fox: zigbee_coordinator EASY\nStarted Coordinator with MAC Address: F2:5A:3C:91:0E:7B:44:D8\n")
        self.addCleanup(os.unlink, handle.name)
        with mock.patch.object(zigbee, "observe", side_effect=AssertionError("observe must not run")):
            result, _ = air_run(run.ZigbeeRun, "zigbee_coordinator", handle.name, lambda candidates: "/dev/ttyACM3")
        self.assertEqual(result.code, EXIT_FAIL)
        self.assertIn("unverified: the fox did not print its channel", result.out)
        self.assertIn("FAIL: not printed on serial", result.out)


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
        macs = run.header_macs(project_header("bluetooth/iBeacon"))
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
                                     "--header", demo_header(project)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                    check=False, cwd="/")
            self.assertEqual(result.returncode, EXIT_OK, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "", script)
            self.assertIn("MAC_ADDR", result.stdout)


if __name__ == "__main__":
    unittest.main()
