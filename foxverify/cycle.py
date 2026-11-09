"""The fox's wake and sleep cycle measured on the air: the boot allowance, the
frame log, the end of wake 1, the two timer rows, the first transmission line
and the median RSSI.

The firmware keeps one cycle, first wake-up to the next, at exactly
``TIME_TO_WAKE + TIME_TO_SLEEP`` seconds: the radio goes on right after boot,
stays on for ``TIME_TO_WAKE`` seconds, and the sleep is shortened by the boot
and start-up time of that cycle. On the air the fox is therefore heard for
about ``TIME_TO_WAKE`` seconds, silent for about ``TIME_TO_SLEEP`` seconds, and
the first frame of one wake to the first frame of the next is
``TIME_TO_WAKE + TIME_TO_SLEEP``.

``Cycle`` records every frame attributed to the fox as ``Heard(time, rssi)``
on the wall clock (``time.time()``, the clock the pcap timestamps and the
scanners already use), finds the end of wake 1, and derives the three numbers
the timer rows judge:

- the span ``t_last1 - t_first1``, the time on the air in wake 1;
- the gap ``t_first2 - t_last1``, the time off the air;
- the period ``t_first2 - t_first1``, one cycle.

Wake 1 ends with the serial port when it is being followed: the ``Going to
sleep`` line, or the port vanishing as a native USB board's does in deep
sleep. Both come after the radio stopped, so every frame after that instant
belongs to wake 2. Silence is the other signal: the fox quiet for longer than
the radio's frame granularity plus the boot allowance. While the serial port
is followed and has not spoken, silence only counts after the latest moment
wake 1 can end, ``t_first1 + TIME_TO_WAKE + BOOT_ALLOWANCE``, so that a pause
between inquiry responses is never taken for the sleep; without a serial port
it counts anywhere.

The Bluetooth scans start before the fox is reset, so they hear wake 1's
true first frame. The Wi-Fi and Zigbee captures start after the serial
readback, which names the channel, and so begin ``late`` seconds after the
reset; the fox may have been on the air that long before it was heard, so
the span and the period lower bounds are lowered by ``late``, and the first
transmission line says the figure is an upper bound when the fox was heard
as soon as the capture began.

``listen`` is the loop every backend runs: it reads frames, polls the serial
follower, retunes the sniffer when a random-channel fox reports wake 2's
channel, and stops when the backend has what it needs and the cycle is
complete or not being measured, or at the deadline.
"""
from __future__ import annotations

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


def needed(wake: int, sleep: int) -> float:
    """The --timeout that lets a run measure the cycle: one cycle plus the boot."""
    return wake + sleep + BOOT_ALLOWANCE


def fits(wake: int, sleep: int, timeout: float) -> bool:
    return timeout >= needed(wake, sleep)


def budget_note(wake: int, sleep: int, timeout: float) -> str:
    """The note of a run whose --timeout is too short to measure the cycle."""
    return ("TIME_TO_WAKE and TIME_TO_SLEEP: serial only, --timeout %g is under the %g s "
            "the cycle needs (TIME_TO_WAKE + TIME_TO_SLEEP + %g)"
            % (timeout, needed(wake, sleep), BOOT_ALLOWANCE))


