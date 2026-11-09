"""The fox's wake and sleep cycle measured on the air: the budget tiers, the
boot allowance, the frame log, the end of each wake, the three timer rows, the
first transmission and first wake lines and the median RSSI.

The firmware keeps one cycle, one wake-up to the next, at exactly
``TIME_TO_WAKE + TIME_TO_SLEEP`` seconds from the second wake on: the radio
goes on right after boot, stays on for ``TIME_TO_WAKE`` seconds once the
readback is printed, and the sleep is shortened by the boot and start-up time
of that cycle. The first boot is different. The reset, the boot, the stack's
start-up (a Zigbee fox forms its network) and the readback all happen before
the wake timer starts, and a fox whose ``TIME_TO_SLEEP`` cannot absorb them
reboots at once, so wake 1 is heard for less than ``TIME_TO_WAKE`` and the
first cycle runs long by the boot. The exact figures the firmware promises
are therefore wake 2's span and the period from wake 2 to wake 3, and those
are what a run with the budget for two cycles judges; a run with the budget
for one cycle judges wake 1 and the gap to wake 2 against what a first boot
can deliver, with wider tolerances.

The budget is decided up front from ``--timeout`` and the block's timers,
with ``C = TIME_TO_WAKE + TIME_TO_SLEEP`` and ``B = BOOT_ALLOWANCE``:

- ``NONE``, ``--timeout < C + B``: the identity rows only, as fast as the
  air allows; the timers stay serial only.
- ``ONE_CYCLE``, ``C + B <= --timeout < 2C + B``: the capture goes on through
  the first sleep to wake 2's first frame, and the rows judge the first boot.
- ``TWO_CYCLES``, ``--timeout >= 2C + B``: the capture goes on to wake 3's
  first frame, and the rows judge wake 2 and the period to wake 3.

Below the two-cycle tier the run ends as soon as what it set out to measure
is in, and a suggestion line after the summary names the ``--timeout`` that
measures the exact cycle time.

``Cycle`` records every frame attributed to the fox as ``Heard(time, rssi)``
on the wall clock (``time.time()``, the clock the pcap timestamps and the
scanners already use), splits them into wakes, and derives the numbers the
rows judge: the span of a wake (its first to its last frame), the gap to the
next wake (its last frame to the next wake's first), the period (first frame
to first frame) and the first cycle (the reset to wake 2's first frame).

A wake ends with the serial port when it is being followed: the ``Going to
sleep`` line, or the port vanishing as a native USB board's does in deep
sleep. Both come after the radio stopped, so every frame after that instant
belongs to the next wake. Silence is the other signal: the fox quiet for
longer than the radio's frame granularity plus the boot allowance. While the
serial port is followed and has not spoken, silence only counts after the
latest moment the wake can end, its first frame plus ``TIME_TO_WAKE`` plus
``BOOT_ALLOWANCE``, so that a pause between inquiry responses is never taken
for the sleep; without a serial port it counts anywhere.

The Bluetooth scans start before the fox is reset, so they hear wake 1's
true first frame. The Wi-Fi and Zigbee captures start after the serial
readback, which names the channel, and so begin ``late`` seconds after the
reset; the fox may have been on the air that long before it was heard. The
first transmission line says the figure is an upper bound when the fox was
heard as soon as the capture began, and the first-boot rows allow for it.

``listen`` is the loop every backend runs: it reads frames, polls the serial
follower, retunes the sniffer when a random-channel fox reports the channel
of its next wake, and stops when the backend has what it needs and the cycle
is done, or at the deadline.
"""
from __future__ import annotations

import math
import statistics
import threading
import time
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

from .conf import Block
from .report import FAIL, PASS, Report, UNVERIFIED
from .serial_fox import Readback

# Seconds from a reset to the first frame, which is also the whole off-air
# gap of a TIME_TO_SLEEP 0 fox. Boot plus Arduino init is about 1 s on every
# board, the Bluedroid stack about 1 s more, the Wi-Fi stack under 0.5 s, the
# Zigbee stack 1-3 s to its first frame; 5 s holds with a margin on every fox.
# The first transmission line shows the measured figure on every run, so this
# constant can be corrected from evidence.
BOOT_ALLOWANCE = 5.0
# Seconds between polls of the capture and the serial port in ``listen``.
POLL = 0.25
# The smallest frame granularity used for a radio whose cadence is observed.
MIN_GRANULARITY = 1.0
# The period tolerance is the larger of this and one percent of the cycle.
PERIOD_TOLERANCE = 1.0
PERIOD_TOLERANCE_RATIO = 0.01

