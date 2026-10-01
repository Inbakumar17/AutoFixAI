"""Fixer interface and the shared analysis context handed to every fixer."""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..astutils import parent_map
from ..edits import SourceMap
from ..models import ExecutionResult, Fix, Issue, TextEdit


@dataclass
class Context:
    """Everything a fixer may look at (built once per repair round)."""

    source: str
    tree: ast.Module
    issues: list[Issue]
    run: Optional[ExecutionResult]
    parents: dict
    sm: SourceMap

    @classmethod
    def build(cls, source: str, issues: list[Issue], run: Optional[ExecutionResult]) -> Optional[Context]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        return cls(source, tree, issues, run, parent_map(tree), SourceMap(source))

    # -- text helpers -----------------------------------------------------
    def line_text(self, number: int) -> str:
        return self.sm.lines[number - 1] if 1 <= number <= len(self.sm.lines) else ""

    def text(self, node: ast.AST) -> Optional[str]:
        return ast.get_source_segment(self.source, node)

    def indent_of(self, number: int) -> str:
        line = self.line_text(number)
        return line[: len(line) - len(line.lstrip(" \t"))]

    @staticmethod
    def indent_unit(indent: str) -> str:
        return "\t" if "\t" in indent else "    "

    def starts_line(self, node: ast.AST) -> bool:
        """True if only whitespace precedes ``node`` on its first line."""
        prefix = self.line_text(node.lineno).encode("utf-8")[: node.col_offset].decode("utf-8", "ignore")
        return prefix.strip() == ""

    def owns_lines(self, node: ast.AST) -> bool:
        """True if ``node`` is alone on its line(s) (a trailing comment is fine)."""
        tail = self.line_text(node.end_lineno).encode("utf-8")[node.end_col_offset:].decode("utf-8", "ignore")
        rest = tail.strip()
        return self.starts_line(node) and (rest == "" or rest.startswith("#"))

    def _only_child(self, stmt: ast.stmt, parent: ast.AST) -> bool:
        for name in ("body", "orelse", "finalbody"):
            seq = getattr(parent, name, None)
            if isinstance(seq, list) and stmt in seq:
                return len(seq) == 1
        return False

    def remove_statement_edit(self, stmt: ast.stmt) -> Optional[TextEdit]:
        """Edit that deletes ``stmt`` (or turns it into ``pass`` if it is the only one in its block)."""
        if not self.owns_lines(stmt):
            return None
        parent = self.parents.get(stmt)
        if parent is not None and not isinstance(parent, ast.Module) and self._only_child(stmt, parent):
            return TextEdit(stmt.lineno, stmt.col_offset, stmt.end_lineno, stmt.end_col_offset, "pass")
        end = stmt.end_lineno + 1
        if stmt.lineno == 1:  # removing the very first statement: also drop the blank lines after it
            while end <= len(self.sm.lines) and not self.line_text(end).strip():
                end += 1
        return TextEdit(stmt.lineno, 0, end, 0, "")


def node_edit(node: ast.AST, text: str) -> TextEdit:
    """Edit replacing exactly the source range of ``node``."""
    return TextEdit(node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, text)


class Fixer(ABC):
    """A rule that proposes fixes.

    ``stage`` is ``"static"`` (needs only the source) or ``"runtime"`` (needs the
    traceback of a failed run).
    """

    rule: str = ""
    stage: str = "static"

    @abstractmethod
    def propose(self, ctx: Context) -> list[Fix]:
        ...
