"""The wake and sleep cycle measured on synthetic timestamps: the budget tiers
and their lines, the end of each wake by the serial port and by silence, the
two-cycle rows from wake 2 and wake 3, the first-boot rows from wake 1 and the
gap to wake 2, the FAIL texts for a wake that was not heard, the capture loop's
early exit and retunes, the FIRST_FRAME row, the first wake line and the
median RSSI."""
import io
import unittest

from foxverify import conf, cycle, report
from foxverify.cycle import BOOT_ALLOWANCE, NONE, ONE_CYCLE, TWO_CYCLES, Cycle, Heard
from foxverify.serial_fox import FakeClock, parse_transcript
from foxverify.tests import frozen_text, read_fixture
from foxverify.tests.fakes import deadline


def heard(start, count, spacing, rssi=-50):
    """``count`` frames from ``start`` every ``spacing`` seconds."""
    return [Heard(start + i * spacing, rssi) for i in range(count)]


def fed(frames, **kwargs):
    kwargs.setdefault("reset_time", 0.0)
    kwargs.setdefault("granularity", 1.0)
    kwargs.setdefault("tier", ONE_CYCLE)
    one = Cycle(**kwargs)
    for frame in frames:
        one.feed(frame)
    return one


def block_and_readback(project, tokens, transcript, replace=()):
    """The frozen block and the parsed transcript of a project, with the
    given (old, new) replacements made in the header and the transcript."""
    text, log = frozen_text(project), read_fixture("transcripts", transcript)
    for old, new in replace:
        text = text.replace(old, new)
    for old, new in replace:
        log = log.replace(old, new)
    return conf.select(text, tokens), parse_transcript(log)


class TierTest(unittest.TestCase):
    """--timeout against one and two cycles plus the 5 s boot allowance for
    the demo blocks, and the lines each tier prints."""

    def test_constant_and_formula(self):
        self.assertEqual(BOOT_ALLOWANCE, 5.0)
        self.assertEqual(cycle.needed(30, 30, 1), 65.0)
        self.assertEqual(cycle.needed(30, 30), 125.0)
        self.assertEqual(cycle.needed(300, 0, 1), 305.0)
        self.assertEqual(cycle.needed(300, 0, 2), 605.0)
        self.assertEqual(cycle.full_timeout(300, 0), 605)
        self.assertEqual(cycle.full_timeout(15, 5), 45)

    def test_classic_hard_none_at_60_one_at_65_two_at_125(self):
        self.assertEqual(cycle.tier(30, 30, 60), NONE)
        self.assertEqual(cycle.tier(30, 30, 64.9), NONE)
        self.assertEqual(cycle.tier(30, 30, 65), ONE_CYCLE)
        self.assertEqual(cycle.tier(30, 30, 124.9), ONE_CYCLE)
        self.assertEqual(cycle.tier(30, 30, 125), TWO_CYCLES)

    def test_ibeacon_medium_and_wifi_easy_ap_fit_two_cycles_in_60(self):
        self.assertEqual(cycle.tier(5, 5, 60), TWO_CYCLES)
        self.assertEqual(cycle.needed(5, 5), 25.0)
        self.assertEqual(cycle.tier(15, 5, 60), TWO_CYCLES)
        self.assertEqual(cycle.needed(15, 5), 45.0)
        self.assertEqual(cycle.tier(15, 5, 44.9), ONE_CYCLE)
        self.assertEqual(cycle.tier(15, 5, 25), ONE_CYCLE)
        self.assertEqual(cycle.tier(15, 5, 24.9), NONE)

    def test_zigbee_demo_none_at_60_one_at_305_two_at_605(self):
        self.assertEqual(cycle.tier(300, 0, 60), NONE)
        self.assertEqual(cycle.tier(300, 0, 305), ONE_CYCLE)
        self.assertEqual(cycle.tier(300, 0, 604), ONE_CYCLE)
        self.assertEqual(cycle.tier(300, 0, 605), TWO_CYCLES)
        self.assertEqual(cycle.suggestion(NONE, 300, 0), "run with --timeout 605 to measure the cycle time")

    def test_demo_blocks_of_every_project_at_60(self):
        expect = [
            ("classic_discoverable", ["HARD"], NONE),
            ("iBeacon", ["MEDIUM"], TWO_CYCLES),
            ("wifi_ap_client", ["AP", "EASY"], TWO_CYCLES),
            ("zigbee_coordinator", ["COORDINATOR", "EASY"], NONE),
        ]
        for project, tokens, which in expect:
            block = conf.select(frozen_text(project), tokens)
            self.assertEqual(cycle.tier(block.integer("TIME_TO_WAKE"), block.integer("TIME_TO_SLEEP"), 60),
                             which, project)

    def test_suggestion_lines(self):
        self.assertEqual(cycle.suggestion(NONE, 30, 30), "run with --timeout 125 to measure the cycle time")
        self.assertEqual(cycle.suggestion(ONE_CYCLE, 30, 30),
                         "run with --timeout 125 for the exact cycle time; this run judged the first boot "
                         "with wider tolerances")
        self.assertEqual(cycle.suggestion(ONE_CYCLE, 300, 0),
                         "run with --timeout 605 for the exact cycle time; this run judged the first boot "
                         "with wider tolerances")
        self.assertIsNone(cycle.suggestion(TWO_CYCLES, 15, 5))

    def test_tier_lines(self):
        self.assertEqual(cycle.tier_line(TWO_CYCLES, 300, 0, 605),
                         "measuring the cycle time from wake 2 and wake 3 (--timeout 605 covers two cycles of "
                         "300 s plus the 5 s boot allowance)")
        self.assertEqual(cycle.tier_line(ONE_CYCLE, 300, 0, 305),
                         "judging the first boot with wider tolerances (--timeout 305 covers one cycle of 300 s "
                         "plus the 5 s boot allowance; two cycles need 605)")
        self.assertEqual(cycle.tier_line(NONE, 300, 0, 60),
                         "TIME_TO_WAKE and TIME_TO_SLEEP serial only (--timeout 60 is under the 605 s needed to "
                         "measure the cycle time: two cycles of 300 s plus the 5 s boot allowance)")
        self.assertEqual(cycle.tier_line(NONE, 15, 5, 24.5),
                         "TIME_TO_WAKE and TIME_TO_SLEEP serial only (--timeout 24.5 is under the 45 s needed to "
                         "measure the cycle time: two cycles of 20 s plus the 5 s boot allowance)")


