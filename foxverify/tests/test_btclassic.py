import io
import unittest

from foxverify import btclassic, conf, report
from foxverify.report import RunError
from foxverify.serial_fox import parse_transcript
from foxverify.tests import project_header, read_fixture
from foxverify.tests.fakes import FakeLineReader, Recorder, deadline

HEADER = project_header("bluetooth/classic_discoverable")
WITH_NAME = read_fixture("btmgmt", "with_name.log")
WITHOUT_NAME = read_fixture("btmgmt", "without_name.log")
FOX = "F2:F6:6D:BC:2A:80"


class ParseTest(unittest.TestCase):
    def test_devices_with_names(self):
        found = {f.address: f for f in btclassic.parse_btmgmt(WITH_NAME)}
        self.assertEqual(set(found), {FOX, "70:10:5C:11:22:33"})
        fox = found[FOX]
        self.assertEqual(fox.type, "BR/EDR")
        self.assertEqual(fox.rssi, -61)
        self.assertEqual(fox.flags, "0x0000")
        self.assertEqual(fox.name, "Demo Case BTC Hard Fox")
        self.assertFalse(fox.short_name)
        self.assertEqual(found["70:10:5C:11:22:33"].name, "Kitchen speaker")

    def test_device_without_a_name_and_a_short_name(self):
        found = {f.address: f for f in btclassic.parse_btmgmt(WITHOUT_NAME)}
        self.assertIsNone(found[FOX].name)
        self.assertEqual(found[FOX].rssi, -58)
        self.assertEqual(found["70:10:5C:11:22:33"].name, "Kitchen spe")
        self.assertTrue(found["70:10:5C:11:22:33"].short_name)

    def test_second_response_keeps_an_earlier_name(self):
        parser = btclassic.BtmgmtParser()
        parser.feed_text(WITH_NAME)
        parser.feed("hci0 dev_found: F2:F6:6D:BC:2A:80 type BR/EDR rssi -70 flags 0x0000")
        self.assertEqual(parser.get("f2:f6:6d:bc:2a:80").name, "Demo Case BTC Hard Fox")
        self.assertEqual(parser.get(FOX).rssi, -70)

    def test_name_line_without_a_device_is_ignored(self):
        parser = btclassic.BtmgmtParser()
        self.assertIsNone(parser.feed("name stray"))
        self.assertIsNone(parser.feed("Discovery started"))

    def test_command_and_adapter_index(self):
        self.assertEqual(btclassic.btmgmt_command("/usr/bin/btmgmt", "hci1"),
                         ["/usr/bin/btmgmt", "--index", "1", "find", "-b"])
        with self.assertRaises(RunError):
            btclassic.adapter_index("wlan0")

    def test_info_name(self):
        text = "Device F2:F6:6D:BC:2A:80 (public)\n\tName: Demo Case BTC Hard Fox\n\tAlias: Demo Case BTC Hard Fox\n"
        self.assertEqual(btclassic.parse_info_name(text), "Demo Case BTC Hard Fox")
        self.assertIsNone(btclassic.parse_info_name("Device F2:F6:6D:BC:2A:80 not available\n"))


