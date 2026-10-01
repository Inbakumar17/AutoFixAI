# Security policy

## Threat model - please read

AutoFixAI **runs code**. By default it executes the file you give it (to catch runtime errors), and with
`--test-cmd` it executes the command you give it, repeatedly, against candidate patches.

* The sandbox (separate process, timeout, isolated mode, CPU/memory limits on POSIX) protects against
  *accidents* such as infinite loops and runaway memory. It is **not** a security boundary.
* **Never run AutoFixAI on code or test commands you would not run yourself.**
* `--no-run` performs static analysis only and never executes the target.
* `--test-cmd` temporarily overwrites the target file; it is restored afterwards.

## Reporting a vulnerability

Please report privately through GitHub:
<https://github.com/KomaliG7/AutoFixAI/security/advisories/new>

Please do not open a public issue for security problems. You can expect an acknowledgement within a
week. Examples of in-scope reports: the tool writing outside the intended file, leaving the target file
corrupted after an interrupted run, or executing code in `--no-run` mode.

## Supported versions

Only the latest release receives fixes.
