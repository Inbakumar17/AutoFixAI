"""Test-driven, mutation-based program repair.

When a bug produces no crash - a wrong operator, an off-by-one, the wrong
variable - rule-based fixers have nothing to latch onto.  The classic answer
from the automated-program-repair literature (GenProg, Le Goues et al. 2012;
"generate-and-validate") is:

1. *Localise*: rank source lines by suspiciousness (see :mod:`autofixai.localize`).
2. *Mutate*: generate small, syntactically valid edits ("mutants") using generic
   operators - swap ``<`` for ``<=``, ``+`` for ``-``, change a constant by one, ...
3. *Validate*: keep the first mutant that makes the whole test-suite pass.

This module contains only **generic** operators.  Nothing here knows about any
particular benchmark.  Because tests are the only specification, a patch that
passes them is *plausible*, not guaranteed correct - see the README.
"""

from __future__ import annotations

import ast
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from .astutils import FUNC_TYPES
from .edits import OverlapError, apply_edits
from .fixers.base import Context, node_edit
from .models import TextEdit

# ------------------------------------------------------------------ data model


@dataclass(frozen=True)
class Mutant:
    operator: str
    description: str
    line: int
    stmt_line: int
    edits: tuple[TextEdit, ...]
    priority: int  # lower = tried earlier among equally suspicious lines


@dataclass
class MutationResult:
    patched: Optional[str]
    mutant: Optional[Mutant]
    tried: int
    generated: int
    seconds: float

    @property
    def found(self) -> bool:
        return self.patched is not None


# ------------------------------------------------------------- operator tables

_ARITH = {
    ast.Add: ("+", r"\+"),
    ast.Sub: ("-", r"-"),
    ast.Mult: ("*", r"(?<!\*)\*(?!\*)"),
    ast.Div: ("/", r"(?<!/)/(?!/)"),
    ast.FloorDiv: ("//", r"//"),
    ast.Mod: ("%", r"%"),
}
_BITWISE = {
    ast.BitAnd: ("&", r"&"),
    ast.BitOr: ("|", r"\|"),
    ast.BitXor: ("^", r"\^"),
    ast.LShift: ("<<", r"<<"),
    ast.RShift: (">>", r">>"),
}
_BINOPS = {**_ARITH, **_BITWISE}
_GROUPS = [list(_ARITH), list(_BITWISE)]

_CMP = {
    ast.Lt: ("<", r"<(?!=)"),
    ast.LtE: ("<=", r"<="),
    ast.Gt: (">", r">(?!=)"),
    ast.GtE: (">=", r">="),
    ast.Eq: ("==", r"=="),
    ast.NotEq: ("!=", r"!="),
    ast.In: ("in", r"\bin\b"),
    ast.NotIn: ("not in", r"\bnot\s+in\b"),
    ast.Is: ("is", r"\bis\b(?!\s+not)"),
    ast.IsNot: ("is not", r"\bis\s+not\b"),
}
_CMP_GROUPS = [
    [ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq],
    [ast.In, ast.NotIn],
    [ast.Is, ast.IsNot],
]

_NEEDS_PARENS = (ast.IfExp, ast.BoolOp, ast.Compare, ast.Lambda, ast.NamedExpr)


def _group_of(op_type: type, groups: list[list[type]]) -> list[type]:
    for g in groups:
        if op_type in g:
            return g
    return []


# ---------------------------------------------------------------- generation


