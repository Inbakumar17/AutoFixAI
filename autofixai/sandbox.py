"""Run code in an isolated child process and capture what went wrong.

The original prototype used ``exec(code, {})`` inside the tool's own process.
That lets buggy code hang the tool (``while True``), exhaust memory, or call
``sys.exit``.  Here the code runs in a separate interpreter with:

* a hard wall-clock timeout,
* isolated mode (``-I``: ignores user site-packages and environment vars),
* a throw-away working directory,
* stdin closed, and (on POSIX) CPU-time and memory limits.

This is *defence in depth for buggy code*, not a security sandbox for hostile
code.  Never point AutoFixAI at code you would not run yourself.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from .models import ExecutionResult

SCRIPT_NAME = "snippet.py"
MAX_CAPTURE = 20_000

_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)')
_EXC_RE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*)(?::\s?(?P<msg>.*))?$")


def parse_traceback(stderr: str) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Extract (exception type, message, line-in-our-script) from a traceback."""
    text = stderr.strip()
    if not text:
        return None, None, None
    last = next((ln.strip() for ln in reversed(text.splitlines()) if ln.strip()), "")
    match = _EXC_RE.match(last)
    exc_type = match.group("type") if match else None
    exc_msg = (match.group("msg") or "") if match else last
    line = None
    for filename, number in _FRAME_RE.findall(text):
        if os.path.basename(filename) == SCRIPT_NAME:
            line = int(number)  # keep the innermost frame inside our script
    return exc_type, exc_msg, line


def _limiter(memory_mb: int, cpu_seconds: int) -> Optional[Callable[[], None]]:
    if os.name != "posix":
        return None

    def apply() -> None:  # runs in the child, before exec
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            limit = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ImportError, ValueError, OSError):
            pass

    return apply


def _clip(text: str) -> str:
    return text if len(text) <= MAX_CAPTURE else text[:MAX_CAPTURE] + "\n...[truncated]"


def run_code(source: str, timeout: float = 5.0, memory_mb: int = 512) -> ExecutionResult:
    """Execute ``source`` and describe the outcome."""
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("SYSTEMROOT", "PATH"):  # required by the interpreter on Windows
        if key in os.environ:
            env[key] = os.environ[key]

    with tempfile.TemporaryDirectory(prefix="autofixai_") as tmp:
        script = Path(tmp) / SCRIPT_NAME
        script.write_text(source, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-I", SCRIPT_NAME],
                cwd=tmp,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                preexec_fn=_limiter(memory_mb, max(1, int(timeout) + 1)),
            )
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            return ExecutionResult(
                status="timeout",
                stdout=_clip(out),
                exc_type="TimeoutError",
                exc_message=f"execution exceeded {timeout:g}s",
            )

    if proc.returncode == 0:
        return ExecutionResult(status="ok", stdout=_clip(proc.stdout), stderr=_clip(proc.stderr))

    exc_type, exc_msg, line = parse_traceback(proc.stderr)
    if exc_type is None:
        exc_msg = f"process exited with code {proc.returncode}"
    return ExecutionResult(
        status="error",
        stdout=_clip(proc.stdout),
        stderr=_clip(proc.stderr),
        exc_type=exc_type,
        exc_message=exc_msg,
        line=line,
    )