class Cycle:
    """The frames heard from the fox and what they say about its cycle.

    ``reset_time`` is when the fox left reset, None when it was not reset
    (``--no-reset``, or a USB stack that has no reset).
    ``granularity`` is the radio's longest normal spacing between frames in
    seconds, or None to take the largest spacing seen in wake 1 (at least
    ``MIN_GRANULARITY``). ``measure`` says whether the capture goes on through
    the first sleep to wake 2; without it the frames only feed the first
    transmission line and the median RSSI. ``wake`` is the block's
    TIME_TO_WAKE, which bounds where silence may end wake 1 while a serial
    port is followed; ``serial`` says a port is followed. ``listen_time`` is
    when the capture began hearing the fox's channel: the reset time for a
    scan that was already running, and otherwise filled in by ``listen`` when
    its loop starts. ``radio_time`` is when the banner arrived on serial,
    which the fox prints once its radio is up.
    """

    def __init__(self, reset_time: Optional[float], granularity: Optional[float], measure: bool,
                 wake: Optional[int] = None, serial: bool = True,
                 boot_allowance: float = BOOT_ALLOWANCE, clock: Callable[[], float] = time.time,
                 listen_time: Optional[float] = None, radio_time: Optional[float] = None):
        self.reset_time = reset_time
        self._granularity = granularity
        self.measure = measure
        self.wake = wake
        self.serial = serial
        self.allowance = boot_allowance
        self.clock = clock
        self.listen_time = listen_time
        self.radio_time = radio_time
        self.frames: List[Heard] = []
        # When the serial port said the fox went to sleep, or vanished.
        self.sleep_time: Optional[float] = None
        # Wake 2's channel as read from the serial port and when the sniffer
        # was told, for a random-channel fox.
        self.retuned: Optional[Tuple[int, float]] = None

    def feed(self, frame: Heard) -> None:
        self.frames.append(frame)

    def mark_sleep(self, when: float) -> None:
        """The serial port reported the end of wake 1 at ``when``."""
        if self.sleep_time is None:
            self.sleep_time = when

    def _split(self) -> Tuple[List[Heard], List[Heard], float]:
        """The frames of wake 1, those of wake 2 and the granularity in use."""
        wake1: List[Heard] = []
        wake2: List[Heard] = []
        granularity = self._granularity if self._granularity is not None else MIN_GRANULARITY
        for frame in self.frames:
            if wake2 or (wake1 and self._ends_wake1(wake1[0], wake1[-1], frame, granularity)):
                wake2.append(frame)
                continue
            if wake1 and self._granularity is None:
                granularity = max(granularity, frame.time - wake1[-1].time)
            wake1.append(frame)
        return wake1, wake2, granularity

    def _silence_counts(self, first: Heard, when: float) -> bool:
        """Whether silence before ``when`` may end wake 1: anywhere without a
        serial port, only past the latest end of wake 1 with one."""
        if not self.serial:
            return True
        return self.wake is not None and when > first.time + self.wake + self.allowance

    def _ends_wake1(self, first: Heard, last: Heard, frame: Heard, granularity: float) -> bool:
        if self.sleep_time is not None:
            return frame.time > self.sleep_time
        if frame.time - last.time <= granularity + self.allowance:
            return False
        return self._silence_counts(first, frame.time)

    def granularity(self) -> float:
        return self._split()[2]

    def wake1(self) -> List[Heard]:
        return self._split()[0]

    def wake2(self) -> List[Heard]:
        return self._split()[1]

    def ended(self, now: Optional[float] = None) -> bool:
        """True once wake 1 is known to be over."""
        if self.sleep_time is not None:
            return True
        wake1, wake2, granularity = self._split()
        if wake2:
            return True
        if not wake1:
            return False
        now = self.clock() if now is None else now
        if now - wake1[-1].time <= granularity + self.allowance:
            return False
        return self._silence_counts(wake1[0], now)

    def complete(self) -> bool:
        """True once the first frame of wake 2 was heard."""
        return bool(self.wake2())

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

    def span(self) -> Optional[float]:
        wake1 = self.wake1()
        return wake1[-1].time - wake1[0].time if wake1 else None

    def gap(self) -> Optional[float]:
        wake1, wake2, _ = self._split()
        return wake2[0].time - wake1[-1].time if wake2 else None

    def period(self) -> Optional[float]:
        wake1, wake2, _ = self._split()
        return wake2[0].time - wake1[0].time if wake2 else None

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
    serial port between reads for the end of wake 1 and, when ``retune`` is
    given, for wake 2's channel, which the sniffer is moved to once."""
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
            boundary = follower.boundary()
            if boundary is not None:
                cycle.mark_sleep(boundary)
            channel = follower.channel()
            if retune is not None and channel is not None and cycle.retuned is None:
                debug("wake 2 is on channel %d, retuning" % channel)
                retune(channel)
                cycle.retuned = (channel, cycle.clock())
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