class BoundaryTest(unittest.TestCase):
    """How the end of each wake is found."""

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
        self.assertAlmostEqual(one.first_cycle(), 17.0)

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

    def test_silence_with_a_serial_port_waits_for_the_latest_end_of_the_wake(self):
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

    def test_three_wakes_by_sleep_lines_and_by_silence(self):
        """Two sleep instants split three wakes; without the second the end
        of wake 2 is found by silence, which a serial port delays to the
        latest end of that wake."""
        frames = heard(2.0, 10, 1.0) + heard(22.0, 10, 1.0) + heard(42.0, 3, 1.0)
        one = fed(frames, tier=TWO_CYCLES, wake=10)
        one.mark_sleep(11.5)
        one.mark_sleep(31.5)
        self.assertEqual(one.wakes(), 3)
        self.assertEqual([len(one.frames_of(n)) for n in (1, 2, 3)], [10, 10, 3])
        self.assertAlmostEqual(one.span(2), 9.0)
        self.assertAlmostEqual(one.gap(2), 11.0)
        self.assertAlmostEqual(one.period(2), 20.0)
        self.assertTrue(one.complete())
        self.assertTrue(one.ended(wake=2))
        self.assertEqual(one.frames_of(4), [])
        one = fed(frames, tier=TWO_CYCLES, wake=10)
        one.mark_sleep(11.5)
        self.assertEqual(one.wakes(), 3)
        self.assertEqual(len(one.frames_of(2)), 10)
        one = fed(heard(2.0, 10, 1.0) + heard(22.0, 10, 1.0) + heard(36.0, 3, 1.0), tier=TWO_CYCLES, wake=10)
        one.mark_sleep(11.5)
        # 36 - 31 = 5 s of silence is under the granularity plus the
        # allowance, so the frames at 36 still belong to wake 2.
        self.assertEqual(one.wakes(), 2)
        self.assertFalse(one.complete())
        self.assertFalse(one.ended(39.0, wake=2))
        self.assertTrue(one.ended(45.0, wake=2))

    def test_sleep_instants_count_once_and_in_order(self):
        one = fed(heard(2.0, 3, 1.0))
        one.mark_sleep(5.0)
        one.mark_sleep(5.0)
        one.mark_sleep(4.0)
        one.mark_sleep(25.0)
        self.assertEqual(one.sleep_times, [5.0, 25.0])

    def test_adaptive_granularity_is_the_largest_gap_in_wake_1(self):
        one = fed([Heard(2.0, -40), Heard(2.1, -40), Heard(4.5, -40), Heard(4.6, -40), Heard(7.0, -40)],
                  granularity=None, serial=False)
        self.assertAlmostEqual(one.granularity(), 2.4)
        self.assertFalse(one.ended(14.0))
        self.assertTrue(one.ended(14.6))
        one = fed([Heard(2.0, -40), Heard(2.2, -40)], granularity=None, serial=False)
        self.assertEqual(one.granularity(), cycle.MIN_GRANULARITY)

    def test_done_and_complete_per_tier(self):
        one = fed(heard(2.0, 3, 1.0), tier=NONE)
        self.assertFalse(one.measure)
        self.assertTrue(one.done())
        self.assertFalse(one.complete())
        one = fed(heard(2.0, 3, 1.0), tier=ONE_CYCLE)
        self.assertTrue(one.measure)
        self.assertFalse(one.done())
        one.mark_sleep(5.0)
        one.feed(Heard(10.0, -50))
        self.assertTrue(one.done())
        one = fed(heard(2.0, 3, 1.0) + [Heard(10.0, -50)], tier=TWO_CYCLES, wake=3)
        one.mark_sleep(5.0)
        self.assertFalse(one.done())
        one.mark_sleep(11.0)
        one.feed(Heard(20.0, -50))
        self.assertTrue(one.done())
        self.assertEqual(one.wakes_wanted, 3)