# The budget tiers, decided from --timeout and the block's timers.
NONE = "none"
ONE_CYCLE = "one cycle"
TWO_CYCLES = "two cycles"
# The wakes a tier hears before its capture may stop.
WAKES = {NONE: 1, ONE_CYCLE: 2, TWO_CYCLES: 3}
# The prefix of an air text judged with the first-boot rules.
FIRST_BOOT = "first boot: "


class Heard(NamedTuple):
    """One frame from the fox: when it was heard and its RSSI in dBm."""

    time: float
    rssi: Optional[int]


class HeardLog:
    """Frames per address, filled by a scan thread and taken in batches by
    the main thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._heard: Dict[str, List[Heard]] = {}

    def add(self, address: str, when: float, rssi: Optional[int]) -> None:
        with self._lock:
            self._heard.setdefault(address.upper(), []).append(Heard(when, rssi))

    def take(self, address: str) -> List[Heard]:
        """Every frame from ``address`` since the last call."""
        with self._lock:
            return self._heard.pop(address.upper(), [])


def needed(wake: int, sleep: int, cycles: int = 2) -> float:
    """The --timeout that lets a run hear ``cycles`` cycles after the boot."""
    return cycles * (wake + sleep) + BOOT_ALLOWANCE


def tier(wake: int, sleep: int, timeout: float) -> str:
    """The budget tier of a run: two cycles when --timeout covers
    ``2 * (TIME_TO_WAKE + TIME_TO_SLEEP) + BOOT_ALLOWANCE``, one cycle when
    it covers one cycle plus the allowance, none otherwise."""
    if timeout >= needed(wake, sleep, 2):
        return TWO_CYCLES
    if timeout >= needed(wake, sleep, 1):
        return ONE_CYCLE
    return NONE


def full_timeout(wake: int, sleep: int) -> int:
    """The whole-second --timeout the two-cycle tier needs."""
    return int(math.ceil(needed(wake, sleep, 2)))


def tier_line(which: str, wake: int, sleep: int, timeout: float) -> str:
    """The line printed before the table saying what the run will measure."""
    cycle_seconds = wake + sleep
    if which == TWO_CYCLES:
        return ("measuring the cycle time from wake 2 and wake 3 (--timeout %g covers two cycles of %d s "
                "plus the %g s boot allowance)" % (timeout, cycle_seconds, BOOT_ALLOWANCE))
    if which == ONE_CYCLE:
        return ("judging the first boot with wider tolerances (--timeout %g covers one cycle of %d s plus "
                "the %g s boot allowance; two cycles need %d)"
                % (timeout, cycle_seconds, BOOT_ALLOWANCE, full_timeout(wake, sleep)))
    return ("TIME_TO_WAKE and TIME_TO_SLEEP serial only (--timeout %g is under the %g s one cycle of %d s "
            "plus the %g s boot allowance needs)" % (timeout, needed(wake, sleep, 1), cycle_seconds, BOOT_ALLOWANCE))


def suggestion(which: str, wake: int, sleep: int) -> Optional[str]:
    """The line after the summary of a run below the two-cycle tier, naming
    the --timeout that measures the exact cycle time; None in that tier."""
    if which == NONE:
        return "run with --timeout %d to measure the cycle time" % full_timeout(wake, sleep)
    if which == ONE_CYCLE:
        return ("run with --timeout %d for the exact cycle time; this run judged the first boot with wider "
                "tolerances" % full_timeout(wake, sleep))
    return None


class Cycle:
    """The frames heard from the fox and what they say about its cycle.

    ``reset_time`` is when the fox left reset, None when it was not reset
    (``--no-reset``, or a USB stack that has no reset).
    ``granularity`` is the radio's longest normal spacing between frames in
    seconds, or None to take the largest spacing seen in wake 1 (at least
    ``MIN_GRANULARITY``). ``tier`` says how far the capture goes: to wake 2's
    first frame in the one-cycle tier, to wake 3's in the two-cycle tier;
    in the none tier the frames only feed the first transmission line and
    the median RSSI. ``wake`` is the block's TIME_TO_WAKE, which bounds where
    silence may end a wake while a serial port is followed; ``serial`` says a
    port is followed. ``listen_time`` is when the capture began hearing the
    fox's channel: the reset time for a scan that was already running, and
    otherwise filled in by ``listen`` when its loop starts. ``radio_time`` is
    when the banner arrived on serial, which the fox prints once its radio is
    up.
    """

    def __init__(self, reset_time: Optional[float], granularity: Optional[float], tier: str = TWO_CYCLES,
                 wake: Optional[int] = None, serial: bool = True,
                 boot_allowance: float = BOOT_ALLOWANCE, clock: Callable[[], float] = time.time,
                 listen_time: Optional[float] = None, radio_time: Optional[float] = None):
        self.reset_time = reset_time
        self._granularity = granularity
        self.tier = tier
        self.wake = wake
        self.serial = serial
        self.allowance = boot_allowance
        self.clock = clock
        self.listen_time = listen_time
        self.radio_time = radio_time
        self.frames: List[Heard] = []
        # When the serial port said a wake ended, or vanished, one instant
        # per sleep in order.
        self.sleep_times: List[float] = []
        # Per wake of a random-channel fox: the channel its serial printed and
        # when the sniffer was moved to it.
        self.retunes: Dict[int, Tuple[int, float]] = {}

    @property
    def measure(self) -> bool:
        """Whether the capture goes on past wake 1 to measure the cycle."""
        return self.tier != NONE

    @property
    def wakes_wanted(self) -> int:
        """The wake whose first frame completes the capture."""
        return WAKES[self.tier]

    def feed(self, frame: Heard) -> None:
        self.frames.append(frame)

    def mark_sleep(self, when: float) -> None:
        """The serial port reported the end of a wake at ``when``. The
        instants come in order and each counts once."""
        if not self.sleep_times or when > self.sleep_times[-1]:
            self.sleep_times.append(when)

    def _split(self) -> Tuple[List[List[Heard]], float]:
        """The frames of each wake in order and the granularity in use."""
        wakes: List[List[Heard]] = []
        granularity = self._granularity if self._granularity is not None else MIN_GRANULARITY
        for frame in self.frames:
            if not wakes:
                wakes.append([frame])
            elif self._opens_next_wake(wakes, frame, granularity):
                wakes.append([frame])
            else:
                if len(wakes) == 1 and self._granularity is None:
                    granularity = max(granularity, frame.time - wakes[0][-1].time)
                wakes[-1].append(frame)
        return wakes, granularity

    def _opens_next_wake(self, wakes: List[List[Heard]], frame: Heard, granularity: float) -> bool:
        """Whether ``frame`` is the first of the wake after the current one:
        past the instant the serial port gave for the current wake's end when
        it gave one, otherwise after a silence longer than the granularity
        plus the boot allowance, where silence counts."""
        current = wakes[-1]
        ended = len(wakes) - 1
        if ended < len(self.sleep_times):
            return frame.time > self.sleep_times[ended]
        if frame.time - current[-1].time <= granularity + self.allowance:
            return False
        return self._silence_counts(current[0], frame.time)

    def _silence_counts(self, first: Heard, when: float) -> bool:
        """Whether silence before ``when`` may end the wake that began with
        ``first``: anywhere without a serial port, only past the latest end
        of that wake with one."""
        if not self.serial:
            return True
        return self.wake is not None and when > first.time + self.wake + self.allowance

    def granularity(self) -> float:
        return self._split()[1]

    def frames_of(self, wake: int) -> List[Heard]:
        """The frames of wake ``wake``, counted from 1; empty when it was not
        heard."""
        wakes = self._split()[0]
        return wakes[wake - 1] if 0 < wake <= len(wakes) else []

    def wake1(self) -> List[Heard]:
        return self.frames_of(1)

    def wake2(self) -> List[Heard]:
        return self.frames_of(2)

    def wakes(self) -> int:
        """How many wakes have been heard."""
        return len(self._split()[0])

    def ended(self, now: Optional[float] = None, wake: int = 1) -> bool:
        """True once wake ``wake`` is known to be over: the serial port gave
        its end, a later wake was heard, or the fox has been quiet since its
        last frame for longer than the granularity plus the boot allowance
        where silence counts."""
        if len(self.sleep_times) >= wake:
            return True
        wakes, granularity = self._split()
        if len(wakes) > wake:
            return True
        if len(wakes) < wake:
            return False
        frames = wakes[wake - 1]
        now = self.clock() if now is None else now
        if now - frames[-1].time <= granularity + self.allowance:
            return False
        return self._silence_counts(frames[0], now)

    def complete(self) -> bool:
        """True once the first frame of the wake that completes the tier was
        heard: wake 2 in the one-cycle tier, wake 3 in the two-cycle tier;
        never in the none tier, which measures no cycle."""
        return self.measure and self.wakes() >= self.wakes_wanted

    def done(self) -> bool:
        """True when the capture may stop as far as the cycle is concerned."""
        return not self.measure or self.complete()

    def late(self) -> float:
        """Seconds between the reset and the start of the capture, during
        which the fox may have been on the air unheard; 0 for a scan that was
        already running."""
        if self.reset_time is None or self.listen_time is None:
            return 0.0
        return max(0.0, self.listen_time - self.reset_time)

    def first_transmission(self) -> Optional[float]:
        """Seconds from the reset to the first frame."""
        if self.reset_time is None or not self.frames:
            return None
        return self.frames[0].time - self.reset_time

    def heard_at_once(self) -> bool:
        """True when the first frame came within one frame spacing of the
        capture starting late, so the fox was probably already on the air and
        the first transmission figure is only an upper bound."""
        if not self.frames or self.late() == 0.0:
            return False
        return self.frames[0].time - self.listen_time <= self.granularity()

    def boot_bound(self) -> Optional[float]:
        """The most the first boot can have taken from the reset to the first
        frame: the first transmission figure, an upper bound when the capture
        began late, plus the late start itself."""
        seconds = self.first_transmission()
        return None if seconds is None else seconds + self.late()

    def span(self, wake: int = 1) -> Optional[float]:
        """Seconds from the first to the last frame of wake ``wake``."""
        frames = self.frames_of(wake)
        return frames[-1].time - frames[0].time if frames else None

    def gap(self, wake: int = 1) -> Optional[float]:
        """Seconds from the last frame of wake ``wake`` to the first of the
        next."""
        frames, following = self.frames_of(wake), self.frames_of(wake + 1)
        return following[0].time - frames[-1].time if frames and following else None

    def period(self, wake: int = 1) -> Optional[float]:
        """Seconds from the first frame of wake ``wake`` to the first of the
        next."""
        frames, following = self.frames_of(wake), self.frames_of(wake + 1)
        return following[0].time - frames[0].time if frames and following else None

    def first_cycle(self) -> Optional[float]:
        """Seconds from the reset to wake 2's first frame, the cycle the fox's
        first boot ran."""
        following = self.frames_of(2)
        if self.reset_time is None or not following:
            return None
        return following[0].time - self.reset_time

    def rssi_text(self) -> Optional[str]:
        """``median -42 dBm over 38 frames`` from every frame with an RSSI."""
        values = [frame.rssi for frame in self.frames if frame.rssi is not None]
        if not values:
            return None
        return "median %d dBm over %d frame%s" % (round(statistics.median(values)), len(values),
                                                  "" if len(values) == 1 else "s")


def listen(cycle: Optional[Cycle], deadline, read: Callable[[float], Sequence[Heard]],
           goal: Callable[[], bool], follower=None, retune: Optional[Callable[[int], None]] = None,
           debug: Callable[[str], None] = lambda text: None) -> None:
    """The capture loop. ``read(timeout)`` waits up to ``timeout`` seconds and
    returns the frames from the fox that arrived; ``goal()`` is true once the
    backend has what its own rows need. The loop ends when the goal is met
    and the cycle is done, or at the deadline. ``follower`` reads the fox's
    serial port between reads for the end of each wake and, when ``retune``
    is given, for the channel of each later wake, which the sniffer is moved
    to once per wake."""
    if cycle is not None and cycle.listen_time is None:
        cycle.listen_time = cycle.clock()
    while True:
        remaining = deadline.remaining()
        if remaining <= 0:
            break
        if goal() and (cycle is None or cycle.done()):
            break
        if follower is not None and cycle is not None:
            follower.poll()
            for boundary in follower.boundaries():
                cycle.mark_sleep(boundary)
            if retune is not None:
                for wake in range(2, cycle.wakes_wanted + 1):
                    channel = follower.channel(wake)
                    if channel is not None and wake not in cycle.retunes:
                        debug("wake %d is on channel %d, retuning" % (wake, channel))
                        retune(channel)
                        cycle.retunes[wake] = (channel, cycle.clock())
        for frame in read(min(remaining, POLL)):
            if cycle is not None:
                cycle.feed(frame)


def first_transmission_line(cycle: Cycle, no_reset: bool) -> str:
    """The line under the table: seconds from the reset to the first frame."""
    if no_reset:
        return "first transmission: not measured (--no-reset)"
    if cycle.reset_time is None:
        return "first transmission: not measured (the fox was not reset)"
    seconds = cycle.first_transmission()
    if seconds is None:
        return "first transmission: none heard before the deadline"
    if cycle.heard_at_once():
        # The fox was on the air when the capture began, so only an upper
        # bound was observed; the banner, printed once the radio is up, says
        # when the fox began transmitting.
        text = "first transmission: by %.1f s after reset (the sniffer started listening at %.1f s" % (
            seconds, cycle.late())
        radio = None if cycle.radio_time is None else cycle.radio_time - cycle.reset_time
        if radio is not None:
            text += "; the radio was up at %.1f s by serial" % radio
        text += ")"
        if cycle.measure and radio is not None and radio > cycle.allowance:
            text += ", over the %g s boot allowance" % cycle.allowance
        return text
    text = "first transmission: %.1f s after reset" % seconds
    if cycle.measure and seconds > cycle.allowance:
        text += ", over the %g s boot allowance" % cycle.allowance
    return text


def first_wake_line(cycle: Cycle) -> Optional[str]:
    """The line under the table of a two-cycle run, where wake 1 is not
    judged: how long the first boot was on the air, off the air, and its
    cycle from the reset to wake 2's first frame. None when the fox was not
    heard."""
    span = cycle.span(1)
    if span is None:
        return None
    text = "first wake: on the air %.1f s" % span
    gap, first_cycle = cycle.gap(1), cycle.first_cycle()
    if gap is not None:
        text += ", then off the air %.1f s" % gap
    if first_cycle is not None:
        text += ", cycle time %.1f s" % first_cycle
    return text


def _wake_missing(cycle: Cycle, wake: int, random_channel: bool) -> str:
    """The air text of a row whose wake ``wake`` was not heard."""
    if not cycle.ended(wake=wake - 1):
        return "wake %d had not ended at the deadline" % (wake - 1)
    retuned = cycle.retunes.get(wake)
    if random_channel and retuned is None:
        return "wake %d not heard: its channel was not seen on serial" % wake
    if retuned is not None:
        channel, when = retuned
        return "wake %d not heard on channel %d after retuning at +%.1f s" % (wake, channel, _since_reset(cycle, when))
    return "wake %d not heard before the deadline" % wake


def _since_reset(cycle: Cycle, when: float) -> float:
    return when - cycle.reset_time if cycle.reset_time is not None else when


def _retuned(cycle: Cycle, wake: int) -> str:
    """The retune suffix of a FAIL text whose measurement ends at wake
    ``wake``'s first frame."""
    retuned = cycle.retunes.get(wake)
    if retuned is None:
        return ""
    return ", retuned at +%.1f s" % _since_reset(cycle, retuned[1])


