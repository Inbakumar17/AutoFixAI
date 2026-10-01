"""Fixers driven by a runtime failure (they need the traceback of a real run)."""

from __future__ import annotations

import ast
import re
from typing import Optional

from ..astutils import (
    FUNC_TYPES,
    enclosing,
    enclosing_statement,
    is_zero_constant,
    param_names,
)
from ..models import Fix, TextEdit
from .base import Context, Fixer, node_edit

_DIV_OPS = (ast.Div, ast.FloorDiv, ast.Mod)


class ZeroDivisionFixer(Fixer):
    """Repair ``ZeroDivisionError`` reported at a specific line.

    * ``a / 0`` (literal zero): the only function parameter that is *not* already
      part of the expression is almost certainly the intended divisor.
    * ``a / b``: add a guard so a zero divisor returns ``None`` instead of crashing.

    Both cases add the guard, because the divisor may still be zero at runtime.
    """

    rule = "zero-division"
    stage = "runtime"

    def propose(self, ctx: Context) -> list[Fix]:
        run = ctx.run
        if run is None or run.exc_type != "ZeroDivisionError" or not run.line:
            return []
        node = self._find_division(ctx, run.line)
        if node is None:
            return []
        func = enclosing(node, ctx.parents, FUNC_TYPES)
        stmt = enclosing_statement(node, ctx.parents)
        if func is None or stmt is None or not ctx.starts_line(stmt):
            return []

        divisor = node.right
        edits: list[TextEdit] = []
        if is_zero_constant(divisor):
            used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            candidates = [p for p in param_names(func) if p not in used]
            if len(candidates) != 1:
                return []
            name = candidates[0]
            edits.append(node_edit(divisor, name))
            confidence = 0.75
            description = f"Replace the literal divisor 0 with parameter '{name}' and guard against zero"
            reason = (
                f"Dividing by the literal 0 always fails. '{name}' is the only parameter of "
                f"{func.name}() not already used in this expression, so it is most likely the intended "
                "divisor. A guard handles the case where it is genuinely zero."
            )
        elif isinstance(divisor, ast.Name):
            name = divisor.id
            confidence = 0.7
            description = f"Guard the division by '{name}' against zero"
            reason = (
                f"'{name}' was zero when the division ran. Returning None early avoids the crash; "
                "review whether None is the right result for your program."
            )
        else:
            return []

        indent = ctx.indent_of(stmt.lineno)
        guard = f"{indent}if {name} == 0:\n{indent}{ctx.indent_unit(indent)}return None\n"
        edits.append(TextEdit(stmt.lineno, 0, stmt.lineno, 0, guard))
        return [
            Fix(
                rule=self.rule,
                description=description,
                line=stmt.lineno,
                edits=edits,
                confidence=confidence,
                reason=reason,
            )
        ]

    @staticmethod
    def _find_division(ctx: Context, line: int) -> Optional[ast.BinOp]:
        found = [
            n
            for n in ast.walk(ctx.tree)
            if isinstance(n, ast.BinOp) and isinstance(n.op, _DIV_OPS) and n.lineno <= line <= n.end_lineno
        ]
        for n in found:
            if is_zero_constant(n.right):
                return n
        named = [n for n in found if isinstance(n.right, ast.Name)]
        return named[0] if len(named) == 1 else None


def _is_len_call(node: ast.AST, name: Optional[str] = None) -> bool:
    ok = (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
    )
    return ok and (name is None or node.args[0].id == name)


def _subscripts_on_line(ctx: Context, line: int) -> list[ast.Subscript]:
    return [
        n
        for n in ast.walk(ctx.tree)
        if isinstance(n, ast.Subscript) and n.lineno <= line <= n.end_lineno and isinstance(n.value, ast.Name)
    ]


