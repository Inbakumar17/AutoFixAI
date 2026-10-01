"""Glue between the mutation engine and a user-supplied test command."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from .models import Fix
from .mutation import MutationResult, search


def command_oracle(path: Path, command: list[str], timeout: float = 30.0) -> Callable[[str], bool]:
    """Return ``oracle(candidate_source) -> bool`` that runs ``command`` against a candidate.

    The candidate is written to ``path`` and the command runs in ``path``'s directory.
    The caller is responsible for restoring the original file afterwards.
    """

    # Python's bytecode cache is keyed on (mtime in whole seconds, size).  Two candidates of equal
    # length written within one second (e.g. `a - b` / `a + b`) would otherwise reuse a stale .pyc.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def oracle(candidate: str) -> bool:
        path.write_text(candidate, encoding="utf-8")
        try:
            proc = subprocess.run(
                command,
                cwd=path.parent,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
        return proc.returncode == 0

    return oracle


def repair_with_tests(
    source: str,
    path: Path,
    command: list[str],
    *,
    test_timeout: float = 30.0,
    max_candidates: int = 500,
    time_limit: float = 120.0,
) -> tuple[Optional[str], Optional[Fix], MutationResult | None, bool]:
    """Try to make ``command`` pass by mutating ``source``.

    Returns ``(patched_source, fix, search_result, already_passing)``.  ``path`` is always
    restored to ``source`` before returning.
    """
    oracle = command_oracle(path, command, test_timeout)
    try:
        if oracle(source):
            return source, None, None, True
        result = search(source, oracle, max_candidates=max_candidates, time_limit=time_limit)
    finally:
        path.write_text(source, encoding="utf-8")
    if not result.found or result.mutant is None:
        return None, None, result, False
    m = result.mutant
    fix = Fix(
        rule="mutation",
        description=f"Line {m.line}: {m.description}",
        line=m.line,
        edits=list(m.edits),
        confidence=0.5,
        reason=(
            f"Found by test-driven search after {result.tried} candidates: this is the first single edit "
            "that makes your test command pass. Tests are the only specification, so review it - a "
            "passing patch can still be wrong."
        ),
    )
    return result.patched, fix, result, False
