"""Spectrum-based fault localisation (SBFL).

Given, for every test, the set of source lines it executed and whether it
passed, rank lines by how suspicious they are.  A line executed by many failing
tests and few passing ones is more likely to contain the bug.

We use the Ochiai formula, one of the best-performing SBFL metrics in the
program-repair literature (Abreu et al., 2007):

    suspiciousness(line) = ef / sqrt(total_failed * (ef + ep))

where ``ef``/``ep`` are the numbers of failing/passing tests that executed the line.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import sqrt


def ochiai(tests: Iterable[tuple[set[int], bool]]) -> dict[int, float]:
    tests = list(tests)
    total_failed = sum(1 for _, passed in tests if not passed)
    if total_failed == 0:
        return {}
    ef: dict[int, int] = {}
    ep: dict[int, int] = {}
    for lines, passed in tests:
        bucket = ep if passed else ef
        for line in lines:
            bucket[line] = bucket.get(line, 0) + 1
    scores: dict[int, float] = {}
    for line in set(ef) | set(ep):
        failed_here = ef.get(line, 0)
        if failed_here == 0:
            scores[line] = 0.0
            continue
        scores[line] = failed_here / sqrt(total_failed * (failed_here + ep.get(line, 0)))
    return scores
