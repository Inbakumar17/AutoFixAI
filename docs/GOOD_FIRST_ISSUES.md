# Issues to open on day one

Copy each block into a new GitHub issue with the listed labels. They are ordered easiest first.
A repo with 6-8 clear, scoped issues is far more likely to attract contributors than an empty tracker.

---

### 1. Fix `== None` / `!= None` comparisons  
**Labels:** `good first issue`, `fixer`  
`if x == None:` should be `if x is None:` (and `!= None` -> `is not None`).
Add a static fixer in `autofixai/fixers/static.py` (model it on `IsLiteralFixer`).

**Acceptance criteria**
- [ ] Fixes `x == None`, `x != None`, and `None == x`
- [ ] Does not touch `x == "None"` (a string) or `==` between two non-None values
- [ ] Tests include a look-alike that must stay unchanged
- [ ] Rule name `none-comparison`, listed in the README table

---

### 2. Replace bare `except:` with `except Exception:`  
**Labels:** `good first issue`, `fixer`  
A bare `except:` also swallows `KeyboardInterrupt` and `SystemExit`.

**Acceptance criteria**
- [ ] `except:` becomes `except Exception:`; `except ValueError:` is untouched
- [ ] Reason string explains the difference
- [ ] Tests + README row

---

### 3. Add `--select RULE` to run only chosen rules  
**Labels:** `good first issue`, `cli`  
The CLI has `--ignore`; add its inverse. Wire it through `repair(...)`.

**Acceptance criteria**
- [ ] `autofix f.py --select unused-import` only applies that rule
- [ ] `--select` and `--ignore` can be combined (ignore wins)
- [ ] Unknown rule names produce a helpful error listing valid rules

---

### 4. `--check` mode for CI (exit non-zero if changes would be made)  
**Labels:** `good first issue`, `cli`  
Like `black --check`: never writes files, exits `3` when fixes are available.

**Acceptance criteria**
- [ ] Exit codes documented in README
- [ ] Works together with `--json`
- [ ] Test covers both outcomes

---

### 5. Mutation operator: swap related function names  
**Labels:** `help wanted`, `mutation`  
Many logic bugs are a wrong-but-similar call: `min`/`max`, `any`/`all`, `append`/`extend`,
`sorted`/`reversed`, `lstrip`/`rstrip`. Add a generic operator in `autofixai/mutation.py`.

**Acceptance criteria**
- [ ] New operator emits one mutant per swap, priority between `constant` and `name-swap`
- [ ] Unit tests in `tests/test_mutation.py`
- [ ] Re-run `python -m benchmark.run_quixbugs` and report whether the correct-repair count changes
      (it may not - say so honestly)

---

### 6. Syntax-error repair: missing colon after `def` / `if` / `for` / `while`  
**Labels:** `help wanted`, `fixer`  
Currently syntax errors are only reported. Handle the most common case first (missing `:`), using the
position Python reports for the `SyntaxError`.

**Acceptance criteria**
- [ ] `def f()` -> `def f():`, same for `if/elif/else/for/while/class/try/except/with`
- [ ] The engine must re-parse after the edit and discard it if the result still does not parse
- [ ] Benchmark case `UNSUP-syntax-colon` moves out of the "unsupported" category

---

### 7. Emit SARIF so findings appear in GitHub Code Scanning  
**Labels:** `help wanted`, `feature`  
Add `--sarif out.sarif`, converting `Report.issues` and `Report.fixes` to SARIF 2.1.0
(include fix suggestions as `fixes[]`).

**Acceptance criteria**
- [ ] Output validates against the SARIF 2.1.0 schema
- [ ] Documented example workflow that uploads the file with `github/codeql-action/upload-sarif`

---

### 8. Evaluate on BugsInPy (real-world bugs)  
**Labels:** `research`, `help wanted`  
QuixBugs is small and algorithmic. Add `benchmark/run_bugsinpy.py` that checks out a bug, runs its failing
test as the `--test-cmd` oracle, and records plausible/identical/overfit outcomes like the QuixBugs harness.

**Acceptance criteria**
- [ ] Reproducible instructions in `benchmark/README.md`
- [ ] Results table committed, with honest caveats
- [ ] Expect a much lower success rate than QuixBugs - that is a valid, publishable result

---

### 9. Windows resource limits for the sandbox  
**Labels:** `help wanted`, `platform`  
CPU/memory limits are POSIX-only (`resource`). Investigate Windows Job Objects (via `ctypes`) to enforce a
memory cap, or document the gap precisely. Tests must be skipped cleanly on the other platform.
