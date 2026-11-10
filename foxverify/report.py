"""Result rows, the table, the one deadline of a run and the exit codes.

Every verify script prints a table with the columns value, header, serial, air
and verdict, then one summary line. The verdicts are:

- ``pass``: header, serial and air agree.
- ``FAIL``: any disagreement; all three values are in the row.
- ``serial only``: header and serial agree and the value is not confirmed on
  the air (the PSK text, MAX_CLIENTS, TXPOWER, EXT_PAN_ID, and the sleep
  timers when the run's budget does not cover one cycle); the verdict column
  may carry the reason, and the air column may carry what was heard without
  it deciding the verdict, such as the median RSSI under TXPOWER.
- ``unverified``: observable on air but not seen within the budget; the
  verdict column carries the reason.

A line added with ``line`` is printed between the table and the notes, which
is where the first wake figures go. A line given to ``suggest`` is
printed after the summary, which is where a run whose budget was too short
for the exact cycle time names the ``--timeout`` that measures it.

The exit code is 0 when nothing FAILed, 1 when any row FAILed and 2 when the
run could not happen at all (no fox, not a fox, a missing tool or privilege);
code paths raise ``RunError`` for the last case.

``Deadline`` is the one monotonic clock of a run. It starts at launch and every
blocking wait asks it for the remaining time instead of sleeping a fixed span.
"""
from __future__ import annotations

import sys
import time
from typing import Callable, List, NamedTuple, Optional, TextIO

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NO_RUN = 2

PASS = "pass"
FAIL = "FAIL"
SERIAL = "serial only"
UNVERIFIED = "unverified"

COLUMNS = ("value", "header", "serial", "air", "verdict")

# Shown in a column whose value does not exist, for example the air column of
# a value that is not observable on air.
EMPTY = "-"
# The reason of a FAIL row whose serial column is empty: the fox stopped
# before that readback line, or does not print it.
NOT_PRINTED = "not printed on serial"


class RunError(Exception):
    """The run could not happen. The message is printed and the script exits 2."""

    exit_code = EXIT_NO_RUN


class Deadline:
    """A point on the monotonic clock that every wait in the run measures against."""

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.seconds = float(seconds)
        self.started = clock()
        self.at = self.started + self.seconds

    def now(self) -> float:
        return self._clock()

    def elapsed(self) -> float:
        return self._clock() - self.started

    def remaining(self) -> float:
        return max(0.0, self.at - self._clock())

    def expired(self) -> bool:
        return self._clock() >= self.at

    def budget(self, want: float) -> float:
        """The shorter of ``want`` and the time left."""
        return min(float(want), self.remaining())


class Row(NamedTuple):
    value: str
    header: str
    serial: str
    air: str
    verdict: str
    reason: str

    def cells(self) -> List[str]:
        verdict = self.verdict
        if self.reason:
            verdict = "%s: %s" % (verdict, self.reason)
        return [self.value, self.header, self.serial, self.air, verdict]


def _text(value: Optional[object]) -> str:
    return EMPTY if value is None else str(value)


class Report:
    """The rows of one run, the notes printed under them and the exit code."""

    def __init__(self, deadline: Optional[Deadline] = None, out: TextIO = sys.stdout,
                 verbose: bool = False):
        self.deadline = deadline
        self.out = out
        self.verbose = verbose
        self.rows: List[Row] = []
        self.lines: List[str] = []
        self.notes: List[str] = []
        self.suggestion: Optional[str] = None

    def add(self, value: str, header: Optional[object], serial: Optional[object],
            air: Optional[object], verdict: str, reason: str = "") -> Row:
        """Append a row with a verdict the caller has already decided."""
        row = Row(value, _text(header), _text(serial), _text(air), verdict, reason)
        self.rows.append(row)
        return row

    def check(self, value: str, header: Optional[object], serial: Optional[object],
              air: Optional[object] = None, on_air: bool = True,
              agree: Optional[bool] = None, reason: str = "") -> Row:
        """Append a row and decide its verdict from the three values.

        ``header`` and ``serial`` are compared as text unless ``agree`` says
        whether they match, which is how a random CHANNEL or PAN ID accepts
        whatever the fox picked. ``air`` is compared against what the fox
        printed, or against the header when the fox printed nothing for this
        value. ``on_air=False`` marks a value the air does not decide and
        gives ``serial only`` instead of ``unverified``, with ``reason`` and
        ``air`` shown as given; ``air=None`` with ``on_air=True`` means the
        value was not seen and ``reason`` says why. A FAIL row carries no
        reason, its values speak, except that a header value the fox did not
        print says ``NOT_PRINTED``.
        """
        if agree is None:
            agree = header is not None and serial is not None and _text(header) == _text(serial)
        if not agree:
            missing = serial is None and header is not None
            return self.add(value, header, serial, air, FAIL, NOT_PRINTED if missing else "")
        if not on_air:
            return self.add(value, header, serial, air, SERIAL, reason)
        if air is None:
            return self.add(value, header, serial, None, UNVERIFIED, reason or "not seen")
        expected = serial if serial is not None else header
        if _text(air) != _text(expected):
            return self.add(value, header, serial, air, FAIL, "")
        return self.add(value, header, serial, air, PASS, "")

    def line(self, text: str) -> None:
        """A plain line printed between the table and the notes."""
        self.lines.append(text)

    def note(self, text: str) -> None:
        """A line printed between the table and the summary, marked ``note:``."""
        self.notes.append(text)

    def suggest(self, text: Optional[str]) -> None:
        """The one line printed after the summary; None prints nothing."""
        self.suggestion = text

    def say(self, text: str) -> None:
        """Progress the user always sees."""
        self.out.write(text + "\n")
        self.out.flush()

    def debug(self, text: str) -> None:
        """Progress shown only with -v."""
        if self.verbose:
            self.say(text)

    def count(self, verdict: str) -> int:
        return sum(1 for row in self.rows if row.verdict == verdict)

    def failed(self) -> bool:
        return self.count(FAIL) > 0

    def exit_code(self) -> int:
        return EXIT_FAIL if self.failed() else EXIT_OK

    def table(self) -> str:
        """The rows as aligned text, header line first."""
        cells = [list(COLUMNS)] + [row.cells() for row in self.rows]
        widths = [max(len(line[i]) for line in cells) for i in range(len(COLUMNS))]
        lines = []
        for line in cells:
            padded = [text.ljust(widths[i]) for i, text in enumerate(line)]
            lines.append(" | ".join(padded).rstrip())
        return "\n".join(lines)

    def summary(self) -> str:
        """One line: the overall verdict, the counts and the time used."""
        word = FAIL if self.failed() else PASS
        text = "%s: %d pass, %d FAIL, %d %s, %d unverified" % (
            word, self.count(PASS), self.count(FAIL), self.count(SERIAL), SERIAL, self.count(UNVERIFIED))
        if self.deadline is not None:
            text += ", %.1f s of %.0f s" % (self.deadline.elapsed(), self.deadline.seconds)
        return text

    def render(self) -> str:
        parts = [self.table()]
        parts.extend(self.lines)
        parts.extend("note: " + note for note in self.notes)
        parts.append(self.summary())
        if self.suggestion is not None:
            parts.append(self.suggestion)
        return "\n".join(parts) + "\n"

    def emit(self) -> int:
        """Print the table, the notes, the summary and the suggestion; return
        the exit code."""
        self.out.write(self.render())
        self.out.flush()
        return self.exit_code()
