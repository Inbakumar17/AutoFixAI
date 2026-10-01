"""Human- and machine-readable views of a :class:`Report`."""

from __future__ import annotations

import difflib
import json

from .models import Report


def unified_diff(report: Report, label: str = "code.py") -> str:
    return "".join(
        difflib.unified_diff(
            report.original.splitlines(keepends=True),
            report.fixed.splitlines(keepends=True),
            fromfile=f"{label} (original)",
            tofile=f"{label} (fixed)",
        )
    )


def format_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2)


def format_text(report: Report, label: str = "code.py", show_diff: bool = True) -> str:
    out: list[str] = []
    bar = "=" * 64
    out += [bar, f" AutoFixAI report - {label}", bar]

    out.append(f"\nIssues detected: {len(report.issues)}")
    for i in report.issues:
        out.append(f"  line {i.line:<4} [{i.rule}] {i.message}")

    if report.initial_run is not None:
        out.append(f"\nBefore: {'PASS' if report.initial_run.passed else 'FAIL'} - {report.initial_run.summary()}")

    out.append(f"\nFixes applied: {len(report.fixes)} (in {report.rounds} round{'s' if report.rounds != 1 else ''})")
    for n, f in enumerate(report.fixes, 1):
        out.append(f"  {n}. line {f.line:<4} [{f.rule}] {f.description}  (confidence {f.confidence:.2f})")
        out.append(f"       why: {f.reason}")

    if show_diff and report.changed:
        out.append("\nDiff:")
        out.append(unified_diff(report, label).rstrip("\n"))

    if report.final_run is not None:
        out.append(f"\nAfter:  {'PASS' if report.final_run.passed else 'FAIL'} - {report.final_run.summary()}")
        if report.final_run.stdout.strip():
            out.append("  program output: " + report.final_run.stdout.strip().replace("\n", "\n                  "))

    if report.unresolved:
        out.append("\nStill unresolved (needs a human):")
        out += [f"  - {u}" for u in report.unresolved]

    out.append("\nResult: " + ("FIXED" if report.success and report.changed else "CLEAN" if report.success else "NEEDS ATTENTION"))
    return "\n".join(out)