def _wake2_missing(cycle: Cycle, random_channel: bool) -> str:
    """The air text of a TIME_TO_SLEEP row whose wake 2 was not heard."""
    if not cycle.ended():
        return "wake 1 had not ended at the deadline"
    if random_channel and cycle.retuned is None:
        return "wake 2 not heard: its channel was not seen on serial"
    if cycle.retuned is not None:
        channel, when = cycle.retuned
        return "wake 2 not heard on channel %d after retuning at +%.1f s" % (channel, _since_reset(cycle, when))
    return "wake 2 not heard before the deadline"


def _since_reset(cycle: Cycle, when: float) -> float:
    return when - cycle.reset_time if cycle.reset_time is not None else when


def rows(report: Report, block: Block, readback: Readback, cycle: Cycle,
         random_channel: bool = False) -> None:
    """The TIME_TO_WAKE and TIME_TO_SLEEP rows of a run that measured the
    cycle. TIME_TO_WAKE passes when the span is within ``TIME_TO_WAKE - g``
    and ``TIME_TO_WAKE + BOOT_ALLOWANCE``, ``g`` the frame granularity.
    TIME_TO_SLEEP passes when the period is ``TIME_TO_WAKE + TIME_TO_SLEEP``
    within the larger of 1 s and one percent, and the gap is at most
    ``TIME_TO_SLEEP + BOOT_ALLOWANCE + g``. A fox whose TIME_TO_SLEEP is
    shorter than its boot reboots as soon as its wake is over, so its cycle
    runs long by that boot; when TIME_TO_SLEEP is under the allowance the
    period may therefore reach ``TIME_TO_WAKE + BOOT_ALLOWANCE``, and a
    TIME_TO_SLEEP 0 fox passes when its reboot takes less than the allowance.
    A capture that began ``late`` seconds after the reset may have missed
    that much of wake 1, so the span and the period may be short by it. A
    wake 2 that was not heard FAILs TIME_TO_SLEEP with the text saying
    why."""
    wake, sleep = block.integer("TIME_TO_WAKE"), block.integer("TIME_TO_SLEEP")
    serial_wake, serial_sleep = readback.integer("time_to_wake"), readback.integer("time_to_sleep")
    granularity, allowance, late = cycle.granularity(), cycle.allowance, cycle.late()
    span, gap, period = cycle.span(), cycle.gap(), cycle.period()

    if serial_wake != wake:
        report.check("TIME_TO_WAKE", wake, serial_wake, on_air=False)
    elif span is None:
        report.add("TIME_TO_WAKE", wake, serial_wake, None, UNVERIFIED, "no frame from the fox")
    elif cycle.ended():
        verdict = PASS if wake - granularity - late <= span <= wake + allowance else FAIL
        report.add("TIME_TO_WAKE", wake, serial_wake, "on the air %.1f s" % span, verdict)
    elif span > wake + allowance:
        report.add("TIME_TO_WAKE", wake, serial_wake, "on the air %.1f s" % span, FAIL)
    else:
        report.add("TIME_TO_WAKE", wake, serial_wake, None, UNVERIFIED, "wake 1 not over before the deadline")

    if serial_sleep != sleep:
        report.check("TIME_TO_SLEEP", sleep, serial_sleep, on_air=False)
    elif span is None:
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, None, UNVERIFIED, "no frame from the fox")
    elif period is None:
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, _wake2_missing(cycle, random_channel), FAIL)
    else:
        target = wake + sleep
        tolerance = max(PERIOD_TOLERANCE, PERIOD_TOLERANCE_RATIO * target)
        # A fox whose TIME_TO_SLEEP is shorter than its boot cannot shorten
        # the sleep enough and reboots at once, so its cycle is TIME_TO_WAKE
        # plus that boot, allowed up to the boot allowance.
        longest = wake + max(sleep, allowance)
        passed = (target - tolerance - late <= period <= longest + tolerance
                  and gap <= sleep + allowance + granularity)
        air = "off the air %.1f s" % gap
        if not passed:
            air += ", cycle %.1f s" % period
            if cycle.retuned is not None:
                air += ", retuned at +%.1f s" % _since_reset(cycle, cycle.retuned[1])
        report.add("TIME_TO_SLEEP", sleep, serial_sleep, air, PASS if passed else FAIL)
