from autofixai.sandbox import parse_traceback, run_code


def test_successful_run_captures_output():
    r = run_code("print('hi')")
    assert r.passed and r.stdout.strip() == "hi"


def test_runtime_error_reports_type_and_line():
    r = run_code("x = 1\ny = x / 0\n")
    assert r.status == "error"
    assert r.exc_type == "ZeroDivisionError"
    assert r.line == 2


def test_syntax_error_is_reported():
    r = run_code("def broken(:\n    pass\n")
    assert r.status == "error" and r.exc_type == "SyntaxError"


def test_infinite_loop_times_out():
    r = run_code("while True:\n    pass\n", timeout=1.0)
    assert r.status == "timeout"


def test_sys_exit_does_not_kill_the_tool():
    r = run_code("import sys\nsys.exit(3)\n")
    assert r.status == "error"


def test_parse_traceback_uses_innermost_script_frame():
    tb = (
        'Traceback (most recent call last):\n'
        '  File "/tmp/x/snippet.py", line 5, in <module>\n'
        '    f()\n'
        '  File "/tmp/x/snippet.py", line 2, in f\n'
        '    return 1 / 0\n'
        'ZeroDivisionError: division by zero\n'
    )
    assert parse_traceback(tb) == ("ZeroDivisionError", "division by zero", 2)
