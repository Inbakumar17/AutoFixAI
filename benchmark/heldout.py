"""Held-out differential testing of "plausible" patches.

A patch that passes the benchmark's own tests may still be wrong (overfitting -
the central weakness of test-driven repair).  For plausible patches we therefore run
the patched program and the reference solution on many fresh random inputs that the
tests never contained, and compare outputs.

Generators exist only for programs whose inputs are easy to synthesise; the rest are
reported as "unverified".
"""

from __future__ import annotations

import random
import signal
import sys
import types
from pathlib import Path

N_INPUTS = 400


class _Timeout(BaseException):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def _load(source: str, name: str):
    module = types.ModuleType(name)
    exec(compile(source, f"<{name}>", "exec"), module.__dict__)
    return module


def _call(fn, *args):
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, 1.0)
    try:
        return ("ok", fn(*args))
    except (_Timeout, Exception) as exc:
        return ("error", type(exc).__name__)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


# ------------------------------------------------------------------ generators
def gen_quicksort(rng):
    return ([rng.randint(-5, 5) for _ in range(rng.randint(0, 12))],)


def gen_next_permutation(rng):
    while True:
        p = rng.sample(range(10), rng.randint(2, 7))
        if p != sorted(p, reverse=True):
            return (p,)


def gen_find_in_sorted(rng):
    arr = sorted(rng.sample(range(-20, 40), rng.randint(0, 15)))
    x = rng.choice(arr) if arr and rng.random() < 0.7 else rng.randint(-25, 45)
    return (arr, x)


def gen_rpn_eval(rng):
    def build(depth):
        if depth == 0 or rng.random() < 0.3:
            return [float(rng.randint(1, 9))]
        return build(depth - 1) + build(depth - 1) + [rng.choice(["+", "-", "*", "/"])]

    return (build(3),)


def _random_nodes(rng, Node):
    n = rng.randint(2, 7)
    nodes = [Node(str(i)) for i in range(n)]
    for a in nodes:
        a.successors = [b for b in nodes if b is not a and rng.random() < 0.3]
    return nodes


def gen_dfs(rng, Node):
    nodes = _random_nodes(rng, Node)
    return (nodes[0], rng.choice(nodes))


def gen_mst(rng):
    n = rng.randint(3, 6)
    weights = rng.sample(range(1, 100), n * n)
    edges, it = {}, iter(weights)
    for i in range(1, n):  # spanning chain guarantees connectivity
        edges[(rng.randrange(0, i), i)] = next(it)
    for _ in range(rng.randint(0, n)):
        a, b = rng.sample(range(n), 2)
        if (a, b) not in edges and (b, a) not in edges:
            edges[(a, b)] = next(it)
    return (edges,)


def _same(name, a, b):
    if a[0] != b[0]:
        return False
    if a[0] == "error":
        return a[1] == b[1]
    x, y = a[1], b[1]
    if name == "rpn_eval":
        return abs(x - y) < 1e-9
    if name == "minimum_spanning_tree":
        return {frozenset(e) for e in x} == {frozenset(e) for e in y}
    return x == y


GENERATORS = {
    "quicksort": gen_quicksort,
    "next_permutation": gen_next_permutation,
    "find_in_sorted": gen_find_in_sorted,
    "rpn_eval": gen_rpn_eval,
    "depth_first_search": gen_dfs,
    "minimum_spanning_tree": gen_mst,
}


def check(name: str, patched: str, reference: str, root: Path) -> dict:
    """Return {"verdict": ..., "agree": k, "total": N}."""
    if name not in GENERATORS:
        return {"verdict": "unverified", "agree": 0, "total": 0}
    for p in (str(root / "python_testcases"),):
        if p not in sys.path:
            sys.path.insert(0, p)
    from node import Node

    fp, fr = getattr(_load(patched, "p"), name), getattr(_load(reference, "r"), name)
    rng, agree = random.Random(12345), 0
    for _ in range(N_INPUTS):
        gen = GENERATORS[name]
        args = gen(rng, Node) if name == "depth_first_search" else gen(rng)
        if name == "depth_first_search":  # graph objects are mutated in place; call both on the same graph
            pass
        if _same(name, _call(fp, *args), _call(fr, *args)):
            agree += 1
    return {"verdict": "equivalent" if agree == N_INPUTS else "overfit", "agree": agree, "total": N_INPUTS}
