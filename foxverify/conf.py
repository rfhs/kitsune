"""Parser for a conference header and selection of the block a fox was built from.

A conference header is C preprocessor text: one block of ``#define`` lines per
difficulty, selected by ``#if defined(EASY)`` ... ``#elif defined(HARD)`` or by
nested ``#if defined(AP)`` / ``#if defined(EASY)`` for Wi-Fi and
``#if defined(COORDINATOR)`` / ``#if defined(EASY)`` for Zigbee. Comments hold
``RFHS_CHALLENGE_NAME`` and ``FOX_KEYWORDS`` lines for the report and tables
of ``WIFI_POWER_*`` names, none of which is a define, so comments are removed
before anything is parsed.

``select(text, defined)`` evaluates the conditionals for a set of macro names
and returns the ``Block`` of defines in force, the way the compiler saw them for
that build. ``blocks(text)`` returns every block keyed by the macros that
select it, for the JSON dump and the tests.

Values are kept as the text written in the header. ``Block`` converts on
request: C strings, decimal and hex integers, byte arrays such as a MAC and
bare identifiers such as ``WIFI_POWER_17dBm``. A value written as another
macro's name (``EXT_PAN_ID MAC_ADDR``) resolves to that macro's value.

A bare ``0`` means random for ``CHANNEL`` and ``PAN_ID``. ``0x0000`` is a real
PAN ID: the firmware tells them apart by the text of the macro, and so does
``Block.is_bare_zero``. For ``CHANNEL`` the firmware compares the number, so
``Block.integer("CHANNEL") == 0`` is the random test there.

``python3 -m foxverify.conf <header> [MACRO ...]`` dumps the blocks as JSON,
or the one block selected when macro names are given.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Dict, Iterable, List, Optional, Tuple

DIFFICULTIES = ("EASY", "MEDIUM", "HARD", "FIVEEASY", "FIVEHARD")
MODES = ("AP", "CLIENT")

# Macros a project's build always defines besides the difficulty and the mode.
PROJECT_MACROS = {
    "classic_discoverable": (),
    "iBeacon": (),
    "wifi_ap_client": (),
    "zigbee_coordinator": ("COORDINATOR",),
}


class ConfError(Exception):
    """The header cannot be parsed or a value is not what the caller asked for."""


def defined_for(project: str, difficulty: str, mode: Optional[str] = None) -> frozenset:
    """The macro names a build of ``project`` defines for a banner's tokens."""
    names = {difficulty}
    if mode:
        names.add(mode)
    names.update(PROJECT_MACROS.get(project, ()))
    return frozenset(names)


