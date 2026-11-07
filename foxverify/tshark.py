"""Reader for the ``tshark -l -T fields`` stream, live from an interface or from
a pcap file or FIFO.

tshark is started with one ``-e`` per field, tab separated, every occurrence of
a field joined with commas and name resolution off, so each line of output is
one frame whose cells line up with the requested field names. A thread moves
the lines into a queue; ``FieldReader.read`` waits on that queue for the time
the caller passes, which is always the remaining time of the run's deadline.
stderr is collected in a second thread and shown when tshark exits early,
because that is where "You don't have permission to capture" and "Interface
doesn't support monitor mode" arrive.

Field names used by the fox checks, as Wireshark registers them:

- Wi-Fi: ``wlan.fc.type_subtype`` (0x0008 beacon, 0x0004 probe request),
  ``wlan.bssid``, ``wlan.sa``, ``wlan.ssid``, ``wlan.ds.current_channel``,
  ``wlan.ht.info.primarychannel``, ``radiotap.channel.freq``,
  ``wlan.rsn.akms.type`` (2 = PSK), ``wlan.rsn.pcs.type`` (4 = CCMP).
- 802.15.4 and Zigbee: ``wpan-tap.ch_num``, ``wpan.src_pan``, ``wpan.dst_pan``,
  ``wpan.src16``, ``wpan.src64``, ``zbee_nwk.frame_type``, ``zbee_nwk.cmd.id``
  (0x08 = Link Status), ``zbee_nwk.src64``, ``zbee.sec.src64``.
- Both: ``frame.time_epoch``.
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
from typing import Callable, Dict, List, Optional, Sequence

from .report import RunError

SEPARATOR = "\t"
AGGREGATOR = ","
# How many lines of tshark's stderr are kept for the error message.
STDERR_LINES = 20

_HEX = re.compile(r"^(?:0x)?([0-9A-Fa-f]+)$")


def command(tshark: str, source: Sequence[str], fields: Sequence[str],
            display_filter: Optional[str] = None) -> List[str]:
    """The tshark argument list for ``source`` (``-i wlan1`` or ``-r fifo``)."""
    argv = [tshark] + list(source) + ["-l", "-n", "-T", "fields",
                                      "-E", "separator=/t",
                                      "-E", "occurrence=a",
                                      "-E", "aggregator=" + AGGREGATOR]
    for field in fields:
        argv += ["-e", field]
    if display_filter:
        argv += ["-Y", display_filter]
    return argv


def live_command(tshark: str, interface: str, fields: Sequence[str],
                 display_filter: Optional[str] = None) -> List[str]:
    return command(tshark, ["-i", interface], fields, display_filter)


def file_command(tshark: str, path: str, fields: Sequence[str],
                 display_filter: Optional[str] = None) -> List[str]:
    return command(tshark, ["-r", path], fields, display_filter)


def hex_int(text: Optional[str]) -> Optional[int]:
    """An integer from a field tshark prints in hex (``0x0008``, ``08``) or
    decimal; None for an empty or unparsable cell."""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    if text.lower().startswith("0x"):
        match = _HEX.match(text)
        return int(match.group(1), 16) if match else None
    try:
        return int(text, 10)
    except ValueError:
        match = _HEX.match(text)
        return int(match.group(1), 16) if match else None


def dec_int(text: Optional[str]) -> Optional[int]:
    """An integer from a decimal cell such as a channel number; None when empty."""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return int(text.split(AGGREGATOR, 1)[0], 10)
    except ValueError:
        return None


def mac_text(text: Optional[str]) -> Optional[str]:
    """A MAC or EUI-64 cell as upper case colon separated hex, the form the
    firmware prints; None when the cell is empty."""
    if text is None:
        return None
    text = text.strip().split(AGGREGATOR, 1)[0]
    if not text:
        return None
    return text.replace("-", ":").upper()


class Record:
    """The cells of one tshark output line keyed by field name."""

    def __init__(self, fields: Sequence[str], cells: Sequence[str], aggregator: str = AGGREGATOR):
        self.fields = list(fields)
        self._cells: Dict[str, str] = {}
        for index, field in enumerate(self.fields):
            self._cells[field] = cells[index] if index < len(cells) else ""
        self.aggregator = aggregator

    def get(self, field: str) -> Optional[str]:
        """The cell text, None when the field was absent from the frame."""
        text = self._cells.get(field, "")
        return text if text != "" else None

    def values(self, field: str) -> List[str]:
        """Every occurrence of the field in the frame."""
        text = self.get(field)
        return [] if text is None else text.split(self.aggregator)

    def first(self, field: str) -> Optional[str]:
        values = self.values(field)
        return values[0] if values else None

    def as_dict(self) -> Dict[str, str]:
        return dict(self._cells)

    def __repr__(self) -> str:
        return "Record(%r)" % (self._cells,)


def parse_line(line: str, fields: Sequence[str]) -> Record:
    return Record(fields, line.rstrip("\r\n").split(SEPARATOR))


class FieldReader:
    """A running tshark whose field lines are read with a timeout.

    ``read`` returns the next ``Record`` or None when ``timeout`` passed
    without one; ``eof`` becomes true once tshark closed its output, and
    ``error`` then says why it exited.
    """

    def __init__(self, argv: Sequence[str], fields: Sequence[str],
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen):
        self.argv = list(argv)
        self.fields = list(fields)
        self._popen = popen
        self.process: Optional[subprocess.Popen] = None
        self._lines: "queue.Queue[Optional[str]]" = queue.Queue()
        self._stderr: List[str] = []
        self._threads: List[threading.Thread] = []
        self.eof = False

    def start(self) -> "FieldReader":
        self.process = self._popen(self.argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        self._threads = [
            threading.Thread(target=self._pump_stdout, daemon=True),
            threading.Thread(target=self._pump_stderr, daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        return self

    def _pump_stdout(self) -> None:
        stream = self.process.stdout
        try:
            for raw in stream:
                self._lines.put(raw.decode("utf-8", "replace"))
        finally:
            self._lines.put(None)

    def _pump_stderr(self) -> None:
        for raw in self.process.stderr:
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            if text:
                self._stderr.append(text)
                del self._stderr[:-STDERR_LINES]

    def read(self, timeout: float) -> Optional[Record]:
        if self.eof:
            return None
        try:
            line = self._lines.get(timeout=max(0.0, timeout))
        except queue.Empty:
            return None
        if line is None:
            self.eof = True
            return None
        return self._parse(line)

    def _parse(self, line: str):
        return parse_line(line, self.fields)

    def exited(self) -> bool:
        return self.process is not None and self.process.poll() is not None

    def wait(self, timeout: float) -> Optional[int]:
        """The exit status once the program ended, with its stderr fully
        collected; None when it is still running after ``timeout`` seconds."""
        try:
            code = self.process.wait(max(0.0, timeout))
        except subprocess.TimeoutExpired:
            return None
        for thread in self._threads:
            thread.join(1.0)
        return code

    def error(self) -> str:
        """Why the program stopped: its exit status and the last stderr lines."""
        name = os.path.basename(self.argv[0])
        code = self.process.poll() if self.process is not None else None
        text = "%s exited" % name if code is None else "%s exited with status %d" % (name, code)
        if self._stderr:
            text += ": " + " / ".join(self._stderr)
        return text

    def stop(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for thread in self._threads:
            thread.join(2.0)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()

    def __enter__(self) -> "FieldReader":
        if self.process is None:
            self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


class LineReader(FieldReader):
    """The same reader for a program whose output is plain lines, such as
    ``btmgmt``: ``read`` returns each line as text without its newline."""

    def __init__(self, argv: Sequence[str], popen: Callable[..., subprocess.Popen] = subprocess.Popen):
        FieldReader.__init__(self, argv, ("line",), popen)

    def _parse(self, line: str) -> str:
        return line.rstrip("\r\n")


def read_until(reader: FieldReader, deadline, accept: Callable[[Record], bool],
               debug: Callable[[str], None] = lambda text: None) -> Optional[Record]:
    """The first record ``accept`` likes before the deadline; None when the
    deadline passes first. tshark exiting early is a ``RunError``."""
    while True:
        remaining = deadline.remaining()
        if remaining <= 0:
            return None
        record = reader.read(remaining)
        if record is None:
            if reader.eof:
                raise RunError(reader.error())
            continue
        debug("tshark: " + "\t".join(record.as_dict().values()))
        if accept(record):
            return record
