# Publishing checklist

## 0. One-time: put the code on GitHub
```bash
cd AutoFixAI                      # the unzipped project folder
git init -b main
git config user.name  "Your Name"
git config user.email "your-github-noreply-email"   # GitHub > Settings > Emails shows it
git add .
git commit -m "AutoFixAI v0.4.0: automated Python bug detection and repair"
git remote add origin https://github.com/KomaliG7/AutoFixAI.git
git push -u origin main
```
Create the empty repo first on github.com (no README/licence - they already exist here).

Then in the repo **Settings**:
* *About* (gear icon, top right): description `Automatically detect, repair, validate and explain Python bugs`;
  topics `python`, `automated-program-repair`, `static-analysis`, `debugging`, `developer-tools`, `ast`.
* *General > Features*: enable **Issues** and **Discussions**.
* *Branches*: protect `main` (require the CI checks to pass).
* Create the labels: `good first issue`, `help wanted`, `fixer`, `mutation`, `docs`, `research`.
* Open the issues from `docs/GOOD_FIRST_ISSUES.md` (copy/paste).

## 1. Check everything locally
```bash
pip install -e ".[dev]" ruff build twine
ruff check .
pytest -q
python -m benchmark.run_benchmark
python -m build && twine check dist/*
```

## 2. Publish to PyPI (Trusted Publishing - no tokens)
1. Create an account at https://pypi.org (enable 2FA).
2. PyPI > *Your projects* > *Publishing* > **Add a pending publisher**:
   project `autofixai`, owner `KomaliG7`, repo `AutoFixAI`, workflow `release.yml`, environment `pypi`.
3. On GitHub: *Settings > Environments > New environment* named `pypi`.
4. Tag and release:
   ```bash
   git tag v0.4.0 && git push --tags
   ```
   then GitHub > *Releases* > *Draft a new release* > choose `v0.4.0` > paste the CHANGELOG entry > **Publish**.
   The `Release to PyPI` workflow builds, tests and uploads.
5. Verify in a clean environment: `pip install autofixai && autofix --version`.

(To rehearse first, publish to https://test.pypi.org with a separate pending publisher.)

## 3. Make it discoverable
* Record the demo: install [VHS](https://github.com/charmbracelet/vhs), run `vhs docs/demo.tape`,
  commit `docs/demo.gif`, and embed it at the top of the README.
* Fill in your family name in `CITATION.cff`.
* Pin the repository on your GitHub profile; add it to your resume with the *verifiable* numbers
  (see README: 11/40 correct on QuixBugs, 0 false positives on controls).