class _Generator:
    def __init__(self, source: str) -> None:
        self.ctx = Context.build(source, [], None)
        self.out: list[Mutant] = []

    # -- helpers --------------------------------------------------------
    def _stmt_line(self, node: ast.AST) -> int:
        cur: Optional[ast.AST] = node
        while cur is not None and not isinstance(cur, ast.stmt):
            cur = self.ctx.parents.get(cur)
        return cur.lineno if cur is not None else getattr(node, "lineno", 1)

    def _emit(self, operator: str, desc: str, node: ast.AST, edits: list[TextEdit], priority: int) -> None:
        self.out.append(
            Mutant(operator, desc, node.lineno, self._stmt_line(node), tuple(edits), priority)
        )

    def _segment_edit(self, left: ast.AST, right: ast.AST, pattern: str, replacement: str) -> Optional[TextEdit]:
        sm = self.ctx.sm
        start = sm.offset(left.end_lineno, left.end_col_offset)
        end = sm.offset(right.lineno, right.col_offset)
        segment = sm.source[start:end]
        new, count = re.subn(pattern, lambda _m: replacement, segment, count=1)
        if count == 0 or new == segment:
            return None
        return TextEdit(left.end_lineno, left.end_col_offset, right.lineno, right.col_offset, new)

    # -- operators ------------------------------------------------------
    def compare_ops(self, node: ast.Compare) -> None:
        if len(node.ops) != 1:
            return
        cur = type(node.ops[0])
        for alt in _group_of(cur, _CMP_GROUPS):
            if alt is cur:
                continue
            e = self._segment_edit(node.left, node.comparators[0], _CMP[cur][1], _CMP[alt][0])
            if e:
                self._emit("compare-op", f"replace '{_CMP[cur][0]}' with '{_CMP[alt][0]}'", node, [e], 1)

    def binary_ops(self, node: ast.BinOp) -> None:
        cur = type(node.op)
        for alt in _group_of(cur, _GROUPS):
            if alt is cur:
                continue
            e = self._segment_edit(node.left, node.right, _BINOPS[cur][1], _BINOPS[alt][0])
            if e:
                self._emit("arith-op", f"replace '{_BINOPS[cur][0]}' with '{_BINOPS[alt][0]}'", node, [e], 2)

    def augassign_ops(self, node: ast.AugAssign) -> None:
        cur = type(node.op)
        for alt in _group_of(cur, _GROUPS):
            if alt is cur:
                continue
            e = self._segment_edit(node.target, node.value, _BINOPS[cur][1] + "=", _BINOPS[alt][0] + "=")
            if e:
                self._emit("arith-op", f"replace '{_BINOPS[cur][0]}=' with '{_BINOPS[alt][0]}='", node, [e], 2)

    def bool_ops(self, node: ast.BoolOp) -> None:
        cur, alt = ("and", "or") if isinstance(node.op, ast.And) else ("or", "and")
        edits = []
        for a, b in zip(node.values, node.values[1:]):
            e = self._segment_edit(a, b, rf"\b{cur}\b", alt)
            if not e:
                return
            edits.append(e)
        self._emit("bool-op", f"replace '{cur}' with '{alt}'", node, edits, 2)

    def constants(self, node: ast.Constant) -> None:
        v = node.value
        if isinstance(v, bool):
            self._emit("constant", f"replace {v} with {not v}", node, [node_edit(node, str(not v))], 3)
        elif isinstance(v, int):
            for new in dict.fromkeys([v + 1, v - 1, 0, 1]):
                if new != v:
                    self._emit("constant", f"replace {v} with {new}", node, [node_edit(node, str(new))], 3)

    def off_by_one(self, node: ast.expr, why: str) -> None:
        if isinstance(node, ast.Constant) or not hasattr(node, "end_lineno"):
            return
        text = self.ctx.text(node)
        if not text or "\n" in text:
            return
        wrap = isinstance(node, _NEEDS_PARENS) or (
            isinstance(node, ast.BinOp) and type(node.op) in (ast.LShift, ast.RShift, ast.BitAnd, ast.BitOr, ast.BitXor)
        )
        base = f"({text})" if wrap else text
        for sign in ("+", "-"):
            self._emit("off-by-one", f"{why}: {sign} 1", node, [node_edit(node, f"{base} {sign} 1")], 3)

    def swap_arguments(self, node: ast.Call) -> None:
        args = node.args
        for i in range(len(args) - 1):
            a, b = args[i], args[i + 1]
            ta, tb = self.ctx.text(a), self.ctx.text(b)
            if isinstance(a, ast.Starred) or isinstance(b, ast.Starred) or not ta or not tb or ta == tb:
                continue
            if "\n" in ta or "\n" in tb:
                continue
            self._emit("swap-args", f"swap arguments {i + 1} and {i + 2} of the call", node,
                       [node_edit(a, tb), node_edit(b, ta)], 4)

    def negation(self, node: ast.AST) -> None:
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self.ctx.text(node.operand)
            if inner:
                self._emit("negation", "remove 'not'", node, [node_edit(node, inner)], 4)
        elif isinstance(node, (ast.If, ast.While)):
            test = self.ctx.text(node.test)
            if test and "\n" not in test:
                self._emit("negation", "negate condition", node.test, [node_edit(node.test, f"not ({test})")], 4)

    def deletions(self, node: ast.stmt) -> None:
        deletable = isinstance(node, (ast.Assign, ast.AugAssign, ast.Break, ast.Continue)) or (
            isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant)
        )
        if not deletable:
            return
        edit = self.ctx.remove_statement_edit(node)
        if edit:
            self._emit("delete-statement", f"delete statement on line {node.lineno}", node, [edit], 5)

    def name_substitution(self, func: ast.AST) -> None:
        a = func.args  # type: ignore[attr-defined]
        variables = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
        for n in ast.walk(func):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                variables.add(n.id)
        variables -= {"self", "cls"}
        if not 2 <= len(variables) <= 14:
            return
        call_targets = {id(n.func) for n in ast.walk(func) if isinstance(n, ast.Call)}
        for n in ast.walk(func):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in variables and id(n) not in call_targets:
                for other in sorted(variables - {n.id}):
                    self._emit("name-swap", f"use '{other}' instead of '{n.id}'", n, [node_edit(n, other)], 6)

    # -- driver -----------------------------------------------------------
    def run(self) -> list[Mutant]:
        if self.ctx is None:
            return []
        for node in ast.walk(self.ctx.tree):
            if isinstance(node, ast.Compare):
                self.compare_ops(node)
                for side in (node.left, *node.comparators):
                    self.off_by_one(side, "comparison operand")
            elif isinstance(node, ast.BinOp):
                self.binary_ops(node)
            elif isinstance(node, ast.AugAssign):
                self.augassign_ops(node)
            elif isinstance(node, ast.BoolOp):
                self.bool_ops(node)
            elif isinstance(node, ast.Constant):
                self.constants(node)
            elif isinstance(node, ast.Subscript) and not isinstance(node.slice, (ast.Constant, ast.Tuple)):
                if isinstance(node.slice, ast.Slice):
                    for part in (node.slice.lower, node.slice.upper):
                        if part is not None:
                            self.off_by_one(part, "slice bound")
                else:
                    self.off_by_one(node.slice, "index")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
                for arg in node.args:
                    self.off_by_one(arg, "range bound")
            elif isinstance(node, ast.Return) and node.value is not None:
                if isinstance(node.value, (ast.Name, ast.BinOp, ast.Call, ast.Subscript)):
                    self.off_by_one(node.value, "returned value")
            if isinstance(node, ast.Call):
                self.swap_arguments(node)
            if isinstance(node, (ast.UnaryOp, ast.If, ast.While)):
                self.negation(node)
            if isinstance(node, ast.stmt):
                self.deletions(node)
            if isinstance(node, FUNC_TYPES):
                self.name_substitution(node)
        return self.out


