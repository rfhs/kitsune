import sys
import unittest

from foxverify import tshark
from foxverify.report import RunError
from foxverify.tests import read_fixture
from foxverify.tests.fakes import FakeReader, deadline


class CommandTest(unittest.TestCase):
    def test_live_command_lists_fields_and_filter(self):
        argv = tshark.live_command("/usr/bin/tshark", "wlan1", ["wlan.bssid", "wlan.ssid"],
                                  "wlan.fc.type_subtype == 0x0008")
        self.assertEqual(argv[:3], ["/usr/bin/tshark", "-i", "wlan1"])
        self.assertIn("-l", argv)
        self.assertIn("-n", argv)
        self.assertEqual(argv[argv.index("-T") + 1], "fields")
        self.assertEqual(argv.count("-e"), 2)
        self.assertEqual(argv[argv.index("-e") + 1], "wlan.bssid")
        self.assertEqual(argv[-2:], ["-Y", "wlan.fc.type_subtype == 0x0008"])
        self.assertIn("separator=/t", argv)
        self.assertIn("occurrence=a", argv)

    def test_file_command_reads_a_path(self):
        argv = tshark.file_command("tshark", "/tmp/x/sniffer.pcap", ["wpan.src_pan"])
        self.assertEqual(argv[:3], ["tshark", "-r", "/tmp/x/sniffer.pcap"])
        self.assertNotIn("-Y", argv)


class CellTest(unittest.TestCase):
    def test_hex_int(self):
        self.assertEqual(tshark.hex_int("0x0008"), 8)
        self.assertEqual(tshark.hex_int("0x08"), 8)
        self.assertEqual(tshark.hex_int("0xfffc"), 0xFFFC)
        self.assertEqual(tshark.hex_int("15"), 15)
        self.assertIsNone(tshark.hex_int(""))
        self.assertIsNone(tshark.hex_int(None))
        self.assertIsNone(tshark.hex_int("zz"))

    def test_dec_int_and_mac_text(self):
        self.assertEqual(tshark.dec_int("11"), 11)
        self.assertEqual(tshark.dec_int("2412,2412"), 2412)
        self.assertIsNone(tshark.dec_int(""))
        self.assertIsNone(tshark.dec_int("abc"))
        self.assertEqual(tshark.mac_text("f2:5a:3c:91:0e:7b:44:d8"), "F2:5A:3C:91:0E:7B:44:D8")
        self.assertEqual(tshark.mac_text("f2-f4-90-22-0d-0f"), "F2:F4:90:22:0D:0F")
        self.assertIsNone(tshark.mac_text(""))

    def test_record_cells_and_occurrences(self):
        fields = ["a", "b", "c", "d"]
        record = tshark.parse_line("1\t2,8\t\tx\n", fields)
        self.assertEqual(record.get("a"), "1")
        self.assertEqual(record.values("b"), ["2", "8"])
        self.assertEqual(record.first("b"), "2")
        self.assertIsNone(record.get("c"))
        self.assertEqual(record.values("c"), [])
        self.assertEqual(record.get("d"), "x")
        self.assertEqual(record.as_dict(), {"a": "1", "b": "2,8", "c": "", "d": "x"})

    def test_short_line_leaves_missing_fields_empty(self):
        record = tshark.parse_line("only", ["a", "b"])
        self.assertEqual(record.get("a"), "only")
        self.assertIsNone(record.get("b"))

    def test_fixture_lines_split_into_the_ap_fields(self):
        from foxverify.wifi import AP_FIELDS
        lines = read_fixture("tshark", "ap_beacons.tsv").splitlines()
        record = tshark.parse_line(lines[0], AP_FIELDS)
        self.assertEqual(record.get("wlan.bssid"), "f2:f4:90:22:0d:0f")
        self.assertEqual(record.get("wlan.ssid"), "Demo Hiro WiFi AP Easy Fox")
        self.assertEqual(record.values("wlan.rsn.akms.type"), ["2"])


FAKE_TSHARK = (
    "import sys, time\n"
    "sys.stdout.write('1\\tf2:f4:90:22:0d:0f\\n'); sys.stdout.flush()\n"
    "time.sleep(0.3)\n"
    "sys.stdout.write('2\\t\\n'); sys.stdout.flush()\n"
    "sys.stderr.write('Capturing on fake\\n'); sys.stderr.flush()\n"
    "sys.exit(3)\n"
)


class FieldReaderTest(unittest.TestCase):
    """The reader on a real subprocess that plays tshark."""

    def test_reads_lines_times_out_and_reports_exit(self):
        fields = ["n", "mac"]
        with tshark.FieldReader([sys.executable, "-c", FAKE_TSHARK], fields) as reader:
            first = reader.read(5.0)
            self.assertEqual(first.get("n"), "1")
            self.assertEqual(first.get("mac"), "f2:f4:90:22:0d:0f")
            self.assertIsNone(reader.read(0.0))
            second = reader.read(5.0)
            self.assertEqual(second.get("n"), "2")
            self.assertIsNone(second.get("mac"))
            self.assertIsNone(reader.read(5.0))
            self.assertTrue(reader.eof)
            self.assertEqual(reader.wait(5.0), 3)
        self.assertTrue(reader.exited())
        error = reader.error()
        self.assertIn("python", error)
        self.assertIn("status 3", error)
        self.assertIn("Capturing on fake", error)

    def test_line_reader_returns_text(self):
        with tshark.LineReader([sys.executable, "-c", "print('a\\tb')"]) as reader:
            self.assertEqual(reader.read(5.0), "a\tb")
            self.assertIsNone(reader.read(5.0))
            self.assertTrue(reader.eof)


class ReadUntilTest(unittest.TestCase):
    def test_returns_the_accepted_record_and_moves_the_clock(self):
        dl, clock = deadline(60)
        reader = FakeReader(["a"], [(1.0, "x"), (2.0, "y"), (3.0, "z")], clock)
        record = tshark.read_until(reader, dl, lambda r: r.get("a") == "y")
        self.assertEqual(record.get("a"), "y")
        self.assertEqual(clock.now, 1003.0)

    def test_none_at_the_deadline(self):
        dl, clock = deadline(5)
        reader = FakeReader(["a"], [(10.0, "late")], clock)
        self.assertIsNone(tshark.read_until(reader, dl, lambda r: True))
        self.assertTrue(dl.expired())

    def test_early_exit_is_a_run_error(self):
        dl, clock = deadline(60)
        reader = FakeReader(["a"], [(0.5, None)], clock)
        with self.assertRaises(RunError) as caught:
            tshark.read_until(reader, dl, lambda r: True)
        self.assertIn("fake", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
