"""Stand-ins for tshark, the clock and commands, shared by the on-air tests."""
from foxverify import tshark
from foxverify.report import Deadline
from foxverify.serial_fox import FakeClock


class FakeReader:
    """A ``FieldReader`` fed from a list of lines, each optionally preceded by
    the seconds that pass before it arrives. ``read`` moves ``clock`` instead
    of waiting."""

    def __init__(self, fields, items, clock, argv=("tshark",)):
        self.fields = list(fields)
        self.argv = list(argv)
        self.items = []
        for item in items:
            if isinstance(item, tuple):
                self.items.append((float(item[0]), item[1]))
            else:
                self.items.append((0.0, item))
        self.clock = clock
        self.eof = False
        self.stopped = False
        self.exit_text = "tshark exited with status 2: fake"

    def start(self):
        return self

    def read(self, timeout):
        if self.eof:
            return None
        if not self.items:
            self.clock.advance(timeout)
            return None
        delay, line = self.items[0]
        if delay > timeout:
            self.items[0] = (delay - timeout, line)
            self.clock.advance(timeout)
            return None
        self.items.pop(0)
        self.clock.advance(delay)
        if line is None:
            self.eof = True
            return None
        return self._parse(line)

    def _parse(self, line):
        return tshark.parse_line(line, self.fields)

    def exited(self):
        return self.eof

    def wait(self, timeout):
        return 2 if self.eof else None

    def error(self):
        return self.exit_text

    def stop(self):
        self.stopped = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


class FakeLineReader(FakeReader):
    def __init__(self, items, clock):
        FakeReader.__init__(self, ("line",), items, clock, ("btmgmt",))

    def _parse(self, line):
        return line.rstrip("\r\n")


class Recorder:
    """A ``run`` callable that records argv lists and answers from a table."""

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def __init__(self, answers=None, fail=None):
        self.calls = []
        self.answers = answers or {}
        self.fail = fail or {}

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        key = " ".join(argv)
        for prefix, result in self.fail.items():
            if key.startswith(prefix):
                return result
        for prefix, stdout in self.answers.items():
            if key.startswith(prefix):
                return self.Result(0, stdout)
        return self.Result(0, "")


def deadline(seconds=60.0, start=1000.0):
    clock = FakeClock(start)
    return Deadline(seconds, clock), clock