class InquiryTest(unittest.TestCase):
    def test_parser_completes_the_fox_at_its_name_line(self):
        dl, clock = deadline(60)
        lines = WITH_NAME.splitlines()
        reader = FakeLineReader([(1.0, line) for line in lines], clock)
        parser = btclassic.BtmgmtParser()
        found = None
        while not dl.expired():
            line = reader.read(dl.remaining())
            if line is None:
                break
            found = parser.feed(line)
            if found is not None and found.address == FOX and found.name is not None:
                break
        self.assertEqual(found.name, "Demo Case BTC Hard Fox")
        self.assertEqual(clock.now, 1008.0)

    def test_run_inquiry_on_a_fake_process(self):
        import subprocess
        import sys
        dl = report.Deadline(30)
        script = "import sys; sys.stdout.write(%r)" % WITH_NAME

        def popen(argv, **kwargs):
            return subprocess.Popen([sys.executable, "-c", script], **kwargs)

        parser = btclassic.run_inquiry(["btmgmt", "--index", "0", "find", "-b"], dl, lambda: FOX, popen)
        self.assertEqual(parser.get(FOX).name, "Demo Case BTC Hard Fox")
        parser = btclassic.run_inquiry(["btmgmt"], dl, lambda: "00:11:22:33:44:55", popen)
        self.assertIsNone(parser.get("00:11:22:33:44:55"))
        self.assertEqual(parser.get(FOX).name, "Demo Case BTC Hard Fox")

    def test_run_inquiry_without_a_target_keeps_every_device(self):
        import subprocess
        import sys
        dl = report.Deadline(30)

        def popen(argv, **kwargs):
            return subprocess.Popen([sys.executable, "-c", "import sys; sys.stdout.write(%r)" % WITH_NAME], **kwargs)

        parser = btclassic.run_inquiry(["btmgmt"], dl, lambda: None, popen)
        self.assertEqual(set(parser.devices), {FOX, "70:10:5C:11:22:33"})
        self.assertFalse(btclassic.named(parser, None))
        self.assertTrue(btclassic.named(parser, FOX))
        self.assertFalse(btclassic.named(parser, "00:11:22:33:44:55"))

    def test_run_inquiry_failure_is_a_run_error(self):
        import subprocess
        import sys
        dl = report.Deadline(30)

        def popen(argv, **kwargs):
            return subprocess.Popen([sys.executable, "-c",
                                     "import sys; sys.stderr.write('Unable to start discovery. status 0x14\\n'); sys.exit(1)"],
                                    **kwargs)

        with self.assertRaises(RunError) as caught:
            btclassic.run_inquiry(["btmgmt"], dl, lambda: FOX, popen)
        self.assertIn("status 0x14", str(caught.exception))

    def test_inquiry_repeats_while_time_allows(self):
        import subprocess
        import sys
        dl = report.Deadline(30)
        outputs = iter([WITHOUT_NAME, WITH_NAME])
        calls = []

        def popen(argv, **kwargs):
            calls.append(argv)
            return subprocess.Popen([sys.executable, "-c", "import sys; sys.stdout.write(%r)" % next(outputs)], **kwargs)

        parser = btclassic.inquiry("hci0", dl, "btmgmt", lambda: FOX, popen)
        self.assertEqual(len(calls), 2)
        self.assertEqual(parser.get(FOX).name, "Demo Case BTC Hard Fox")

    def test_inquiry_keeps_the_nameless_answer_when_time_runs_out(self):
        import subprocess
        import sys
        dl = report.Deadline(5)

        def popen(argv, **kwargs):
            return subprocess.Popen([sys.executable, "-c", "import sys; sys.stdout.write(%r)" % WITHOUT_NAME], **kwargs)

        parser = btclassic.inquiry("hci0", dl, "btmgmt", lambda: FOX, popen)
        self.assertEqual(parser.get(FOX).address, FOX)
        self.assertIsNone(parser.get(FOX).name)

    def test_inquiry_thread_takes_the_target_late(self):
        import subprocess
        import sys
        import time
        dl = report.Deadline(30)
        script = "import sys, time; sys.stdout.write(%r); sys.stdout.flush(); time.sleep(5)" % WITH_NAME

        def popen(argv, **kwargs):
            return subprocess.Popen([sys.executable, "-c", script], **kwargs)

        scan = btclassic.Inquiry("hci0", dl, "btmgmt", popen)
        scan.start()
        time.sleep(0.3)
        self.assertTrue(scan.is_alive())
        scan.set_target("f2:f6:6d:bc:2a:80")
        started = time.monotonic()
        parser = scan.result(dl)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(parser.get(FOX).name, "Demo Case BTC Hard Fox")
        self.assertFalse(scan.is_alive())

    def test_inquiry_thread_stop_and_error(self):
        import subprocess
        import sys
        dl = report.Deadline(30)

        def popen(argv, **kwargs):
            return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"], **kwargs)

        scan = btclassic.Inquiry("hci0", dl, "btmgmt", popen)
        scan.start()
        scan.stop()
        parser = scan.result(report.Deadline(2))
        self.assertEqual(parser.devices, {})

        def failing(argv, **kwargs):
            return subprocess.Popen([sys.executable, "-c",
                                     "import sys; sys.stderr.write('Unable to start discovery. status 0x14\\n'); sys.exit(1)"],
                                    **kwargs)

        scan = btclassic.Inquiry("hci0", dl, "btmgmt", failing)
        scan.start()
        with self.assertRaises(RunError) as caught:
            scan.result(report.Deadline(5))
        self.assertIn("status 0x14", str(caught.exception))