def _period_bounds(wake: int, sleep: int, allowance: float) -> Tuple[float, float, float]:
    """The cycle a wake-to-wake period is judged against, the longest it may
    run, and the tolerance. A fox whose TIME_TO_SLEEP is shorter than its
    boot cannot shorten the sleep enough and reboots at once, so its cycle
    runs long by that boot, allowed up to the boot allowance."""
    target = wake + sleep
    tolerance = max(PERIOD_TOLERANCE, PERIOD_TOLERANCE_RATIO * target)
    return target, wake + max(sleep, allowance), tolerance


def rows(report: Report, block: Block, readback: Readback, cycle: Cycle,
         random_channel: bool = False, last_cycle: Optional[float] = None) -> None:
    """The TIME_TO_WAKE, TIME_TO_SLEEP and CYCLE_TIME rows of a run that
    measured the cycle, judged with the two-cycle rules or the first-boot
    rules by the cycle's tier. ``last_cycle`` is the fox's own figure from
    the ``Last cycle`` line of the wake that ends the judged cycle, shown in
    the serial column of CYCLE_TIME when it was read."""
    if cycle.tier == TWO_CYCLES:
        _exact_rows(report, block, readback, cycle, random_channel, last_cycle)
    else:
        _first_boot_rows(report, block, readback, cycle, random_channel, last_cycle)