class TextTest(unittest.TestCase):
    def first_frame(self, one, reason=""):
        rep = report.Report(out=io.StringIO())
        cycle.first_frame_row(rep, one, reason)
        self.assertEqual([row.value for row in rep.rows], ["FIRST_FRAME"])
        return rep.rows[0].cells()

    def test_first_frame_from_the_banner(self):
        """The row counts from the banner, not the reset: a fox whose radio
        was up at 1.4 s and heard at 2.3 s passes at 0.9 s, and so does a
        Zigbee fox that formed its network for 14.6 s before its banner."""
        one = fed(heard(2.3, 3, 1.0), radio_time=1.4)
        self.assertAlmostEqual(one.first_transmission(), 2.3)
        self.assertAlmostEqual(one.first_frame_delay(), 0.9)
        self.assertEqual(self.first_frame(one),
                         ["FIRST_FRAME", "5", "banner 1.4 s after reset", "0.9 s after the banner", "pass"])
        one = fed(heard(15.0, 3, 1.0), radio_time=14.6, listen_time=0.5, granularity=1.0)
        self.assertEqual(self.first_frame(one),
                         ["FIRST_FRAME", "5", "banner 14.6 s after reset", "0.4 s after the banner", "pass"])

    def test_first_frame_over_the_allowance_fails(self):
        """The allowance is the boot allowance plus one frame spacing: 6 s for
        a 1 s radio, 65 s for a Zigbee fox with PACKET_INTERVAL 60, whose
        first Link Status may come that long after formation."""
        one = fed(heard(7.4, 3, 1.0), radio_time=1.4)
        self.assertEqual(self.first_frame(one),
                         ["FIRST_FRAME", "5", "banner 1.4 s after reset", "6.0 s after the banner", "pass"])
        one = fed(heard(7.5, 3, 1.0), radio_time=1.4)
        self.assertEqual(self.first_frame(one),
                         ["FIRST_FRAME", "5", "banner 1.4 s after reset", "6.1 s after the banner", "FAIL"])
        one = fed(heard(304.6, 3, 1.0), radio_time=1.4, tier=NONE)
        self.assertEqual(self.first_frame(one),
                         ["FIRST_FRAME", "5", "banner 1.4 s after reset", "303.2 s after the banner", "FAIL"])
        one = fed(heard(74.0, 3, 60.0), radio_time=14.6, granularity=60.0)
        self.assertEqual(self.first_frame(one)[3:], ["59.4 s after the banner", "pass"])
        one = fed(heard(80.0, 3, 60.0), radio_time=14.6, granularity=60.0)
        self.assertEqual(self.first_frame(one)[3:], ["65.4 s after the banner", "FAIL"])

    def test_first_frame_before_the_banner(self):
        """A beacon the stack sent before the banner reached the host counts
        from the banner too; a frame within 50 ms either way reads 0.0 s."""
        one = fed(heard(1.3, 3, 1.0), radio_time=1.4, listen_time=0.5)
        self.assertEqual(self.first_frame(one)[3:], ["0.1 s before the banner", "pass"])
        one = fed(heard(1.37, 3, 1.0), radio_time=1.4, listen_time=0.5)
        self.assertEqual(self.first_frame(one)[3:], ["0.0 s after the banner", "pass"])

    def test_first_frame_not_heard_or_not_reset(self):
        self.assertEqual(self.first_frame(fed([], radio_time=1.4)),
                         ["FIRST_FRAME", "5", "banner 1.4 s after reset", "-", "unverified: no frame from the fox"])
        self.assertEqual(self.first_frame(fed(heard(2.0, 3, 1.0))),
                         ["FIRST_FRAME", "5", "-", "-", "unverified: the banner was not timed"])
        one = fed(heard(2.0, 3, 1.0), reset_time=None)
        self.assertIsNone(one.first_transmission())
        self.assertEqual(self.first_frame(one, "--no-reset"),
                         ["FIRST_FRAME", "-", "-", "-", "serial only: --no-reset"])
        self.assertEqual(self.first_frame(one, "the fox was not reset"),
                         ["FIRST_FRAME", "-", "-", "-", "serial only: the fox was not reset"])

    def test_first_frame_when_the_capture_began_after_the_banner(self):
        """A capture tuned after the readback that hears the fox at once has
        an upper bound: within the allowance it passes, beyond it the row is
        unverified, since the fox may have been on the air unheard."""
        one = fed(heard(3.1, 3, 1.0), listen_time=3.0, radio_time=1.4)
        self.assertTrue(one.heard_at_once())
        self.assertAlmostEqual(one.listen_delay(), 1.6)
        self.assertEqual(self.first_frame(one)[3:],
                         ["by 1.7 s after the banner (the sniffer began listening 1.6 s after the banner)", "pass"])
        one = fed(heard(15.0, 3, 1.0), listen_time=15.0, radio_time=14.6)
        self.assertEqual(self.first_frame(one)[3:],
                         ["by 0.4 s after the banner (the sniffer began listening 0.4 s after the banner)", "pass"])
        one = fed(heard(9.1, 3, 1.0), listen_time=9.0, radio_time=1.4)
        self.assertEqual(self.first_frame(one)[3:],
                         ["by 7.7 s after the banner (the sniffer began listening 7.6 s after the banner)",
                          "unverified: heard as soon as the sniffer listened"])

    def test_capture_listening_before_the_banner_hears_the_first_frame(self):
        """A capture tuned on the Starting on channel line was listening
        before the radio came up, so its first frame is exact even when it
        came within one frame spacing of the capture starting."""
        one = fed(heard(1.5, 3, 1.0), listen_time=0.5, radio_time=1.4)
        self.assertFalse(one.heard_at_once())
        self.assertEqual(one.listen_delay(), 0.0)
        self.assertAlmostEqual(one.late(), 0.5)
        self.assertEqual(self.first_frame(one)[3:], ["0.1 s after the banner", "pass"])
        one = fed(heard(3.1, 3, 1.0), listen_time=3.0)
        self.assertFalse(one.heard_at_once())

    def test_fox_heard_after_the_capture_began_is_not_late(self):
        one = fed(heard(4.5, 2, 15.0) + [Heard(24.5, -50)], listen_time=3.0, radio_time=1.4)
        self.assertFalse(one.heard_at_once())
        self.assertAlmostEqual(one.late(), 3.0)
        self.assertAlmostEqual(one.boot_bound(), 7.5)
        self.assertEqual(self.first_frame(one)[3:], ["3.1 s after the banner", "pass"])

    def test_boot_bound_is_the_first_transmission_plus_the_late_start(self):
        self.assertAlmostEqual(fed(heard(2.3, 3, 1.0)).boot_bound(), 2.3)
        self.assertAlmostEqual(fed(heard(15.0, 3, 1.0), listen_time=15.0).boot_bound(), 30.0)
        self.assertIsNone(fed([]).boot_bound())
        self.assertIsNone(fed(heard(2.0, 3, 1.0), reset_time=None).boot_bound())

    def test_first_wake_line(self):
        """The owner's Zigbee first boot: heard from 15 s, on the air 285 s,
        back 1.8 s after its last frame, which is 301.8 s after the reset."""
        one = fed(heard(15.0, 286, 1.0) + [Heard(301.8, -50)], tier=TWO_CYCLES, listen_time=15.0)
        one.mark_sleep(300.4)
        self.assertEqual(cycle.first_wake_line(one),
                         "first wake: on the air 285.0 s, then off the air 1.8 s, cycle time 301.8 s")
        one = fed(heard(15.0, 286, 1.0), tier=TWO_CYCLES, listen_time=15.0)
        self.assertEqual(cycle.first_wake_line(one), "first wake: on the air 285.0 s")
        self.assertIsNone(cycle.first_wake_line(fed([], tier=TWO_CYCLES)))

    def test_median_rssi(self):
        one = fed([Heard(1.0, -40), Heard(2.0, -44), Heard(3.0, -42), Heard(4.0, None)])
        self.assertEqual(one.rssi_text(), "median -42 dBm over 3 frames")
        self.assertEqual(fed([Heard(1.0, -61)]).rssi_text(), "median -61 dBm over 1 frame")
        self.assertEqual(fed([Heard(1.0, -41), Heard(2.0, -42)]).rssi_text(), "median -42 dBm over 2 frames")
        self.assertIsNone(fed([]).rssi_text())
        self.assertIsNone(fed([Heard(1.0, None)]).rssi_text())