def strip_comments(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments, leaving string literals and line
    numbers intact. A block comment keeps its newlines so the line structure
    the preprocessor cares about does not move."""
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"' or c == "'":
            quote = c
            j = i + 1
            while j < n and text[j] != quote:
                if text[j] == "\\":
                    j += 1
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            if j < 0:
                j = n
            out.append(" ")
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise ConfError("unterminated /* comment")
            out.append(" ")
            out.append("\n" * text.count("\n", i, j))
            i = j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


_DIRECTIVE = re.compile(r"^\s*#\s*([a-z]+)\b\s*(.*?)\s*$")
_DEFINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\s+(.*))?$")
_DEFINED = re.compile(r"defined\s*(?:\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)|([A-Za-z_][A-Za-z0-9_]*))")


class _Frame:
    """One open ``#if``: the condition of the branch in force and the conditions
    of the branches before it, which all evaluated false when this one runs."""

    def __init__(self, condition: Optional[str]):
        self.condition = condition
        self.earlier: List[str] = []
        self.closed = False

    def key(self) -> str:
        if self.condition is None:
            return "!(" + " || ".join(self.earlier) + ")"
        names = _DEFINED.findall(self.condition)
        simple = re.sub(r"\s+", "", self.condition)
        if len(names) == 1 and simple in ("defined(%s)" % (names[0][0] or names[0][1]),
                                          "defined%s" % (names[0][0] or names[0][1])):
            return names[0][0] or names[0][1]
        return self.condition


class _Region:
    """A run of defines under one stack of conditions."""

    def __init__(self, frames: List[_Frame]):
        self.frames = [(f.condition, list(f.earlier)) for f in frames]
        self.keys = tuple(f.key() for f in frames)
        self.defines: List[Tuple[str, Optional[str]]] = []

    def active(self, defined: frozenset) -> bool:
        for condition, earlier in self.frames:
            if any(_evaluate(e, defined) for e in earlier):
                return False
            if condition is not None and not _evaluate(condition, defined):
                return False
        return True


def _tokenize(expr: str) -> List[str]:
    tokens = re.findall(r"defined\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)|defined\s+[A-Za-z_][A-Za-z0-9_]*"
                        r"|&&|\|\||!|\(|\)|[A-Za-z_][A-Za-z0-9_]*|\S", expr)
    if "".join(tokens).replace(" ", "") != expr.replace(" ", ""):
        raise ConfError("cannot parse #if expression: %s" % expr)
    return tokens


def _evaluate(expr: str, defined: frozenset) -> bool:
    """Evaluate an ``#if`` expression made of ``defined(X)``, ``!``, ``&&``,
    ``||`` and parentheses. Anything else in a conference header is an error
    here, because nothing in the repo uses it."""
    tokens = _tokenize(expr)
    pos = [0]

    def peek() -> Optional[str]:
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def take() -> str:
        token = tokens[pos[0]]
        pos[0] += 1
        return token

    def primary() -> bool:
        token = peek()
        if token is None:
            raise ConfError("unexpected end of #if expression: %s" % expr)
        if token == "!":
            take()
            return not primary()
        if token == "(":
            take()
            value = disjunction()
            if peek() != ")":
                raise ConfError("missing ) in #if expression: %s" % expr)
            take()
            return value
        match = _DEFINED.fullmatch(token)
        if match:
            take()
            return (match.group(1) or match.group(2)) in defined
        raise ConfError("unsupported #if expression: %s" % expr)

    def conjunction() -> bool:
        value = primary()
        while peek() == "&&":
            take()
            value = primary() and value
        return value

    def disjunction() -> bool:
        value = conjunction()
        while peek() == "||":
            take()
            value = conjunction() or value
        return value

    result = disjunction()
    if peek() is not None:
        raise ConfError("trailing tokens in #if expression: %s" % expr)
    return result


def _regions(text: str) -> List[_Region]:
    stack: List[_Frame] = []
    regions: List[_Region] = []
    current: Optional[_Region] = None
    for number, line in enumerate(strip_comments(text).split("\n"), 1):
        match = _DIRECTIVE.match(line)
        if not match:
            continue
        directive, rest = match.group(1), match.group(2)
        if directive in ("if", "ifdef", "ifndef"):
            if directive == "ifdef":
                rest = "defined(%s)" % rest
            elif directive == "ifndef":
                rest = "!defined(%s)" % rest
            stack.append(_Frame(rest))
            current = None
        elif directive in ("elif", "else"):
            if not stack or stack[-1].closed:
                raise ConfError("line %d: #%s without #if" % (number, directive))
            frame = stack[-1]
            if frame.condition is None:
                raise ConfError("line %d: #%s after #else" % (number, directive))
            frame.earlier.append(frame.condition)
            frame.condition = rest if directive == "elif" else None
            current = None
        elif directive == "endif":
            if not stack:
                raise ConfError("line %d: #endif without #if" % number)
            stack.pop()
            current = None
        elif directive in ("define", "undef"):
            if current is None:
                current = _Region(stack)
                regions.append(current)
            if directive == "undef":
                current.defines.append((rest.strip(), None))
                continue
            define = _DEFINE.match(rest)
            if not define:
                raise ConfError("line %d: cannot parse #define %s" % (number, rest))
            current.defines.append((define.group(1), (define.group(2) or "").strip()))
    if stack:
        raise ConfError("unterminated #if")
    return regions


class Block:
    """The defines in force for one build, with typed access to their values."""

    def __init__(self, defines: Dict[str, str], defined: Iterable[str] = ()):
        self.defines = dict(defines)
        self.defined = frozenset(defined)

    def __contains__(self, name: str) -> bool:
        return name in self.defines

    def __len__(self) -> int:
        return len(self.defines)

    def names(self) -> List[str]:
        return list(self.defines)

    def raw(self, name: str) -> str:
        """The value text as written, with surrounding whitespace removed."""
        if name not in self.defines:
            raise ConfError("%s is not defined in this block" % name)
        return self.defines[name]

    def resolved(self, name: str, seen: Tuple[str, ...] = ()) -> str:
        """The value text after following names of other macros in the block."""
        text = self.raw(name)
        if _IDENTIFIER.fullmatch(text) and text in self.defines and text not in seen:
            return self.resolved(text, seen + (name,))
        return text

    def string(self, name: str) -> str:
        return parse_c_string(self.resolved(name), name)

    def integer(self, name: str) -> int:
        return parse_c_int(self.resolved(name), name)

    def byte_array(self, name: str) -> bytes:
        return parse_byte_array(self.resolved(name), name)

    def identifier(self, name: str) -> str:
        text = self.resolved(name)
        if not _IDENTIFIER.fullmatch(text):
            raise ConfError("%s is not a bare identifier: %s" % (name, text))
        return text

    def is_bare_zero(self, name: str) -> bool:
        """True when the value is written as exactly ``0``, the text the
        firmware reads as random for PAN_ID."""
        return self.raw(name) == "0"

    def mac(self, name: str) -> str:
        return format_bytes(self.byte_array(name))

    def display(self, name: str) -> str:
        """The value as the report's header column shows it: strings without
        quotes, byte arrays as colon separated hex, numbers in decimal,
        identifiers as written."""
        text = self.resolved(name)
        if text.startswith('"'):
            return parse_c_string(text, name)
        if text.startswith("{"):
            return format_bytes(parse_byte_array(text, name))
        if _IDENTIFIER.fullmatch(text):
            return text
        return str(parse_c_int(text, name))

    def as_dict(self) -> Dict[str, str]:
        return dict(self.defines)


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_INT = re.compile(r"^\(?\s*([+-]?)\s*(0[xX][0-9A-Fa-f]+|0[0-7]*|[1-9][0-9]*)\s*[uUlL]*\s*\)?$")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'", "?": "?",
            "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def parse_c_string(text: str, name: str = "value") -> str:
    """A C string literal, or several adjacent ones, as Python text."""
    text = text.strip()
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != '"':
            raise ConfError("%s is not a string literal: %s" % (name, text))
        i += 1
        while i < n and text[i] != '"':
            c = text[i]
            if c == "\\":
                i += 1
                if i >= n:
                    break
                e = text[i]
                if e == "x":
                    digits = re.match(r"[0-9A-Fa-f]{1,2}", text[i + 1:])
                    if not digits:
                        raise ConfError("%s has a bad \\x escape" % name)
                    out.append(chr(int(digits.group(0), 16)))
                    i += len(digits.group(0))
                elif e in "01234567":
                    digits = re.match(r"[0-7]{1,3}", text[i:])
                    out.append(chr(int(digits.group(0), 8)))
                    i += len(digits.group(0)) - 1
                elif e in _ESCAPES:
                    out.append(_ESCAPES[e])
                else:
                    raise ConfError("%s has an unknown escape \\%s" % (name, e))
            else:
                out.append(c)
            i += 1
        if i >= n:
            raise ConfError("%s has an unterminated string literal: %s" % (name, text))
        i += 1
        while i < n and text[i].isspace():
            i += 1
    return "".join(out)


def parse_c_int(text: str, name: str = "value") -> int:
    """A C integer literal: decimal, ``0x`` hex, leading-zero octal, an optional
    sign, an optional ``u``/``l`` suffix and optional parentheses."""
    match = _INT.match(text.strip())
    if not match:
        raise ConfError("%s is not an integer: %s" % (name, text))
    sign, digits = match.group(1), match.group(2)
    if digits[:2] in ("0x", "0X"):
        value = int(digits, 16)
    elif len(digits) > 1 and digits[0] == "0":
        value = int(digits, 8)
    else:
        value = int(digits, 10)
    return -value if sign == "-" else value


def parse_byte_array(text: str, name: str = "value") -> bytes:
    """A brace initializer of byte values, ``{0xF2, 0x81, ...}``."""
    text = text.strip()
    if not (text.startswith("{") and text.endswith("}")):
        raise ConfError("%s is not a byte array: %s" % (name, text))
    inner = text[1:-1].strip()
    if not inner:
        return b""
    values = []
    for item in inner.split(","):
        item = item.strip()
        if not item:
            continue
        value = parse_c_int(item, name)
        if not 0 <= value <= 255:
            raise ConfError("%s has a byte out of range: %s" % (name, item))
        values.append(value)
    return bytes(values)


def format_bytes(data: bytes) -> str:
    """Colon separated upper case hex, the form the firmware prints."""
    return ":".join("%02X" % b for b in data)


def format_u16(value: int) -> str:
    """A 16 bit identifier the way the firmware, the report and Kismet print it."""
    return "0x%04X" % (value & 0xFFFF)


def select(text: str, defined: Iterable[str]) -> Block:
    """The defines in force when ``defined`` names the macros of the build."""
    names = frozenset(defined)
    values: Dict[str, str] = {}
    for region in _regions(text):
        if not region.active(names):
            continue
        for name, value in region.defines:
            if value is None:
                values.pop(name, None)
            else:
                values[name] = value
    return Block(values, names)


def blocks(text: str) -> Dict[str, Dict[str, str]]:
    """Every block that contains defines, keyed by the macros that select it,
    outermost first and space separated: ``"AP EASY"`` for the Wi-Fi header,
    ``"HARD"`` for a Bluetooth one. Defines outside every ``#if`` are under
    the empty key."""
    result: Dict[str, Dict[str, str]] = {}
    for region in _regions(text):
        key = " ".join(region.keys)
        values = result.setdefault(key, {})
        for name, value in region.defines:
            if value is None:
                values.pop(name, None)
            else:
                values[name] = value
    return result


def load(path: str) -> str:
    """The header text; ``path`` is usually the ``current_conf.h`` symlink."""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        sys.stderr.write("usage: python3 -m foxverify.conf <header> [MACRO ...]\n")
        return 2
    text = load(args[0])
    if len(args) > 1:
        data = select(text, args[1:]).as_dict()
    else:
        data = blocks(text)
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