def _exact_rows(report: Report, block: Block, readback: Readback, cycle: Cycle,
                random_channel: bool, last_cycle: Optional[float]) -> None:
    """The rows of the two-cycle tier, from wake 2 and wake 3. TIME_TO_WAKE
    passes when wake 2's span is within ``TIME_TO_WAKE - g`` and
    ``TIME_TO_WAKE + BOOT_ALLOWANCE``, ``g`` the frame granularity.
    TIME_TO_SLEEP passes when the gap from wake 2's last frame to wake 3's
    first is at most ``TIME_TO_SLEEP + BOOT_ALLOWANCE + g`` and, for a fox
    that sleeps longer than ``g + BOOT_ALLOWANCE``, at least
    ``TIME_TO_SLEEP - BOOT_ALLOWANCE - g``: a sleeping fox must be off the
    air. CYCLE_TIME passes when the period from wake 2's first frame to
    wake 3's is ``TIME_TO_WAKE + TIME_TO_SLEEP`` within the larger of 1 s
    and one percent, or up to ``TIME_TO_WAKE + BOOT_ALLOWANCE`` for a fox
    whose TIME_TO_SLEEP is under the allowance. A wake 2 or wake 3 that was
    not heard FAILs the rows that needed it, with the text saying why."""
    wake, sleep = block.integer("TIME_TO_WAKE"), block.integer("TIME_TO_SLEEP")
    serial_wake, serial_sleep = readback.integer("time_to_wake"), readback.integer("time_to_sleep")
    granularity, allowance = cycle.granularity(), cycle.allowance
    heard = cycle.wakes()
    span, gap, period = cycle.span(2), cycle.gap(2), cycle.period(2)
    target, longest, tolerance = _period_bounds(wake, sleep, allowance)

    if serial_wake != wake:
        report.check("TIME_TO_WAKE", wake, serial_wake, on_air=False)
    elif heard == 0:
        report.add("TIME_TO_WAKE", wake, serial_wake, None, UNVERIFIED, "no frame from the fox")
    elif heard == 1:
        report.add("TIME_TO_WAKE", wake, serial_wake, _wake_missing(cycle, 2, random_channel), FAIL)
    elif heard >= 3 or cycle.ended(wake=2):
        verdict = PASS if wake - granularity <= span <= wake + allowance else FAIL
        report.add("TIME_TO_WAKE", wake, serial_wake, "on the air %.1f s" % span, verdict)
    elif span > wake + allowance:
        report.add("TIME_TO_WAKE", wake, serial_wake, "on the air %.1f s" % span, FAIL)
    else:
        report.add("TIME_TO_WAKE", wake, serial_wake, None, UNVERIFIED, "wake 2 not over before the deadline")

    if serial_sleep != sleep:
        report.check("TIME_TO_SLEEP", sleep, serial_sleep, on_air=False)
    elif heard == 0:
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, None, UNVERIFIED, "no frame from the fox")
    elif gap is None:
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, _wake_missing(cycle, heard + 1, random_channel), FAIL)
    else:
        passed = gap <= sleep + allowance + granularity
        if sleep > granularity + allowance:
            passed = passed and gap >= sleep - allowance - granularity
        air = "off the air %.1f s" % gap
        if not passed:
            air += _retuned(cycle, 3)
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, air, PASS if passed else FAIL)

    if heard == 0:
        report.add("CYCLE_TIME", target, last_cycle, None, UNVERIFIED, "no frame from the fox")
    elif period is None:
        report.add("CYCLE_TIME", target, last_cycle, _wake_missing(cycle, heard + 1, random_channel), FAIL)
    else:
        passed = target - tolerance <= period <= longest + tolerance
        air = "%.1f s" % period
        if not passed:
            air += _retuned(cycle, 3)
        report.add("CYCLE_TIME", target, last_cycle, air, PASS if passed else FAIL)


