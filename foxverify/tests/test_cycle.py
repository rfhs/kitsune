"""The wake and sleep cycle measured on synthetic timestamps: the budget rule,
the end of wake 1 by the serial port and by silence, the span, gap and period
rules, the FAIL texts for a wake 2 that was not heard, the first transmission
line and the median RSSI."""
import io
import unittest

from foxverify import conf, cycle, report
from foxverify.cycle import BOOT_ALLOWANCE, Cycle, Heard
from foxverify.serial_fox import FakeClock, parse_transcript
from foxverify.tests import frozen_text, read_fixture
from foxverify.tests.fakes import deadline


def heard(start, count, spacing, rssi=-50):
    """``count`` frames from ``start`` every ``spacing`` seconds."""
    return [Heard(start + i * spacing, rssi) for i in range(count)]


def fed(frames, **kwargs):
    kwargs.setdefault("reset_time", 0.0)
    kwargs.setdefault("granularity", 1.0)
    kwargs.setdefault("measure", True)
    one = Cycle(**kwargs)
    for frame in frames:
        one.feed(frame)
    return one


class BudgetTest(unittest.TestCase):
    """--timeout against TIME_TO_WAKE + TIME_TO_SLEEP + 5 for the demo blocks."""

    def test_constant_and_formula(self):
        self.assertEqual(BOOT_ALLOWANCE, 5.0)
        self.assertEqual(cycle.needed(30, 30), 65.0)
        self.assertEqual(cycle.needed(300, 0), 305.0)

    def test_classic_hard_needs_65(self):
        self.assertFalse(cycle.fits(30, 30, 60))
        self.assertTrue(cycle.fits(30, 30, 65))
        self.assertEqual(cycle.budget_note(30, 30, 60),
                         "TIME_TO_WAKE and TIME_TO_SLEEP: serial only, --timeout 60 is under the 65 s "
                         "the cycle needs (TIME_TO_WAKE + TIME_TO_SLEEP + 5)")

    def test_ibeacon_medium_and_wifi_easy_ap_fit_in_60(self):
        self.assertTrue(cycle.fits(5, 5, 60))
        self.assertTrue(cycle.fits(15, 5, 60))
        self.assertTrue(cycle.fits(15, 5, 25))
        self.assertFalse(cycle.fits(15, 5, 24.9))

    def test_zigbee_demo_needs_305(self):
        self.assertFalse(cycle.fits(300, 0, 60))
        self.assertTrue(cycle.fits(300, 0, 305))
        self.assertIn("--timeout 60 is under the 305 s the cycle needs", cycle.budget_note(300, 0, 60))

    def test_demo_blocks_of_every_project(self):
        expect = [
            ("classic_discoverable", ["HARD"], False),
            ("iBeacon", ["MEDIUM"], True),
            ("wifi_ap_client", ["AP", "EASY"], True),
            ("zigbee_coordinator", ["COORDINATOR", "EASY"], False),
        ]
        for project, tokens, fits in expect:
            block = conf.select(frozen_text(project), tokens)
            self.assertEqual(cycle.fits(block.integer("TIME_TO_WAKE"), block.integer("TIME_TO_SLEEP"), 60),
                             fits, project)