def generate_mutants(source: str) -> list[Mutant]:
    """All first-order mutants of ``source`` (syntax validity is checked at apply time)."""
    return _Generator(source).run()


# --------------------------------------------------------------------- search


def _parses(source: str) -> bool:
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


def search(
    source: str,
    oracle: Callable[[str], bool],
    *,
    scores: Optional[dict[int, float]] = None,
    max_candidates: int = 800,
    time_limit: float = 60.0,
) -> MutationResult:
    """Return the first mutant of ``source`` for which ``oracle`` (the test-suite) passes.

    ``scores`` maps line numbers to suspiciousness (e.g. from :func:`autofixai.localize.ochiai`);
    more suspicious lines are tried first, ties broken by operator simplicity.
    """
    start = time.perf_counter()
    mutants = generate_mutants(source)
    scores = scores or {}

    def key(m: Mutant) -> tuple:
        return (-max(scores.get(m.line, 0.0), scores.get(m.stmt_line, 0.0)), m.priority, m.line)

    mutants.sort(key=key)
    seen = {source}
    tried = 0
    for m in mutants:
        if tried >= max_candidates or time.perf_counter() - start > time_limit:
            break
        try:
            candidate = apply_edits(source, m.edits)
        except OverlapError:
            continue
        if candidate in seen or not _parses(candidate):
            continue
        seen.add(candidate)
        tried += 1
        try:
            ok = oracle(candidate)
        except Exception:
            ok = False
        if ok:
            return MutationResult(candidate, m, tried, len(mutants), time.perf_counter() - start)
    return MutationResult(None, None, tried, len(mutants), time.perf_counter() - start)
