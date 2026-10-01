# Contributing to AutoFixAI

Thanks for helping! Bug reports, new fixers, tests and docs are all welcome.

## Setup

```bash
git clone https://github.com/KomaliG7/AutoFixAI.git
cd AutoFixAI
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Adding a new fixer (the easiest way to contribute)

1. Decide the stage: **static** (source only) goes in `autofixai/fixers/static.py`;
   **runtime** (needs a traceback) goes in `autofixai/fixers/runtime.py`.
2. Subclass `Fixer`, set `rule`, and implement `propose(ctx) -> list[Fix]`.
   Use AST node positions to build `TextEdit`s - **never `str.replace` on the whole file**.
3. Return an honest `confidence` (0-1) and a plain-English `reason`.
4. Register it in `autofixai/fixers/__init__.py::default_fixers`.
5. Add tests in `tests/test_repair.py`: a case that is fixed, and at least one
   *look-alike that must NOT be changed*. Precision matters more than coverage.

## Principles

* **Never break working code.** When unsure, propose nothing.
* **Exact edits only.** Comments, strings and formatting we did not need to touch stay identical.
* **Every fix explains itself.**
* Keep runtime dependencies minimal.

## Pull requests

Run `pytest` and `ruff check .` before opening a PR, keep changes focused, and describe the bug class you fix.
Look for issues labelled `good first issue`.

## Questions and ideas

Open a GitHub Discussion or an issue using the templates. Please read the
[Code of Conduct](CODE_OF_CONDUCT.md); security problems go through [SECURITY.md](SECURITY.md).