class BoundaryTest(unittest.TestCase):
    """How the end of wake 1 is found."""

    def test_going_to_sleep_splits_the_frames_exactly(self):
        one = fed(heard(2.0, 10, 1.0) + heard(17.0, 3, 1.0))
        self.assertFalse(one.ended(12.0))
        self.assertEqual(len(one.wake2()), 0)
        one.mark_sleep(11.5)
        self.assertTrue(one.ended(11.6))
        self.assertEqual(len(one.wake1()), 10)
        self.assertEqual(len(one.wake2()), 3)
        self.assertTrue(one.complete())
        self.assertAlmostEqual(one.span(), 9.0)
        self.assertAlmostEqual(one.gap(), 6.0)
        self.assertAlmostEqual(one.period(), 15.0)

    def test_sleep_learned_late_moves_frames_already_fed(self):
        one = fed(heard(2.0, 5, 1.0) + [Heard(9.0, -50)])
        self.assertEqual(len(one.wake1()), 6)
        one.mark_sleep(6.5)
        self.assertEqual(len(one.wake1()), 5)
        self.assertEqual([f.time for f in one.wake2()], [9.0])

    def test_silence_without_a_serial_port(self):
        one = fed(heard(2.0, 10, 1.0), serial=False)
        self.assertFalse(one.ended(17.0))
        self.assertTrue(one.ended(17.1))
        one.feed(Heard(40.0, -50))
        self.assertEqual(len(one.wake2()), 1)
        self.assertAlmostEqual(one.gap(), 29.0)

    def test_silence_with_a_serial_port_waits_for_the_latest_end_of_wake_1(self):
        one = fed(heard(2.0, 10, 1.0), wake=30, serial=True)
        # Quiet for 20 s is not the sleep while the port may still speak and
        # the wake could last until 2 + 30 + 5.
        self.assertFalse(one.ended(31.0))
        one.feed(Heard(31.0, -50))
        self.assertEqual(len(one.wake1()), 11)
        # Past that moment a long silence is the fallback signal.
        self.assertTrue(one.ended(45.0))
        one.feed(Heard(45.0, -50))
        self.assertEqual(len(one.wake2()), 1)

    def test_adaptive_granularity_is_the_largest_gap_in_wake_1(self):
        one = fed([Heard(2.0, -40), Heard(2.1, -40), Heard(4.5, -40), Heard(4.6, -40), Heard(7.0, -40)],
                  granularity=None, serial=False)
        self.assertAlmostEqual(one.granularity(), 2.4)
        self.assertFalse(one.ended(14.0))
        self.assertTrue(one.ended(14.6))
        one = fed([Heard(2.0, -40), Heard(2.2, -40)], granularity=None, serial=False)
        self.assertEqual(one.granularity(), cycle.MIN_GRANULARITY)

    def test_done_and_complete(self):
        one = fed(heard(2.0, 3, 1.0), measure=False)
        self.assertTrue(one.done())
        self.assertFalse(one.complete())
        one = fed(heard(2.0, 3, 1.0), measure=True)
        self.assertFalse(one.done())
        one.mark_sleep(5.0)
        one.feed(Heard(10.0, -50))
        self.assertTrue(one.done())


class TextTest(unittest.TestCase):
    def test_first_transmission(self):
        one = fed(heard(2.3, 3, 1.0))
        self.assertAlmostEqual(one.first_transmission(), 2.3)
        self.assertEqual(cycle.first_transmission_line(one, False), "first transmission: 2.3 s after reset")
        self.assertEqual(cycle.first_transmission_line(one, True), "first transmission: not measured (--no-reset)")
        self.assertEqual(cycle.first_transmission_line(fed([]), False),
                         "first transmission: none heard before the deadline")

    def test_first_transmission_over_the_allowance(self):
        one = fed(heard(6.2, 3, 1.0))
        self.assertEqual(cycle.first_transmission_line(one, False),
                         "first transmission: 6.2 s after reset, over the 5 s boot allowance")
        one = fed(heard(6.2, 3, 1.0), measure=False)
        self.assertEqual(cycle.first_transmission_line(one, False), "first transmission: 6.2 s after reset")
        one = fed(heard(2.0, 3, 1.0), reset_time=None)
        self.assertIsNone(one.first_transmission())

    def test_first_transmission_of_a_fox_that_was_not_reset(self):
        """A USB stack without a reset leaves no instant to measure from, and
        the line says so without blaming --no-reset."""
        one = fed(heard(2.0, 3, 1.0), reset_time=None)
        self.assertEqual(cycle.first_transmission_line(one, False),
                         "first transmission: not measured (the fox was not reset)")
        self.assertEqual(cycle.first_transmission_line(one, True), "first transmission: not measured (--no-reset)")

    def test_median_rssi(self):
        one = fed([Heard(1.0, -40), Heard(2.0, -44), Heard(3.0, -42), Heard(4.0, None)])
        self.assertEqual(one.rssi_text(), "median -42 dBm over 3 frames")
        self.assertEqual(fed([Heard(1.0, -61)]).rssi_text(), "median -61 dBm over 1 frame")
        self.assertEqual(fed([Heard(1.0, -41), Heard(2.0, -42)]).rssi_text(), "median -42 dBm over 2 frames")
        self.assertIsNone(fed([]).rssi_text())
        self.assertIsNone(fed([Heard(1.0, None)]).rssi_text())