class ExactRowsTest(unittest.TestCase):
    """The two-cycle tier: TIME_TO_WAKE from wake 2's span, TIME_TO_SLEEP from
    the gap to wake 3, CYCLE_TIME from the period between them. The Classic
    HARD block is 30/30 with granularity 3, so wake 2 passes between 27 and
    35 s on the air, the gap between 22 and 38 s and the period within 59-61 s."""

    def setUp(self):
        self.report = report.Report(out=io.StringIO())
        self.block, self.readback = block_and_readback("classic_discoverable", ["HARD"], "classic_hard.log")

    def rows(self, one, random_channel=False, block=None, readback=None, last_cycle=None):
        self.report.rows.clear()
        cycle.rows(self.report, block or self.block, readback or self.readback, one, random_channel, last_cycle)
        return {row.value: row for row in self.report.rows}

    def classic(self, first2=62.0, span2=29.0, first3=122.0, granularity=3.0, sleeps=(32.5, 92.5)):
        """A 30/30 fox heard from 2 s after the reset, with wake 2 and wake 3
        where the arguments put them."""
        frames = heard(2.0, 15, 2.0) + heard(first2, int(span2) + 1, 1.0) + heard(first3, 3, 1.0)
        one = fed(frames, tier=TWO_CYCLES, granularity=granularity, wake=30)
        for when in sleeps:
            one.mark_sleep(when)
        return one

    def test_healthy_30_30_fox_passes_all_three(self):
        rows = self.rows(self.classic())
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "30", "30", "on the air 29.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "30", "30", "off the air 31.0 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "60.0 s", "pass"])
        self.assertEqual([row.value for row in self.report.rows], ["TIME_TO_WAKE", "TIME_TO_SLEEP", "CYCLE_TIME"])
        self.assertEqual(self.report.exit_code(), report.EXIT_OK)

    def test_cycle_time_serial_column_is_the_last_cycle_figure(self):
        rows = self.rows(self.classic(), last_cycle=60.0)
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "60.0", "60.0 s", "pass"])

    def test_owners_zigbee_figures_pass_with_time_to_sleep_0(self):
        """Wake 1 heard from 15 s for 285 s, back after 1.8 s; wake 2 on the
        air the full 300 s; wake 3 after a 2.1 s reboot: the period runs
        302.1 s, within TIME_TO_WAKE + BOOT_ALLOWANCE + tolerance."""
        block, readback = block_and_readback("zigbee_coordinator", ["COORDINATOR", "EASY"], "zigbee_easy.log")
        frames = heard(15.0, 286, 1.0) + heard(301.8, 301, 1.0) + heard(603.9, 2, 1.0)
        one = fed(frames, tier=TWO_CYCLES, listen_time=15.0, wake=300)
        one.mark_sleep(300.4)
        one.mark_sleep(602.1)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "300", "300", "on the air 300.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "0", "0", "off the air 2.1 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "300", "-", "302.1 s", "pass"])
        self.assertEqual(cycle.first_wake_line(one),
                         "first wake: on the air 285.0 s, then off the air 1.8 s, cycle time 301.8 s")
        # The same fox rebooting in 9 s is off the air past 0 + 5 + 1 and
        # runs its cycle past 300 + 5 + 3.
        frames = heard(15.0, 286, 1.0) + heard(301.8, 301, 1.0) + heard(610.9, 2, 1.0)
        one = fed(frames, tier=TWO_CYCLES, listen_time=15.0, wake=300)
        one.mark_sleep(300.4)
        one.mark_sleep(602.1)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "0", "0", "off the air 9.1 s", "FAIL"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "300", "-", "309.1 s", "FAIL"])

    def test_span_tolerances(self):
        self.assertEqual(self.rows(self.classic(span2=27.0))["TIME_TO_WAKE"].verdict, "pass")
        rows = self.rows(self.classic(span2=26.0))
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "30", "30", "on the air 26.0 s", "FAIL"])
        self.assertEqual(self.rows(self.classic(span2=35.0, sleeps=(32.5, 97.5)))["TIME_TO_WAKE"].verdict, "pass")
        self.assertEqual(self.rows(self.classic(span2=36.0, sleeps=(32.5, 98.5)))["TIME_TO_WAKE"].verdict, "FAIL")

    def test_period_four_seconds_off_fails_cycle_time_with_the_number(self):
        rows = self.rows(self.classic(first3=126.0))
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "pass")
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "30", "30", "off the air 35.0 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "64.0 s", "FAIL"])
        self.assertEqual(self.report.exit_code(), report.EXIT_FAIL)
        rows = self.rows(self.classic(first3=118.0))
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "56.0 s", "FAIL"])

    def test_period_tolerance_is_one_second_or_one_percent(self):
        self.assertEqual(self.rows(self.classic(first3=123.0))["CYCLE_TIME"].verdict, "pass")
        self.assertEqual(self.rows(self.classic(first3=123.1))["CYCLE_TIME"].verdict, "FAIL")
        # A 255/45 fox: one percent of 300 s is 3 s.
        block, readback = block_and_readback("wifi_ap_client", ["AP", "HARD"], "wifi_hard_ap.log",
                                             [("TIME_TO_WAKE 30", "TIME_TO_WAKE 255"), ("Time to wake: 30s", "Time to wake: 255s")])
        frames = heard(2.0, 2, 255.0) + heard(302.0, 2, 255.0) + [Heard(604.9, -50)]
        one = fed(frames, tier=TWO_CYCLES, wake=255)
        one.mark_sleep(257.5)
        one.mark_sleep(557.5)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "300", "-", "302.9 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "45", "45", "off the air 47.9 s", "pass"])
        frames = heard(2.0, 2, 255.0) + heard(302.0, 2, 255.0) + [Heard(605.1, -50)]
        one = fed(frames, tier=TWO_CYCLES, wake=255)
        one.mark_sleep(257.5)
        one.mark_sleep(557.5)
        self.assertEqual(self.rows(one, block=block, readback=readback)["CYCLE_TIME"].verdict, "FAIL")

    def test_sleeping_fox_heard_during_its_sleep_fails_time_to_sleep(self):
        """A 30/30 fox back on the air 20 s after its last frame slept less
        than TIME_TO_SLEEP - BOOT_ALLOWANCE - g; the period is then short
        too, and CYCLE_TIME says by how much."""
        one = self.classic(first3=111.0)
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "30", "30", "off the air 20.0 s", "FAIL"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "49.0 s", "FAIL"])
        self.assertEqual(self.rows(self.classic(first3=113.0))["TIME_TO_SLEEP"].verdict, "pass")
        # A gap over TIME_TO_SLEEP + BOOT_ALLOWANCE + g fails too.
        self.assertEqual(self.rows(self.classic(first3=130.0))["TIME_TO_SLEEP"].cells()[3:],
                         ["off the air 39.0 s", "FAIL"])
        self.assertEqual(self.rows(self.classic(first3=129.0))["TIME_TO_SLEEP"].verdict, "pass")

    def test_time_to_sleep_0_has_no_lower_bound(self):
        block, readback = block_and_readback("zigbee_coordinator", ["COORDINATOR", "EASY"], "zigbee_easy.log")
        frames = heard(2.0, 301, 1.0) + heard(304.0, 301, 1.0) + [Heard(606.0, -50)]
        one = fed(frames, tier=TWO_CYCLES, wake=300)
        one.mark_sleep(302.4)
        one.mark_sleep(604.4)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "0", "0", "off the air 2.0 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "300", "-", "302.0 s", "pass"])

    def test_zigbee_last_link_status_precedes_the_stop_by_the_interval(self):
        """A HARD coordinator sends a Link Status every 15 s, so the last one
        can come up to 15 s before the radio stops; wake 2's span may be short
        by the granularity."""
        block, readback = block_and_readback("zigbee_coordinator", ["COORDINATOR", "HARD"], "zigbee_hard.log",
                                             [("TIME_TO_WAKE 300", "TIME_TO_WAKE 60"), ("Time to wake: 300s", "Time to wake: 60s")])
        # Wake 2 from 66 s: Link Status at 66, 81, 96, 111; radio stops at
        # 126; wake 3's first frame at 126 + 3.
        frames = heard(3.0, 4, 15.0) + heard(66.0, 4, 15.0) + [Heard(129.0, -50)]
        one = fed(frames, tier=TWO_CYCLES, granularity=15.0, wake=60)
        one.mark_sleep(63.2)
        one.mark_sleep(126.2)
        rows = self.rows(one, block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "60", "60", "on the air 45.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "0", "0", "off the air 18.0 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "63.0 s", "pass"])

    def test_wake_3_never_comes_fails_time_to_sleep_and_cycle_time(self):
        one = fed(heard(2.0, 15, 2.0) + heard(62.0, 30, 1.0), tier=TWO_CYCLES, granularity=3.0, wake=30)
        one.mark_sleep(32.5)
        one.mark_sleep(92.5)
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "30", "30", "on the air 29.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(),
                         ["TIME_TO_SLEEP", "30", "30", "wake 3 not heard before the deadline", "FAIL"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "wake 3 not heard before the deadline", "FAIL"])
        self.assertEqual(self.report.exit_code(), report.EXIT_FAIL)

    def test_wake_2_never_comes_fails_all_three(self):
        one = fed(heard(2.0, 15, 2.0), tier=TWO_CYCLES, granularity=3.0, wake=30)
        one.mark_sleep(32.5)
        rows = self.rows(one)
        for value in ("TIME_TO_WAKE", "TIME_TO_SLEEP", "CYCLE_TIME"):
            self.assertEqual(rows[value].air, "wake 2 not heard before the deadline", value)
            self.assertEqual(rows[value].verdict, "FAIL", value)

    def test_random_channel_wake_3_texts(self):
        one = fed(heard(2.0, 15, 2.0) + heard(62.0, 30, 1.0), tier=TWO_CYCLES, granularity=3.0, wake=30)
        one.mark_sleep(32.5)
        one.mark_sleep(92.5)
        one.retunes[2] = (9, 61.0)
        rows = self.rows(one, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].air, "wake 3 not heard: its channel was not seen on serial")
        self.assertEqual(rows["CYCLE_TIME"].air, "wake 3 not heard: its channel was not seen on serial")
        one.retunes[3] = (4, 123.4)
        rows = self.rows(one, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].air, "wake 3 not heard on channel 4 after retuning at +123.4 s")
        self.assertEqual(rows["CYCLE_TIME"].verdict, "FAIL")
        # A retune slow enough to miss the period says so.
        one.feed(Heard(126.0, -50))
        rows = self.rows(one, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["off the air 35.0 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells()[3:], ["64.0 s, retuned at +123.4 s", "FAIL"])

    def test_wake_2_not_over_at_the_deadline(self):
        clock = FakeClock(0.0)
        one = fed(heard(2.0, 15, 2.0) + heard(62.0, 10, 1.0), tier=TWO_CYCLES, granularity=3.0, wake=30, clock=clock)
        one.mark_sleep(32.5)
        clock.now = 73.0
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].cells()[3:], ["-", "unverified: wake 2 not over before the deadline"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["wake 2 had not ended at the deadline", "FAIL"])
        self.assertEqual(rows["CYCLE_TIME"].cells()[3:], ["wake 2 had not ended at the deadline", "FAIL"])
        # A fox still on the air past TIME_TO_WAKE + 5 has failed its wake.
        one = fed(heard(2.0, 15, 2.0) + heard(62.0, 40, 1.0), tier=TWO_CYCLES, granularity=3.0, wake=30, clock=clock)
        one.mark_sleep(32.5)
        clock.now = 102.0
        rows = self.rows(one)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "30", "30", "on the air 39.0 s", "FAIL"])

    def test_no_frame_from_the_fox(self):
        rows = self.rows(fed([], tier=TWO_CYCLES))
        for value in ("TIME_TO_WAKE", "TIME_TO_SLEEP", "CYCLE_TIME"):
            self.assertEqual(rows[value].cells()[3:], ["-", "unverified: no frame from the fox"], value)
        self.assertEqual(rows["CYCLE_TIME"].header, "60")

    def test_serial_disagreement_is_a_fail_before_the_air(self):
        block, readback = block_and_readback("classic_discoverable", ["HARD"], "classic_hard.log",
                                             [("Time to wake: 30s", "Time to wake: 20s")])
        rows = self.rows(self.classic(), block=block, readback=readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "30", "20", "-", "FAIL"])
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "pass")
        self.assertEqual(rows["CYCLE_TIME"].verdict, "pass")


