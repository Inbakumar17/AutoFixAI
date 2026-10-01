"""Core data structures shared across AutoFixAI.

Everything the pipeline produces is plain data (dataclasses), so results can be
serialised to JSON, tested easily, and reused by other tools (IDE plugins, CI).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class TextEdit:
    """Replace the source range [start, end) with ``text``.

    Lines are 1-indexed. Columns are UTF-8 *byte* offsets, exactly like the
    ``col_offset`` values produced by Python's ``ast`` module, so AST node
    positions can be used directly.  An insertion has start == end.
    """

    start_line: int
    start_col: int
    end_line: int
    end_col: int
    text: str = ""


@dataclass
class Issue:
    """A problem found in the code (statically or by running it)."""

    rule: str
    message: str
    line: int
    col: int = 0
    severity: str = "warning"  # "error" | "warning"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fix:
    """A proposed repair: one or more text edits plus an explanation."""

    rule: str
    description: str
    line: int
    edits: list[TextEdit]
    confidence: float
    reason: str


@dataclass
class ExecutionResult:
    """Outcome of running a piece of code in the sandbox."""

    status: str  # "ok" | "error" | "timeout"
    stdout: str = ""
    stderr: str = ""
    exc_type: Optional[str] = None
    exc_message: Optional[str] = None
    line: Optional[int] = None

    @property
    def passed(self) -> bool:
        return self.status == "ok"

    def summary(self) -> str:
        if self.status == "ok":
            return "runs without errors"
        if self.status == "timeout":
            return "timed out"
        where = f" (line {self.line})" if self.line else ""
        detail = f"{self.exc_type}: {self.exc_message}" if self.exc_type else (self.exc_message or "failed")
        return f"{detail}{where}"


@dataclass
class Report:
    """Full result of a repair session."""

    original: str
    fixed: str
    issues: list[Issue]
    remaining_issues: list[Issue]
    fixes: list[Fix]
    initial_run: Optional[ExecutionResult]
    final_run: Optional[ExecutionResult]
    rounds: int
    unresolved: list[str]

    @property
    def changed(self) -> bool:
        return self.original != self.fixed

    @property
    def success(self) -> bool:
        """True when nothing is left to fix (and the code runs, if it was executed)."""
        if self.final_run is not None and not self.final_run.passed:
            return False
        if any(u.startswith("tests:") for u in self.unresolved):
            return False
        return not any(i.severity == "error" for i in self.remaining_issues)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["changed"] = self.changed
        data["success"] = self.success
        return data
