import io
import unittest

from foxverify import report


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


class DeadlineTest(unittest.TestCase):
    def test_remaining_budget_and_expiry(self):
        clock = Clock(100.0)
        deadline = report.Deadline(60, clock)
        self.assertEqual(deadline.at, 160.0)
        self.assertEqual(deadline.remaining(), 60.0)
        self.assertEqual(deadline.budget(10), 10.0)
        clock.now = 155.0
        self.assertEqual(deadline.remaining(), 5.0)
        self.assertEqual(deadline.budget(10), 5.0)
        self.assertEqual(deadline.elapsed(), 55.0)
        self.assertFalse(deadline.expired())
        clock.now = 160.0
        self.assertTrue(deadline.expired())
        self.assertEqual(deadline.remaining(), 0.0)
        clock.now = 170.0
        self.assertEqual(deadline.remaining(), 0.0)


class VerdictTest(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        self.report = report.Report(report.Deadline(60, Clock()), self.out)

    def test_pass_when_all_three_agree(self):
        row = self.report.check("MAC_ADDR", "F2:81:5A:C1:A3:26", "F2:81:5A:C1:A3:26", "F2:81:5A:C1:A3:26")
        self.assertEqual(row.verdict, report.PASS)
        self.assertEqual(self.report.exit_code(), report.EXIT_OK)

    def test_fail_when_serial_differs_from_header(self):
        row = self.report.check("CHANNEL", 11, 15, 15)
        self.assertEqual(row.verdict, report.FAIL)
        self.assertEqual(row.cells(), ["CHANNEL", "11", "15", "15", "FAIL"])
        self.assertEqual(self.report.exit_code(), report.EXIT_FAIL)

    def test_fail_when_air_differs(self):
        row = self.report.check("PAN_ID", "0x1337", "0x1337", "0x1234")
        self.assertEqual(row.verdict, report.FAIL)
        self.assertTrue(self.report.failed())

    def test_serial_for_values_not_on_air(self):
        row = self.report.check("TIME_TO_WAKE", 300, 300, on_air=False)
        self.assertEqual(row.verdict, report.SERIAL)
        self.assertEqual(row.air, report.EMPTY)

    def test_unverified_with_reason(self):
        row = self.report.check("PACKET_INTERVAL", 15, 15, None, reason="two frames need 30 s, 12 s left")
        self.assertEqual(row.verdict, report.UNVERIFIED)
        self.assertEqual(row.cells()[4], "unverified: two frames need 30 s, 12 s left")
        self.assertEqual(self.report.exit_code(), report.EXIT_OK)

    def test_unverified_without_reason_says_not_seen(self):
        row = self.report.check("FSSID", "x", "x", None)
        self.assertEqual(row.reason, "not seen")

    def test_random_header_value_accepts_what_the_fox_picked(self):
        row = self.report.check("CHANNEL", "random", 7, 7, agree=True)
        self.assertEqual(row.verdict, report.PASS)
        row = self.report.check("CHANNEL", "random", 7, 9, agree=True)
        self.assertEqual(row.verdict, report.FAIL)

    def test_air_compared_with_header_when_fox_printed_nothing(self):
        row = self.report.check("NAME", "Fox", None, "Fox", agree=True)
        self.assertEqual(row.verdict, report.PASS)
        self.assertEqual(row.serial, report.EMPTY)

    def test_missing_serial_value_is_a_fail(self):
        row = self.report.check("NAME", "Fox", None, "Fox")
        self.assertEqual(row.verdict, report.FAIL)
        self.assertEqual(row.reason, report.NOT_PRINTED)
        self.assertEqual(row.cells()[4], "FAIL: not printed on serial")
        row = self.report.check("TIME_TO_WAKE", 300, None, on_air=False, reason="serial-only run")
        self.assertEqual((row.verdict, row.reason), (report.FAIL, report.NOT_PRINTED))


class RenderTest(unittest.TestCase):
    def test_table_notes_summary_and_exit_code(self):
        out = io.StringIO()
        clock = Clock(0.0)
        rep = report.Report(report.Deadline(60, clock), out)
        rep.check("MAC_ADDR", "F2:81:5A:C1:A3:26", "F2:81:5A:C1:A3:26", "F2:81:5A:C1:A3:26")
        rep.check("TIME_TO_WAKE", 300, 300, on_air=False)
        rep.check("NAME", "Demo Molly BTC Easy Fox", "Demo Molly BTC Easy Fox", None, reason="no inquiry reply")
        rep.note("no sniffer given, serial-only run")
        clock.now = 12.5
        code = rep.emit()
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "value        | header                  | serial                  | air               | verdict")
        self.assertEqual(lines[1], "MAC_ADDR     | F2:81:5A:C1:A3:26       | F2:81:5A:C1:A3:26       | F2:81:5A:C1:A3:26 | pass")
        self.assertEqual(lines[2], "TIME_TO_WAKE | 300                     | 300                     | -                 | serial")
        self.assertEqual(lines[3], "NAME         | Demo Molly BTC Easy Fox | Demo Molly BTC Easy Fox | -                 | unverified: no inquiry reply")
        self.assertEqual(lines[4], "note: no sniffer given, serial-only run")
        self.assertEqual(lines[5], "pass: 1 pass, 0 FAIL, 1 serial, 1 unverified, 12.5 s of 60 s")
        self.assertEqual(len(lines), 6)
        self.assertEqual(code, report.EXIT_OK)

    def test_summary_says_fail(self):
        rep = report.Report(out=io.StringIO())
        rep.check("CHANNEL", 1, 6, 6)
        self.assertEqual(rep.summary(), "FAIL: 0 pass, 1 FAIL, 0 serial, 0 unverified")
        self.assertEqual(rep.emit(), report.EXIT_FAIL)

    def test_say_and_debug(self):
        out = io.StringIO()
        rep = report.Report(out=out, verbose=False)
        rep.say("shown")
        rep.debug("hidden")
        rep.verbose = True
        rep.debug("shown too")
        self.assertEqual(out.getvalue(), "shown\nshown too\n")

    def test_run_error_exits_2(self):
        self.assertEqual(report.RunError("x").exit_code, report.EXIT_NO_RUN)
        self.assertEqual(report.EXIT_NO_RUN, 2)


if __name__ == "__main__":
    unittest.main()
