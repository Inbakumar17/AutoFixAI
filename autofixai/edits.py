"""Position-preserving text edits.

Why this module exists
----------------------
The first version of AutoFixAI repaired code with ``str.replace``.  That is
dangerous: it rewrites *every* occurrence of a substring, including ones inside
strings, comments and unrelated identifiers.

Here every change is expressed as a :class:`~autofixai.models.TextEdit` that
targets an exact source range taken from the AST.  Only that range changes, so
formatting and comments everywhere else are preserved byte-for-byte.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import Fix, TextEdit

# Same line-splitting rules as Python's tokenizer (\n, \r\n, \r only).
_LINE_RE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+")


class OverlapError(ValueError):
    """Raised when two edits touch overlapping source ranges."""


class SourceMap:
    """Converts (line, utf8-byte-column) positions into string offsets."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.lines: list[str] = _LINE_RE.findall(source)
        self.starts: list[int] = []
        pos = 0
        for text in self.lines:
            self.starts.append(pos)
            pos += len(text)
        self.length = len(source)

    def offset(self, line: int, col: int) -> int:
        if line < 1:
            return 0
        if line > len(self.lines):
            return self.length
        text = self.lines[line - 1]
        prefix = text.encode("utf-8")[:col].decode("utf-8", errors="ignore")
        return self.starts[line - 1] + len(prefix)

    def span(self, edit: TextEdit) -> tuple[int, int]:
        return (
            self.offset(edit.start_line, edit.start_col),
            self.offset(edit.end_line, edit.end_col),
        )


def apply_edits(source: str, edits: Iterable[TextEdit]) -> str:
    """Apply non-overlapping edits to ``source`` and return the new text."""
    sm = SourceMap(source)
    spans = sorted(((*sm.span(e), e.text) for e in edits), key=lambda t: (t[0], t[1]))
    last_end = -1
    for start, end, _ in spans:
        if start < last_end:
            raise OverlapError("edits overlap")
        last_end = max(last_end, end)
    out: list[str] = []
    pos = 0
    for start, end, text in spans:
        out.append(source[pos:start])
        out.append(text)
        pos = end
    out.append(source[pos:])
    return "".join(out)


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def select_non_overlapping(source: str, fixes: list[Fix]) -> tuple[list[Fix], list[Fix]]:
    """Greedily choose fixes whose edits do not collide (earlier fixes win).

    Deferred fixes are not lost: the engine re-analyses after each round, so a
    deferred fix is simply re-proposed against the updated code.
    """
    sm = SourceMap(source)
    taken: list[tuple[int, int]] = []
    accepted: list[Fix] = []
    deferred: list[Fix] = []
    for fix in fixes:
        spans = [sm.span(e) for e in fix.edits]
        if any(_overlap(a, b) for a in spans for b in taken):
            deferred.append(fix)
            continue
        accepted.append(fix)
        taken.extend(spans)
    return accepted, deferred
