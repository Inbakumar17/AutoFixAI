# Architecture

```
autofixai/
  models.py      Issue, Fix, TextEdit, ExecutionResult, Report  (plain dataclasses)
  analysis.py    static detection: pyflakes + project AST rules -> list[Issue]
  astutils.py    parent maps, purity check, mutable-default detection, name tables
  edits.py       SourceMap + apply_edits + select_non_overlapping  (exact-range editing)
  sandbox.py     run code in a child process; parse the traceback -> ExecutionResult
  fixers/
    base.py      Fixer interface + Context (source, tree, issues, last run, helpers)
    static.py    UndefinedName / UnusedVariable / UnusedImport / MutableDefault / IsLiteral fixers
    runtime.py   ZeroDivision / IndexError / KeyError / StrConcat fixers (driven by the traceback)
  ../benchmark/  cases.py (corpus + references), run_benchmark.py (harness -> RESULTS.md)
  localize.py    spectrum-based fault localisation (Ochiai)
  mutation.py    generic mutation operators + generate-and-validate search
  testdriven.py  runs a user test command as the oracle (writes/restores the file)
  engine.py      the repair loop
  report.py      text / JSON / diff views
  cli.py         `autofix` command
```

## Design decisions

**1. Edits by position, not by string.**
The prototype used `code.replace(old, new)`. That rewrites every match - inside strings,
comments and longer identifiers - and can silently corrupt working code. Now every fix is a set
of `TextEdit(start, end, text)` built from AST node positions (`lineno`, `col_offset`, ...). Two
fixes that touch overlapping ranges cannot both be applied in the same round; the later one is
re-proposed after re-analysis.

**2. Scope-aware detection instead of "every call is undefined".**
The prototype's analyser flagged any function call. We use pyflakes' scope analysis, so builtins,
imports, parameters and nested scopes are handled correctly.

**3. Validate by running, in a separate process.**
`exec()` inside the tool can hang, exhaust memory or call `sys.exit()`. The sandbox runs code with
a timeout, isolated mode and (POSIX) CPU/memory limits, and parses the traceback for the exception
type and the exact failing line - which is how runtime fixers know where to look.

**4. Fixes can unlock fixes.**
A typo'd function name hides the `ZeroDivisionError` behind it. The engine therefore loops:
apply -> re-run -> read new error -> propose again, with a round cap and cycle detection.

**5. Never leave the code worse.**
After applying, the engine re-parses the result; any fix that would produce a syntax error is
dropped. Fixes that don't make progress stop the loop.

**6. Confidence is explicit.**
Rename confidence is the string similarity ratio; a guard for a zero divisor is 0.7 because it
changes behaviour (returns `None`). Making the uncertainty visible is a feature: it tells the
reader where to look hardest.

## Mapping from the original prototype

| Prototype module | Now |
|---|---|
| `bug_detector.py` | `analysis.py` |
| `root_cause_analyzer.py` | `analysis.py` (scope-aware, no false "undefined" on every call) |
| `dependency_analyzer.py`, `semantic_fix_generator.py`, `fix_generator.py` | `fixers/static.py` (`UnusedVariableFixer`, ...) |
| `symbol_table.py`, `rename_fixer.py`, `self_healer.py` | `fixers/static.py` (`UndefinedNameFixer`) |
| `logic_fix_generator.py` | `fixers/runtime.py` (`ZeroDivisionFixer`, general instead of hard-coded) |
| `test_validator.py` | `sandbox.py` |
| `explainable_fix.py` | `report.py` + `Fix.reason` / `Fix.confidence` |
| `main.py` | `engine.py` + `cli.py` |

## Known weaknesses (worth fixing, good first issues)

* `StrConcatFixer` picks the earliest-evaluated `str + non-str` expression. If that operand is
  actually already a string variable it wraps it in a harmless `str()`; the next round then fixes the
  real culprit. Type inference would remove the noise.
* Confidence values are hand-set rules, not calibrated probabilities.
* Guard fixes (`return None`) change behaviour; they are marked with lower confidence for that reason.

## Test-driven repair: design notes

* **Generic operators only.** `mutation.py` contains no knowledge of any benchmark program.
* **First-order edits.** Every mutant is a set of exact-range `TextEdit`s, so the diff is minimal and
  comments/formatting survive.
* **Ranking.** Candidates are sorted by max(suspiciousness of the edited line, of its statement),
  then by operator simplicity (comparison/arith operator before constant before name swap before deletion).
* **Overfitting is the central risk.** `benchmark/heldout.py` differential-tests plausible patches on
  fresh random inputs. It is a benchmark tool; end users only get the "review it" warning.
* **A real bug this taught us:** two same-length candidates written within one second reuse a stale
  `.pyc`, so a correct patch can appear to fail. The oracle runs tests with `PYTHONDONTWRITEBYTECODE=1`.
