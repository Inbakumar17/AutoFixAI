"""Precision tests: the new fixers must fix their target *and* leave look-alikes alone."""

from autofixai import repair


def test_str_concat_fixed():
    r = repair('n = 3\nprint("n=" + n)\n')
    assert r.success and r.final_run.stdout.strip() == "n=3"


def test_str_concat_not_applied_when_program_already_works():
    src = 'name = "Ada"\nprint("Hi " + name)\n'
    assert not repair(src).changed


def test_index_range_fix_is_reported_with_reason():
    r = repair("xs = [1, 2]\nfor i in range(len(xs) + 1):\n    print(xs[i])\n")
    assert r.success
    assert r.fixes[0].rule == "index-off-by-one" and "one index past the end" in r.fixes[0].reason


def test_index_error_without_known_pattern_is_left_alone():
    r = repair("xs = [1, 2]\nprint(xs[10])\n")
    assert not r.changed and not r.success


def test_key_error_needs_a_literal_key():
    src = 'd = {"a": 1}\nk = "b"\nprint(d[k])\n'
    r = repair(src)
    assert not r.changed and not r.success  # unknown key expression: refuse to guess


def test_key_error_augmented_assignment_is_not_rewritten():
    src = 'd = {}\nd["a"] += 1\n'
    assert not repair(src).changed


def test_is_literal_leaves_is_none_alone():
    src = "x = None\nif x is None:\n    print(1)\n"
    assert not repair(src, execute=False).changed


def test_is_literal_not_negation():
    r = repair('s = "a"\nif s is not "b":\n    print("diff")\n')
    assert '!= "b"' in r.fixed and r.success