class RemoteNameTest(unittest.TestCase):
    def test_cached_name(self):
        dl, clock = deadline(30)
        run = Recorder({"bluetoothctl info": "Device F2:F6:6D:BC:2A:80 (public)\n\tName: Demo Case BTC Hard Fox\n"})
        self.assertEqual(btclassic.remote_name(FOX, dl, "bluetoothctl", run), "Demo Case BTC Hard Fox")
        self.assertEqual(run.calls, [["bluetoothctl", "info", FOX]])

    def test_scan_then_info(self):
        dl, clock = deadline(30)
        answers = iter(["Device F2:F6:6D:BC:2A:80 not available\n", "", "\tName: Demo Case BTC Hard Fox\n"])

        def run(argv, **kwargs):
            calls.append(argv)
            return Recorder.Result(0, next(answers))

        calls = []
        self.assertEqual(btclassic.remote_name(FOX, dl, "bluetoothctl", run), "Demo Case BTC Hard Fox")
        self.assertEqual(calls[1], ["bluetoothctl", "--timeout", "12", "scan", "bredr"])

    def test_no_bluetoothctl_or_no_time(self):
        dl, clock = deadline(30)
        self.assertIsNone(btclassic.remote_name(FOX, dl, None))
        dl, clock = deadline(1)
        run = Recorder({"bluetoothctl info": "Device F2:F6:6D:BC:2A:80 not available\n"})
        self.assertIsNone(btclassic.remote_name(FOX, dl, "bluetoothctl", run))
        self.assertEqual(len(run.calls), 1)


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.report = report.Report(out=io.StringIO())
        self.block = conf.select(HEADER, ["HARD"])
        self.readback = parse_transcript(read_fixture("transcripts", "classic_hard.log"))

    def rows(self):
        return {row.value: row for row in self.report.rows}

    def test_pass_with_eir_name(self):
        found = btclassic.parse_btmgmt(WITH_NAME)
        fox = [f for f in found if f.address == FOX][0]
        btclassic.rows(self.report, self.block, self.readback, fox)
        self.assertEqual([row.verdict for row in self.report.rows], ["pass", "pass"])

    def test_remote_name_fills_in(self):
        fox = [f for f in btclassic.parse_btmgmt(WITHOUT_NAME) if f.address == FOX][0]
        btclassic.rows(self.report, self.block, self.readback, fox, name="Demo Case BTC Hard Fox")
        self.assertEqual(self.rows()["NAME"].verdict, "pass")
        self.report.rows.clear()
        btclassic.rows(self.report, self.block, self.readback, fox)
        self.assertEqual(self.rows()["NAME"].verdict, "unverified")
        self.assertEqual(self.rows()["NAME"].reason, "inquiry response without a name and no remote name")
        self.assertEqual(self.rows()["MAC_ADDR"].verdict, "pass")

    def test_no_response(self):
        btclassic.rows(self.report, self.block, self.readback, None)
        self.assertEqual([row.reason for row in self.report.rows], ["no inquiry response"] * 2)

    def test_wrong_name_fails(self):
        fox = btclassic.Found(FOX, "BR/EDR", -60, "0x0000", "Other Fox", False)
        btclassic.rows(self.report, self.block, self.readback, fox)
        self.assertEqual(self.rows()["NAME"].verdict, "FAIL")


if __name__ == "__main__":
    unittest.main()