class RowsTest(unittest.TestCase):
    """The TIME_TO_WAKE and TIME_TO_SLEEP rows from measured cycles. The Wi-Fi
    EASY AP block is 15/5 with granularity 1, so a wake passes between 14 and
    20 s on the air, a period within 19-21 s and a gap of at most 11 s."""

    def setUp(self):
        self.report = report.Report(out=io.StringIO())
        self.block = conf.select(frozen_text("wifi_ap_client"), ["AP", "EASY"])
        self.readback = parse_transcript(read_fixture("transcripts", "wifi_easy_ap.log"))

    def rows(self, one, random_channel=False, block=None, readback=None):
        cycle.rows(self.report, block or self.block, readback or self.readback, one, random_channel)
        return {row.value: row for row in self.report.rows}

    def exact_cycle(self, wake, sleep, boot=1.5, granularity=1.0, spacing=0.1024, sleep_line=True):
        """Frames of a fox that boots in ``boot`` seconds, beacons every
        ``spacing`` for ``wake`` seconds and keeps its cycle exact."""
        first1 = boot
        count = int(wake / spacing) + 1
        first2 = wake + sleep + boot
        one = fed(heard(first1, count, spacing) + heard(first2, 3, spacing), granularity=granularity)
        if sleep_line:
            one.mark_sleep(first1 + wake + 0.2)
        return one

    def test_wifi_easy_ap_passes(self):
        rows = self.rows(self.exact_cycle(15, 5))
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "pass")
        self.assertEqual(rows["TIME_TO_WAKE"].air, "on the air 15.0 s")
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "pass")
        self.assertEqual(rows["TIME_TO_SLEEP"].air, "off the air 5.0 s")
        self.assertEqual((rows["TIME_TO_WAKE"].header, rows["TIME_TO_WAKE"].serial), ("15", "15"))
        self.assertEqual(self.report.exit_code(), report.EXIT_OK)

    def test_span_tolerances(self):
        one = fed(heard(1.0, 2, 14.0) + [Heard(40.0, -50)])
        one.mark_sleep(16.0)
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "pass")
        self.report.rows.clear()
        one = fed(heard(1.0, 2, 13.9) + [Heard(40.0, -50)])
        one.mark_sleep(16.0)
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "FAIL")
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "15", "15", "on the air 13.9 s", "FAIL"])
        self.report.rows.clear()
        one = fed(heard(1.0, 2, 20.0) + [Heard(40.0, -50)])
        one.mark_sleep(22.0)
        self.assertEqual(self.rows(one)["TIME_TO_WAKE"].verdict, "pass")
        self.report.rows.clear()
        one = fed(heard(1.0, 2, 20.1) + [Heard(40.0, -50)])
        one.mark_sleep(22.0)
        self.assertEqual(self.rows(one)["TIME_TO_WAKE"].verdict, "FAIL")

    def test_period_three_seconds_off_fails_with_the_three_values(self):
        one = fed(heard(1.5, 2, 15.0) + [Heard(24.5, -50)])
        one.mark_sleep(17.0)
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "pass")
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(),
                         ["TIME_TO_SLEEP", "5", "5", "off the air 8.0 s, cycle 23.0 s", "FAIL"])
        self.assertEqual(self.report.exit_code(), report.EXIT_FAIL)

    def test_period_tolerance_is_one_second_or_one_percent(self):
        one = fed(heard(1.5, 2, 15.0) + [Heard(22.5, -50)])
        one.mark_sleep(17.0)
        self.assertEqual(self.rows(one)["TIME_TO_SLEEP"].verdict, "pass")
        self.report.rows.clear()
        one = fed(heard(1.5, 2, 15.0) + [Heard(22.6, -50)])
        one.mark_sleep(17.0)
        self.assertEqual(self.rows(one)["TIME_TO_SLEEP"].verdict, "FAIL")
        # A 255/45 fox: one percent of 300 s is 3 s.
        text = frozen_text("wifi_ap_client").replace("#define TIME_TO_WAKE 30", "#define TIME_TO_WAKE 255")
        block = conf.select(text, ["AP", "HARD"])
        readback = parse_transcript(read_fixture("transcripts", "wifi_hard_ap.log").replace(
            "Time to wake: 30s", "Time to wake: 255s"))
        self.report.rows.clear()
        one = fed(heard(2.0, 2, 255.0) + [Heard(304.9, -50)], granularity=1.0)
        one.mark_sleep(257.5)
        self.assertEqual(self.rows(one, block=block, readback=readback)["TIME_TO_SLEEP"].verdict, "pass")
        self.report.rows.clear()
        one = fed(heard(2.0, 2, 255.0) + [Heard(305.1, -50)], granularity=1.0)
        one.mark_sleep(257.5)
        self.assertEqual(self.rows(one, block=block, readback=readback)["TIME_TO_SLEEP"].verdict, "FAIL")

    def test_time_to_sleep_zero_passes_a_quick_reboot_and_fails_a_slow_one(self):
        block = conf.select(frozen_text("zigbee_coordinator"), ["COORDINATOR", "EASY"])
        readback = parse_transcript(read_fixture("transcripts", "zigbee_easy.log"))
        # 300/0, boot 2 s each time: the fox reboots as soon as its wake is
        # over, so the cycle is 300 s plus the boot and the gap is the boot.
        one = fed(heard(2.0, 301, 1.0) + [Heard(304.0, -50)], granularity=1.0)
        one.mark_sleep(302.4)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_WAKE"].air, "on the air 300.0 s")
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "pass")
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "0", "0", "off the air 2.0 s", "pass"])
        self.report.rows.clear()
        # The same fox booting in 7 s: the gap is over the allowance plus the
        # granularity.
        one = fed(heard(7.0, 301, 1.0) + [Heard(314.0, -50)], granularity=1.0)
        one.mark_sleep(307.4)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(),
                         ["TIME_TO_SLEEP", "0", "0", "off the air 7.0 s, cycle 307.0 s", "FAIL"])
        self.report.rows.clear()
        # A boot of exactly the allowance plus the granularity still passes.
        one = fed(heard(6.0, 301, 1.0) + [Heard(312.0, -50)], granularity=1.0)
        one.mark_sleep(306.4)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "0", "0", "off the air 6.0 s", "pass"])

    def test_zigbee_last_link_status_precedes_the_stop_by_the_interval(self):
        """A HARD coordinator sends a Link Status every 15 s, so the last one
        can come up to 15 s before the radio stops; the span may be short by
        the granularity."""
        text = frozen_text("zigbee_coordinator").replace("#define TIME_TO_WAKE 300", "#define TIME_TO_WAKE 60")
        block = conf.select(text, ["COORDINATOR", "HARD"])
        readback = parse_transcript(read_fixture("transcripts", "zigbee_hard.log").replace(
            "Time to wake: 300s", "Time to wake: 60s"))
        # First frame 3 s after reset, Link Status at 3, 18, 33, 48; radio
        # stops at 63; next wake's first frame at 63 + 3.
        one = fed(heard(3.0, 4, 15.0) + [Heard(66.0, -50)], granularity=15.0)
        one.mark_sleep(63.2)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "60", "60", "on the air 45.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "0", "0", "off the air 18.0 s", "pass"])

    def test_wake_2_never_comes_is_a_fail(self):
        one = fed(heard(1.5, 2, 15.0))
        one.mark_sleep(17.0)
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "pass")
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(),
                         ["TIME_TO_SLEEP", "5", "5", "wake 2 not heard before the deadline", "FAIL"])
        self.assertEqual(self.report.exit_code(), report.EXIT_FAIL)

    def test_random_channel_without_wake_2_channel_on_serial(self):
        one = fed(heard(1.5, 2, 15.0))
        one.mark_sleep(17.0)
        rows = self.rows(one, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].air, "wake 2 not heard: its channel was not seen on serial")
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "FAIL")

    def test_random_channel_retuned_but_nothing_heard(self):
        one = fed(heard(1.5, 2, 15.0))
        one.mark_sleep(17.0)
        one.retuned = (9, 23.4)
        rows = self.rows(one, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].air, "wake 2 not heard on channel 9 after retuning at +23.4 s")
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "FAIL")

    def test_slow_retune_that_misses_the_period_says_so(self):
        one = fed(heard(1.5, 2, 15.0) + [Heard(25.0, -50)])
        one.mark_sleep(17.0)
        one.retuned = (9, 24.0)
        rows = self.rows(one, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].air, "off the air 8.5 s, cycle 23.5 s, retuned at +24.0 s")
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "FAIL")

    def test_wake_1_not_over_at_the_deadline(self):
        clock = FakeClock(0.0)
        one = fed(heard(1.5, 10, 1.0), clock=clock)
        clock.now = 12.0
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "unverified")
        self.assertEqual(rows["TIME_TO_WAKE"].reason, "wake 1 not over before the deadline")
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(),
                         ["TIME_TO_SLEEP", "5", "5", "wake 1 had not ended at the deadline", "FAIL"])
        self.report.rows.clear()
        # A fox still on the air past TIME_TO_WAKE + 5 has failed its wake.
        one = fed(heard(1.5, 30, 1.0), clock=clock)
        clock.now = 31.0
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "15", "15", "on the air 29.0 s", "FAIL"])

    def test_late_capture_lowers_the_span_and_period_floors(self):
        """A Wi-Fi capture starts after the readback, here 3 s after the
        reset: the first 1.5 s of beacons were never heard, so the span and
        the period come out 1.5 s short of the firmware's exact figures and
        still pass."""
        one = fed(heard(3.0, 2, 13.5) + [Heard(21.5, -50)], listen_time=3.0, radio_time=1.4)
        one.mark_sleep(16.7)
        self.assertAlmostEqual(one.late(), 3.0)
        self.assertTrue(one.heard_at_once())
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "15", "15", "on the air 13.5 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "5", "5", "off the air 5.0 s", "pass"])
        self.report.rows.clear()
        # Without the late start the same numbers would fail.
        one = fed(heard(3.0, 2, 13.5) + [Heard(21.5, -50)])
        one.mark_sleep(16.7)
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "FAIL")
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "FAIL")
        self.report.rows.clear()
        # Short by more than the late start is still a FAIL.
        one = fed(heard(3.0, 2, 10.9) + [Heard(21.5, -50)], listen_time=3.0)
        one.mark_sleep(16.7)
        self.assertEqual(self.rows(one)["TIME_TO_WAKE"].verdict, "FAIL")

    def test_fox_heard_after_the_capture_began_is_not_late(self):
        one = fed(heard(4.5, 2, 15.0) + [Heard(24.5, -50)], listen_time=3.0)
        self.assertFalse(one.heard_at_once())
        self.assertAlmostEqual(one.late(), 3.0)
        self.assertEqual(cycle.first_transmission_line(one, False), "first transmission: 4.5 s after reset")

    def test_first_transmission_when_the_capture_began_late(self):
        one = fed(heard(3.1, 3, 1.0), listen_time=3.0, radio_time=1.4)
        self.assertEqual(cycle.first_transmission_line(one, False),
                         "first transmission: by 3.1 s after reset (the sniffer started listening at 3.0 s; "
                         "the radio was up at 1.4 s by serial)")
        one = fed(heard(3.1, 3, 1.0), listen_time=3.0)
        self.assertEqual(cycle.first_transmission_line(one, False),
                         "first transmission: by 3.1 s after reset (the sniffer started listening at 3.0 s)")
        one = fed(heard(7.1, 3, 1.0), listen_time=7.0, radio_time=6.2)
        self.assertEqual(cycle.first_transmission_line(one, False),
                         "first transmission: by 7.1 s after reset (the sniffer started listening at 7.0 s; "
                         "the radio was up at 6.2 s by serial), over the 5 s boot allowance")
        one = fed(heard(7.1, 3, 1.0), listen_time=7.0, radio_time=6.2, measure=False)
        self.assertNotIn("allowance", cycle.first_transmission_line(one, False))

    def test_no_frame_from_the_fox(self):
        rows = self.rows(fed([]))
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "15", "15", "-", "unverified: no frame from the fox"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "5", "5", "-", "unverified: no frame from the fox"])

    def test_serial_disagreement_is_a_fail_before_the_air(self):
        readback = parse_transcript(read_fixture("transcripts", "wifi_easy_ap.log").replace(
            "Time to wake: 15s", "Time to wake: 20s"))
        rows = self.rows(self.exact_cycle(15, 5), readback=readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "15", "20", "-", "FAIL"])
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "pass")