class IndexErrorFixer(Fixer):
    """Repair classic off-by-one ``IndexError`` patterns.

    Recognised (all keyed to the subscript that failed at the traceback line):
      * ``for i in range(len(xs) + 1): ... xs[i]``  ->  ``range(len(xs))``
      * ``while i <= len(xs): ... xs[i]``           ->  ``i < len(xs)``
      * ``xs[len(xs)]``                             ->  ``xs[len(xs) - 1]``
    """

    rule = "index-off-by-one"
    stage = "runtime"

    def propose(self, ctx: Context) -> list[Fix]:
        run = ctx.run
        if run is None or run.exc_type != "IndexError" or not run.line:
            return []
        for sub in _subscripts_on_line(ctx, run.line):
            name = sub.value.id
            fix = (
                self._last_element(ctx, sub, name)
                or self._range_loop(ctx, sub, name)
                or self._while_loop(ctx, sub, name)
            )
            if fix:
                return [fix]
        return []

    def _last_element(self, ctx: Context, sub: ast.Subscript, name: str) -> Optional[Fix]:
        if not _is_len_call(sub.slice, name):
            return None
        return Fix(
            rule=self.rule,
            description=f"Use {name}[len({name}) - 1] to reach the last element",
            line=sub.lineno,
            edits=[node_edit(sub.slice, f"len({name}) - 1")],
            confidence=0.8,
            reason=f"Valid indexes run from 0 to len({name}) - 1, so {name}[len({name})] is always one past the end.",
        )

    def _range_loop(self, ctx: Context, sub: ast.Subscript, name: str) -> Optional[Fix]:
        cur = ctx.parents.get(sub)
        while cur is not None:
            if isinstance(cur, ast.For) and isinstance(cur.iter, ast.Call):
                call = cur.iter
                if isinstance(call.func, ast.Name) and call.func.id == "range" and call.args:
                    stop = call.args[-1]
                    if (
                        isinstance(stop, ast.BinOp)
                        and isinstance(stop.op, ast.Add)
                        and _is_len_call(stop.left, name)
                        and isinstance(stop.right, ast.Constant)
                        and stop.right.value == 1
                    ):
                        return Fix(
                            rule=self.rule,
                            description=f"Change range(... len({name}) + 1) to range(... len({name}))",
                            line=call.lineno,
                            edits=[node_edit(stop, ctx.text(stop.left) or f"len({name})")],
                            confidence=0.85,
                            reason=(
                                f"The loop runs one index past the end of {name}; its last valid "
                                f"index is len({name}) - 1, and range() already excludes its stop value."
                            ),
                        )
            cur = ctx.parents.get(cur)
        return None

    def _while_loop(self, ctx: Context, sub: ast.Subscript, name: str) -> Optional[Fix]:
        cur = ctx.parents.get(sub)
        while cur is not None:
            if isinstance(cur, ast.While) and isinstance(cur.test, ast.Compare):
                t = cur.test
                if len(t.ops) == 1 and isinstance(t.ops[0], ast.LtE) and _is_len_call(t.comparators[0], name):
                    start = ctx.sm.offset(t.left.end_lineno, t.left.end_col_offset)
                    end = ctx.sm.offset(t.comparators[0].lineno, t.comparators[0].col_offset)
                    segment = ctx.sm.source[start:end]
                    if "<=" in segment:
                        return Fix(
                            rule=self.rule,
                            description=f"Change '<=' to '<' in the loop condition over len({name})",
                            line=t.lineno,
                            edits=[
                                TextEdit(
                                    t.left.end_lineno,
                                    t.left.end_col_offset,
                                    t.comparators[0].lineno,
                                    t.comparators[0].col_offset,
                                    segment.replace("<=", "<", 1),
                                )
                            ],
                            confidence=0.8,
                            reason=f"With '<=' the index reaches len({name}), which is one past the last element.",
                        )
            cur = ctx.parents.get(cur)
        return None


class KeyErrorFixer(Fixer):
    """Turn ``d["missing"]`` into ``d.get("missing")`` when that exact key raised ``KeyError``."""

    rule = "key-error"
    stage = "runtime"

    def propose(self, ctx: Context) -> list[Fix]:
        run = ctx.run
        if run is None or run.exc_type != "KeyError" or not run.line or run.exc_message is None:
            return []
        matches = [
            s
            for s in _subscripts_on_line(ctx, run.line)
            if isinstance(s.ctx, ast.Load)
            and isinstance(s.slice, ast.Constant)
            and repr(s.slice.value) == run.exc_message
        ]
        if len(matches) != 1:
            return []
        sub = matches[0]
        key = ctx.text(sub.slice)
        return [
            Fix(
                rule=self.rule,
                description=f"Use {sub.value.id}.get({key}) instead of {sub.value.id}[{key}]",
                line=sub.lineno,
                edits=[node_edit(sub, f"{sub.value.id}.get({key})")],
                confidence=0.6,
                reason=(
                    f"The key {key} is not in '{sub.value.id}'. .get() returns None instead of raising. "
                    "If you need a specific fallback, use .get(key, default)."
                ),
            )
        ]


def _is_str_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str":
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_str_expr(node.left) or _is_str_expr(node.right)
    return False


class StrConcatFixer(Fixer):
    """Fix ``"text" + number`` (and ``number + "text"``) by converting the number with ``str()``."""

    rule = "str-concat"
    stage = "runtime"

    _CONCAT = re.compile(r"can only concatenate str \(not \"[\w.]+\"\) to str")
    _OPERAND = re.compile(r"unsupported operand type\(s\) for \+: '([\w.]+)' and '([\w.]+)'")

    def propose(self, ctx: Context) -> list[Fix]:
        run = ctx.run
        if run is None or run.exc_type != "TypeError" or not run.line or not run.exc_message:
            return []
        msg = run.exc_message
        wrap_right = bool(self._CONCAT.search(msg))
        m = self._OPERAND.search(msg)
        wrap_left = bool(m and m.group(2) == "str" and m.group(1) != "str")
        if not (wrap_right or wrap_left):
            return []

        found = []
        for n in ast.walk(ctx.tree):
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add) and n.lineno <= run.line <= n.end_lineno:
                target = None
                if wrap_right and _is_str_expr(n.left) and not _is_str_expr(n.right):
                    target = n.right
                elif wrap_left and _is_str_expr(n.right) and not _is_str_expr(n.left):
                    target = n.left
                if target is not None:
                    found.append((n.end_lineno, n.end_col_offset, target))
        if not found:
            return []
        # Operands are evaluated inner-first / left-first, so the earliest-ending expression fails first.
        target = min(found, key=lambda t: (t[0], t[1]))[2]
        text = ctx.text(target)
        if text is None:
            return []
        return [
            Fix(
                rule=self.rule,
                description=f"Convert {text} to a string with str() before concatenating",
                line=target.lineno,
                edits=[node_edit(target, f"str({text})")],
                confidence=0.85,
                reason=(
                    "Python does not implicitly convert numbers to text when using '+'. "
                    "str() makes the concatenation valid."
                ),
            )
        ]
