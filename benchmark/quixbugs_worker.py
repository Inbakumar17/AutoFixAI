"""Evaluate AutoFixAI on ONE QuixBugs program.  Runs in its own process.

QuixBugs (Lin et al., 2017): 40 classic algorithms, each with a single-line bug
and a test-suite.  We drive the project's own pytest test files, but run them
in-process (importing the candidate as ``python_programs.<name>``) so that
hundreds of candidates can be validated per second on a single core.

Nothing here is specific to a program: the same generic engine
(:mod:`autofixai.mutation`) is used for all 40.

Usage: python -m benchmark.quixbugs_worker <quixbugs_root> <program_name>
Prints one JSON object on the last line of stdout.
"""

from __future__ import annotations

import ast
import difflib
import importlib
import json
import resource
import signal
import sys
import time
import types
from pathlib import Path

from _pytest.outcomes import Skipped

from autofixai import repair
from autofixai.localize import ochiai
from autofixai.mutation import search


def _normalised(source: str) -> str:
    """AST fingerprint that ignores module-level docstring blocks (the reference files drop them)."""
    tree = ast.parse(source)
    tree.body = [
        n for n in tree.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))
    ]
    return ast.dump(tree)


class _Timeout(BaseException):
    """Not an Exception subclass, so candidate code cannot swallow it."""


def _on_alarm(signum, frame):
    raise _Timeout()


class Suite:
    def __init__(self, root: Path, name: str) -> None:
        self.root, self.name = root, name
        self.filename = f"<candidate:{name}>"
        for p in (str(root / "python_testcases"), str(root)):
            if p not in sys.path:
                sys.path.insert(0, p)
        import pytest

        pytest.use_correct = False
        pytest.run_slow = False
        self.limit = 2.0

    def _load(self, source: str):
        module = types.ModuleType(f"python_programs.{self.name}")
        exec(compile(source, self.filename, "exec"), module.__dict__)
        sys.modules[f"python_programs.{self.name}"] = module
        sys.modules.pop(f"test_{self.name}", None)
        test_module = importlib.import_module(f"test_{self.name}")
        tests = []
        for attr in sorted(dir(test_module)):
            fn = getattr(test_module, attr)
            if not attr.startswith("test") or not callable(fn) or isinstance(fn, type):
                continue
            params = [m for m in getattr(fn, "pytestmark", []) if m.name == "parametrize"]
            if params:
                for i, values in enumerate(params[0].args[1]):
                    tests.append((f"{attr}[{i}]", fn, tuple(values)))
            else:
                tests.append((attr, fn, ()))
        return tests

    def _tracer(self, lines: set):
        def global_trace(frame, event, arg):
            if frame.f_code.co_filename != self.filename:
                return None
            lines.add(frame.f_lineno)

            def local(frame, event, arg):
                if event == "line":
                    lines.add(frame.f_lineno)
                return local

            return local

        return global_trace

    def run(self, source: str, coverage: bool = False, stop_on_fail: bool = False):
        """Return [(test_id, passed, covered_lines)].  Each test has its own time limit."""
        results = []
        signal.signal(signal.SIGALRM, _on_alarm)
        try:
            signal.setitimer(signal.ITIMER_REAL, self.limit * 3)
            tests = self._load(source)
            signal.setitimer(signal.ITIMER_REAL, 0)
        except (_Timeout, Exception):
            signal.setitimer(signal.ITIMER_REAL, 0)
            return [("<load-error>", False, set())]
        for tid, fn, args in tests:
            lines: set[int] = set()
            if coverage:
                sys.settrace(self._tracer(lines))
            signal.setitimer(signal.ITIMER_REAL, self.limit)
            try:
                fn(*args)
                ok = True
            except Skipped:  # the benchmark itself skips its slowest cases
                ok = True
            except (_Timeout, Exception):
                ok = False
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                sys.settrace(None)
            results.append((tid, ok, lines))
            if stop_on_fail and not ok:
                break
        return results

    def passes(self, source: str) -> bool:
        res = self.run(source, stop_on_fail=True)
        return bool(res) and all(ok for _, ok, _ in res)


def main() -> None:
    root, name = Path(sys.argv[1]), sys.argv[2]
    time_limit = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))

    buggy = (root / "python_programs" / f"{name}.py").read_text()
    correct = (root / "correct_python_programs" / f"{name}.py").read_text()
    suite = Suite(root, name)
    out = {"name": name}

    suite.limit = 15.0
    t0 = time.perf_counter()
    correct_res = suite.run(correct)
    dur = time.perf_counter() - t0
    if not correct_res or not all(ok for _, ok, _ in correct_res):
        print(json.dumps({**out, "status": "invalid", "note": "reference does not pass its own tests here"}))
        return
    suite.limit = min(2.0, max(0.25, 10 * dur / max(1, len(correct_res))))

    buggy_res = suite.run(buggy, coverage=True)
    if all(ok for _, ok, _ in buggy_res):
        print(json.dumps({**out, "status": "invalid", "note": "buggy version already passes"}))
        return
    out["failing_tests"] = sum(1 for _, ok, _ in buggy_res if not ok)
    out["total_tests"] = len(buggy_res)
    scores = ochiai([(lines, ok) for _, ok, lines in buggy_res])

    baseline = repair(buggy, execute=False)
    out["baseline_pipeline_passes"] = suite.passes(baseline.fixed)

    result = search(buggy, suite.passes, scores=scores, max_candidates=2000, time_limit=time_limit)
    out.update(tried=result.tried, generated=result.generated, seconds=round(result.seconds, 2))
    if not result.found:
        out["status"] = "failed"
    else:
        same = _normalised(result.patched) == _normalised(correct)
        out["status"] = "identical" if same else "plausible"
        out["patch"] = result.mutant.description
        out["operator"] = result.mutant.operator
        out["patched"] = result.patched
        out["diff"] = "".join(
            difflib.unified_diff(buggy.splitlines(True), result.patched.splitlines(True), "buggy", "patched", n=0)
        )
    print(json.dumps(out))


if __name__ == "__main__":
    main()