class FirstBootRowsTest(unittest.TestCase):
    """The one-cycle tier: the three rows judge wake 1 and the gap to wake 2
    with the first-boot tolerances, and say so with ``first boot:``."""

    def setUp(self):
        self.report = report.Report(out=io.StringIO())
        self.classic_block, self.classic_readback = block_and_readback("classic_discoverable", ["HARD"],
                                                                       "classic_hard.log")
        self.zigbee_block, self.zigbee_readback = block_and_readback("zigbee_coordinator", ["COORDINATOR", "EASY"],
                                                                     "zigbee_easy.log")
        self.wifi_block, self.wifi_readback = block_and_readback("wifi_ap_client", ["AP", "EASY"], "wifi_easy_ap.log")

    def rows(self, one, block, readback, random_channel=False, last_cycle=None):
        self.report.rows.clear()
        cycle.rows(self.report, block, readback, one, random_channel, last_cycle)
        return {row.value: row for row in self.report.rows}

    def test_owners_zigbee_first_boot_passes_all_three(self):
        """Reset at 0, the capture listening from 15 s and hearing the fox at
        once, on the air 285 s, back 1.8 s after the last frame: the span may
        be short by the 30 s boot bound plus the granularity, the gap of a
        TIME_TO_SLEEP 0 fox has no lower bound, and the 301.8 s first cycle is
        under 300 + 30 + 5 + 3."""
        one = fed(heard(15.0, 286, 1.0) + [Heard(301.8, -50)], listen_time=15.0, wake=300)
        one.mark_sleep(300.4)
        self.assertAlmostEqual(one.boot_bound(), 30.0)
        rows = self.rows(one, self.zigbee_block, self.zigbee_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(),
                         ["TIME_TO_WAKE", "300", "300", "first boot: on the air 285.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(),
                         ["TIME_TO_SLEEP", "0", "0", "first boot: off the air 1.8 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "300", "-", "first boot: 301.8 s", "pass"])
        self.assertEqual(self.report.exit_code(), report.EXIT_OK)
        rows = self.rows(one, self.zigbee_block, self.zigbee_readback, last_cycle=301.6)
        self.assertEqual(rows["CYCLE_TIME"].serial, "301.6")

    def test_classic_30_30_with_a_3_s_boot_passes(self):
        """The sleep absorbed the boot, so the first cycle is exactly 60 s
        from the reset to wake 2's first frame when wake 2 is heard at once."""
        one = fed(heard(3.0, 28, 1.0) + [Heard(60.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(30.5)
        rows = self.rows(one, self.classic_block, self.classic_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "30", "30", "first boot: on the air 27.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(), ["TIME_TO_SLEEP", "30", "30", "first boot: off the air 30.0 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "first boot: 60.0 s", "pass"])

    def test_classic_first_cycle_includes_wake_2_boot(self):
        """The firmware's cycle ends at wake 2's boot and the first frame
        comes its own boot later, so a 63 s first cycle of a fox that boots
        in 3 s passes; 70 s is past 60 + 5 + 1 and fails."""
        one = fed(heard(3.0, 28, 1.0) + [Heard(63.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(30.5)
        rows = self.rows(one, self.classic_block, self.classic_readback)
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "first boot: 63.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["first boot: off the air 33.0 s", "pass"])
        one = fed(heard(3.0, 28, 1.0) + [Heard(70.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(30.5)
        rows = self.rows(one, self.classic_block, self.classic_readback)
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "60", "-", "first boot: 70.0 s", "FAIL"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["first boot: off the air 40.0 s", "FAIL"])
        self.assertEqual(self.report.exit_code(), report.EXIT_FAIL)

    def test_classic_heard_10_s_short_fails_time_to_wake(self):
        one = fed(heard(3.0, 18, 1.0) + [Heard(60.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(30.5)
        rows = self.rows(one, self.classic_block, self.classic_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "30", "30", "first boot: on the air 17.0 s", "FAIL"])
        self.assertEqual(rows["CYCLE_TIME"].verdict, "pass")
        # Short by exactly the boot bound plus the granularity still passes.
        one = fed(heard(3.0, 25, 1.0) + [Heard(60.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(30.5)
        self.assertEqual(self.rows(one, self.classic_block, self.classic_readback)["TIME_TO_WAKE"].verdict, "pass")
        # Never long: past TIME_TO_WAKE + 5 is a FAIL.
        one = fed(heard(3.0, 36, 1.0) + [Heard(60.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(38.5)
        rows = self.rows(one, self.classic_block, self.classic_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells()[3:], ["first boot: on the air 35.0 s", "pass"])
        one = fed(heard(3.0, 37, 1.0) + [Heard(60.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(39.5)
        rows = self.rows(one, self.classic_block, self.classic_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells()[3:], ["first boot: on the air 36.0 s", "FAIL"])

    def test_classic_heard_during_its_first_sleep_fails_time_to_sleep(self):
        """A 30/30 fox back 15 s after its last frame: under TIME_TO_SLEEP
        minus the boot bound, the allowance and the granularity (30 - 3 - 5 - 3)."""
        one = fed(heard(3.0, 28, 1.0) + [Heard(45.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(30.5)
        rows = self.rows(one, self.classic_block, self.classic_readback)
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["first boot: off the air 15.0 s", "FAIL"])
        one = fed(heard(3.0, 28, 1.0) + [Heard(49.0, -50)], granularity=3.0, wake=30)
        one.mark_sleep(30.5)
        self.assertEqual(self.rows(one, self.classic_block, self.classic_readback)["TIME_TO_SLEEP"].verdict, "pass")

    def test_wifi_15_5_with_a_3_s_boot_absorbed_by_the_sleep_passes(self):
        one = fed(heard(3.0, 13, 1.0) + [Heard(20.0, -50)], wake=15)
        one.mark_sleep(15.3)
        self.assertAlmostEqual(one.boot_bound(), 3.0)
        rows = self.rows(one, self.wifi_block, self.wifi_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells()[3:], ["first boot: on the air 12.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["first boot: off the air 5.0 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "20", "-", "first boot: 20.0 s", "pass"])

    def test_late_wifi_capture_hears_the_first_wake_short(self):
        """A Wi-Fi capture that began 3 s after the reset and heard the fox
        at once: the first 1.5 s of beacons went unheard, and the bound of
        3 + 3 s covers it."""
        one = fed(heard(3.0, 2, 13.5) + [Heard(21.5, -50)], listen_time=3.0, radio_time=1.4, wake=15)
        one.mark_sleep(16.7)
        self.assertTrue(one.heard_at_once())
        self.assertAlmostEqual(one.boot_bound(), 6.0)
        rows = self.rows(one, self.wifi_block, self.wifi_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells()[3:], ["first boot: on the air 13.5 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["first boot: off the air 5.0 s", "pass"])
        self.assertEqual(rows["CYCLE_TIME"].cells()[3:], ["first boot: 21.5 s", "pass"])
        # Short by more than the bound is still a FAIL.
        one = fed(heard(3.0, 2, 7.9) + [Heard(21.5, -50)], listen_time=3.0, wake=15)
        one.mark_sleep(16.7)
        self.assertEqual(self.rows(one, self.wifi_block, self.wifi_readback)["TIME_TO_WAKE"].verdict, "FAIL")

    def test_wake_2_never_comes_fails_time_to_sleep_and_cycle_time(self):
        one = fed(heard(1.5, 2, 15.0), wake=15)
        one.mark_sleep(17.0)
        rows = self.rows(one, self.wifi_block, self.wifi_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells()[3:], ["first boot: on the air 15.0 s", "pass"])
        self.assertEqual(rows["TIME_TO_SLEEP"].cells(),
                         ["TIME_TO_SLEEP", "5", "5", "wake 2 not heard before the deadline", "FAIL"])
        self.assertEqual(rows["CYCLE_TIME"].cells(), ["CYCLE_TIME", "20", "-", "wake 2 not heard before the deadline", "FAIL"])
        self.assertEqual(self.report.exit_code(), report.EXIT_FAIL)

    def test_random_channel_wake_2_texts(self):
        one = fed(heard(1.5, 2, 15.0), wake=15)
        one.mark_sleep(17.0)
        rows = self.rows(one, self.wifi_block, self.wifi_readback, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].air, "wake 2 not heard: its channel was not seen on serial")
        self.assertEqual(rows["CYCLE_TIME"].air, "wake 2 not heard: its channel was not seen on serial")
        one.retunes[2] = (9, 23.4)
        rows = self.rows(one, self.wifi_block, self.wifi_readback, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].air, "wake 2 not heard on channel 9 after retuning at +23.4 s")
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "FAIL")
        # A slow retune that pushed the first cycle past its bound says so.
        one.feed(Heard(30.0, -50))
        rows = self.rows(one, self.wifi_block, self.wifi_readback, random_channel=True)
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["first boot: off the air 13.5 s, retuned at +23.4 s", "FAIL"])
        self.assertEqual(rows["CYCLE_TIME"].cells()[3:], ["first boot: 30.0 s, retuned at +23.4 s", "FAIL"])

    def test_wake_1_not_over_at_the_deadline(self):
        clock = FakeClock(0.0)
        one = fed(heard(1.5, 10, 1.0), clock=clock, wake=15)
        clock.now = 12.0
        rows = self.rows(one, self.wifi_block, self.wifi_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].verdict, "unverified")
        self.assertEqual(rows["TIME_TO_WAKE"].reason, "wake 1 not over before the deadline")
        self.assertEqual(rows["TIME_TO_SLEEP"].cells()[3:], ["wake 1 had not ended at the deadline", "FAIL"])
        self.assertEqual(rows["CYCLE_TIME"].cells()[3:], ["wake 1 had not ended at the deadline", "FAIL"])
        one = fed(heard(1.5, 30, 1.0), clock=clock, wake=15)
        clock.now = 31.0
        rows = self.rows(one, self.wifi_block, self.wifi_readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "15", "15", "first boot: on the air 29.0 s", "FAIL"])

    def test_no_frame_and_serial_disagreement(self):
        rows = self.rows(fed([], wake=15), self.wifi_block, self.wifi_readback)
        for value in ("TIME_TO_WAKE", "TIME_TO_SLEEP", "CYCLE_TIME"):
            self.assertEqual(rows[value].cells()[3:], ["-", "unverified: no frame from the fox"], value)
        block, readback = block_and_readback("wifi_ap_client", ["AP", "EASY"], "wifi_easy_ap.log",
                                             [("Time to wake: 15s", "Time to wake: 20s")])
        one = fed(heard(3.0, 13, 1.0) + [Heard(20.0, -50)], wake=15)
        one.mark_sleep(15.3)
        rows = self.rows(one, block, readback)
        self.assertEqual(rows["TIME_TO_WAKE"].cells(), ["TIME_TO_WAKE", "15", "20", "-", "FAIL"])
        self.assertEqual(rows["TIME_TO_SLEEP"].verdict, "pass")
        self.assertEqual(rows["CYCLE_TIME"].verdict, "pass")


class ListenTest(unittest.TestCase):
    """The capture loop: frames fed, the follower polled, the retune made once
    per wake, the loop ending as soon as the tier's last wake is heard."""

    class Follower:
        def __init__(self, boundaries=(), channels=None):
            self._boundaries = list(boundaries)
            self._channels = channels or {}
            self.polls = 0

        def poll(self):
            self.polls += 1

        def boundaries(self):
            return list(self._boundaries)

        def channel(self, wake=2):
            return self._channels.get(wake)

        def channel_label(self, wake=2):
            return "Operating channel" if wake in self._channels else None

    def test_stops_at_the_goal_without_a_cycle_to_measure(self):
        dl, clock = deadline(60)
        reads = []

        def read(timeout):
            reads.append(timeout)
            clock.advance(timeout)
            return [Heard(clock.now, -50)]

        one = Cycle(0.0, 1.0, NONE, clock=clock)
        cycle.listen(one, dl, read, lambda: len(one.frames) >= 2)
        self.assertEqual(len(one.frames), 2)
        self.assertEqual(reads, [cycle.POLL, cycle.POLL])
        # The loop stamps when the capture began; a stamp given is kept.
        self.assertEqual(one.listen_time, 1000.0)
        one = Cycle(0.0, 1.0, NONE, clock=clock, listen_time=0.0)
        cycle.listen(one, dl, read, lambda: True)
        self.assertEqual(one.listen_time, 0.0)

    def test_one_cycle_tier_stops_at_wake_2_first_frame(self):
        dl, clock = deadline(60, start=0.0)
        frames = iter([[Heard(1.0, -50)], [Heard(2.0, -50)]] + [[]] * 100 + [[Heard(30.0, -50)], [Heard(30.3, -50)]])

        def read(timeout):
            clock.advance(timeout)
            return next(frames, [])

        follower = self.Follower(boundaries=[3.0], channels={2: 9})
        tuned = []
        one = Cycle(0.0, 1.0, ONE_CYCLE, clock=clock)
        cycle.listen(one, dl, read, lambda: True, follower, tuned.append)
        self.assertEqual(tuned, [9])
        self.assertEqual(one.retunes[2][0], 9)
        self.assertEqual(one.sleep_times, [3.0])
        self.assertTrue(one.complete())
        self.assertEqual([f.time for f in one.frames], [1.0, 2.0, 30.0])
        self.assertGreater(follower.polls, 100)
        self.assertLess(clock.now, 26.0)

    def test_two_cycle_tier_goes_on_to_wake_3_and_retunes_each_wake(self):
        dl, clock = deadline(120, start=0.0)
        batches = {1.0: [Heard(1.0, -50)], 30.0: [Heard(30.0, -50)], 60.0: [Heard(60.0, -50)], 60.25: [Heard(60.25, -50)]}

        def read(timeout):
            clock.advance(timeout)
            return batches.get(round(clock.now, 2), [])

        follower = self.Follower(boundaries=[3.0, 33.0], channels={2: 9, 3: 4})
        tuned = []
        one = Cycle(0.0, 1.0, TWO_CYCLES, clock=clock)
        cycle.listen(one, dl, read, lambda: True, follower, tuned.append)
        self.assertEqual(tuned, [9, 4])
        self.assertEqual(one.retunes[2][0], 9)
        self.assertEqual(one.retunes[3][0], 4)
        self.assertEqual(one.sleep_times, [3.0, 33.0])
        self.assertEqual(one.wakes(), 3)
        self.assertTrue(one.complete())
        self.assertEqual([f.time for f in one.frames], [1.0, 30.0, 60.0])
        self.assertLess(clock.now, 61.0)

    def test_stops_at_the_deadline(self):
        dl, clock = deadline(2, start=0.0)
        one = Cycle(0.0, 1.0, TWO_CYCLES, clock=clock)
        cycle.listen(one, dl, lambda timeout: clock.advance(timeout) or [], lambda: True)
        self.assertTrue(dl.expired())
        self.assertFalse(one.complete())


if __name__ == "__main__":
    unittest.main()