class ListenTest(unittest.TestCase):
    """The capture loop: frames fed, the follower polled, the retune made once."""

    class Follower:
        def __init__(self, boundary=None, channel=None):
            self._boundary = boundary
            self._channel = channel
            self.polls = 0

        def poll(self):
            self.polls += 1

        def boundary(self):
            return self._boundary

        def channel(self):
            return self._channel

    def test_stops_at_the_goal_without_a_cycle_to_measure(self):
        dl, clock = deadline(60)
        reads = []

        def read(timeout):
            reads.append(timeout)
            clock.advance(timeout)
            return [Heard(clock.now, -50)]

        one = Cycle(0.0, 1.0, measure=False, clock=clock)
        cycle.listen(one, dl, read, lambda: len(one.frames) >= 2)
        self.assertEqual(len(one.frames), 2)
        self.assertEqual(reads, [cycle.POLL, cycle.POLL])
        # The loop stamps when the capture began; a stamp given is kept.
        self.assertEqual(one.listen_time, 1000.0)
        one = Cycle(0.0, 1.0, measure=False, clock=clock, listen_time=0.0)
        cycle.listen(one, dl, read, lambda: True)
        self.assertEqual(one.listen_time, 0.0)

    def test_goes_on_until_wake_2_when_measuring(self):
        dl, clock = deadline(60, start=0.0)
        frames = iter([[Heard(1.0, -50)], [Heard(2.0, -50)]] + [[]] * 100 + [[Heard(30.0, -50)]])

        def read(timeout):
            clock.advance(timeout)
            return next(frames, [])

        follower = self.Follower(boundary=3.0, channel=9)
        tuned = []
        one = Cycle(0.0, 1.0, measure=True, clock=clock)
        cycle.listen(one, dl, read, lambda: True, follower, tuned.append)
        self.assertEqual(tuned, [9])
        self.assertEqual(one.retuned[0], 9)
        self.assertEqual(one.sleep_time, 3.0)
        self.assertTrue(one.complete())
        self.assertGreater(follower.polls, 100)

    def test_stops_at_the_deadline(self):
        dl, clock = deadline(2, start=0.0)
        one = Cycle(0.0, 1.0, measure=True, clock=clock)
        cycle.listen(one, dl, lambda timeout: clock.advance(timeout) or [], lambda: True)
        self.assertTrue(dl.expired())
        self.assertFalse(one.complete())


if __name__ == "__main__":
    unittest.main()
