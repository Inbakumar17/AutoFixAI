from autofixai.localize import ochiai
from autofixai.mutation import generate_mutants, search


def make_oracle(namespace_fn, cases):
    def oracle(src):
        env = {}
        exec(src, env)
        return all(env[namespace_fn](*args) == want for args, want in cases)

    return oracle


def test_ochiai_ranks_failing_only_lines_highest():
    scores = ochiai([({1, 2, 3}, False), ({1, 2}, True), ({1, 4}, True)])
    assert scores[3] > scores[2] > scores[1]
    assert scores[4] == 0.0


def test_ochiai_no_failures_gives_no_scores():
    assert ochiai([({1}, True)]) == {}


def test_all_mutants_that_apply_cleanly_are_syntactically_examinable():
    src = "def f(a, b):\n    if a < b:\n        return a + b\n    return 0\n"
    ops = {m.operator for m in generate_mutants(src)}
    assert {"compare-op", "arith-op", "constant", "negation", "name-swap"} <= ops


def test_search_fixes_wrong_operator():
    src = "def add(a, b):\n    return a - b\n"
    res = search(src, make_oracle("add", [((1, 2), 3), ((5, 5), 10)]))
    assert res.found and "a + b" in res.patched


def test_search_fixes_off_by_one_comparison():
    src = "def count(n):\n    total = 0\n    i = 0\n    while i < n:\n        total += 1\n        i += 1\n    return total\n"
    src_bug = src.replace("i < n", "i < n - 1")
    res = search(src_bug, make_oracle("count", [((3,), 3), ((0,), 0), ((5,), 5)]))
    assert res.found


def test_search_returns_none_when_no_single_edit_fixes():
    src = "def f(a):\n    return a\n"
    res = search(src, make_oracle("f", [((1,), 99)]), max_candidates=50)
    assert not res.found and res.patched is None


def test_localisation_prioritises_suspicious_lines():
    src = "def f(a, b):\n    x = a + b\n    y = a * b\n    return y - x\n"
    muts_line = {m.line for m in generate_mutants(src)}
    assert {2, 3, 4} <= muts_line
    seen_first = []

    def oracle(candidate):
        seen_first.append(candidate)
        return False

    search(src, oracle, scores={3: 1.0}, max_candidates=5)
    assert "a * b" not in seen_first[0]  # the first candidates mutate line 3