def _first_boot_rows(report: Report, block: Block, readback: Readback, cycle: Cycle,
                     random_channel: bool, last_cycle: Optional[float]) -> None:
    """The rows of the one-cycle tier, from wake 1 and the gap to wake 2,
    judged against what a first boot can deliver. Let ``d`` be the most the
    boot can have taken from the reset to the first frame (``boot_bound``),
    ``g`` the granularity and ``B`` the allowance. The fox's wake timer
    starts once its boot, start-up and readback are done, and the capture
    may have begun later still, so TIME_TO_WAKE passes when wake 1's span is
    within ``TIME_TO_WAKE - d - g`` and ``TIME_TO_WAKE + B``. TIME_TO_SLEEP
    passes when the gap is at most ``TIME_TO_SLEEP + B + g`` and, for a fox
    that sleeps longer than ``d + B + g``, at least
    ``TIME_TO_SLEEP - d - B - g``, since the firmware shortens the first
    sleep by the boot. CYCLE_TIME is the reset to wake 2's first frame: the
    firmware's cycle is exactly ``TIME_TO_WAKE + TIME_TO_SLEEP`` when the
    sleep absorbed the boot and ``TIME_TO_WAKE + d`` when it could not, and
    wake 2's own boot comes on top before its first frame, so the row passes
    within ``TIME_TO_WAKE + TIME_TO_SLEEP`` minus the period tolerance and
    the larger of the two plus ``B`` plus that tolerance. A wake 2 that was
    not heard FAILs TIME_TO_SLEEP and CYCLE_TIME with the text saying why."""
    wake, sleep = block.integer("TIME_TO_WAKE"), block.integer("TIME_TO_SLEEP")
    serial_wake, serial_sleep = readback.integer("time_to_wake"), readback.integer("time_to_sleep")
    granularity, allowance = cycle.granularity(), cycle.allowance
    span, gap, first_cycle = cycle.span(1), cycle.gap(1), cycle.first_cycle()
    boot = cycle.boot_bound() or 0.0
    target, _, tolerance = _period_bounds(wake, sleep, allowance)

    if serial_wake != wake:
        report.check("TIME_TO_WAKE", wake, serial_wake, on_air=False)
    elif span is None:
        report.add("TIME_TO_WAKE", wake, serial_wake, None, UNVERIFIED, "no frame from the fox")
    elif cycle.ended(wake=1):
        verdict = PASS if wake - boot - granularity <= span <= wake + allowance else FAIL
        report.add("TIME_TO_WAKE", wake, serial_wake, FIRST_BOOT + "on the air %.1f s" % span, verdict)
    elif span > wake + allowance:
        report.add("TIME_TO_WAKE", wake, serial_wake, FIRST_BOOT + "on the air %.1f s" % span, FAIL)
    else:
        report.add("TIME_TO_WAKE", wake, serial_wake, None, UNVERIFIED, "wake 1 not over before the deadline")

    if serial_sleep != sleep:
        report.check("TIME_TO_SLEEP", sleep, serial_sleep, on_air=False)
    elif span is None:
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, None, UNVERIFIED, "no frame from the fox")
    elif gap is None:
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, _wake_missing(cycle, 2, random_channel), FAIL)
    else:
        passed = gap <= sleep + allowance + granularity
        if sleep > boot + allowance + granularity:
            passed = passed and gap >= sleep - boot - allowance - granularity
        air = FIRST_BOOT + "off the air %.1f s" % gap
        if not passed:
            air += _retuned(cycle, 2)
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, air, PASS if passed else FAIL)

    if span is None:
        report.add("CYCLE_TIME", target, last_cycle, None, UNVERIFIED, "no frame from the fox")
    elif first_cycle is None:
        report.add("CYCLE_TIME", target, last_cycle, _wake_missing(cycle, 2, random_channel), FAIL)
    else:
        passed = target - tolerance <= first_cycle <= max(target, wake + boot) + allowance + tolerance
        air = FIRST_BOOT + "%.1f s" % first_cycle
        if not passed:
            air += _retuned(cycle, 2)
        report.add("CYCLE_TIME", target, last_cycle, air, PASS if passed else FAIL)
