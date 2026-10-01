"""Small, well-tested helpers for working with Python ASTs."""

from __future__ import annotations

import ast
import builtins
from typing import Optional

FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_MUTABLE_NODES = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
_MUTABLE_CALLS = {"list", "dict", "set"}


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def enclosing(node: ast.AST, parents: dict, types: tuple) -> Optional[ast.AST]:
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, types):
            return cur
        cur = parents.get(cur)
    return None


def enclosing_statement(node: ast.AST, parents: dict) -> Optional[ast.stmt]:
    cur: Optional[ast.AST] = node
    while cur is not None and not isinstance(cur, ast.stmt):
        cur = parents.get(cur)
    return cur  # type: ignore[return-value]


def is_pure(node: ast.AST) -> bool:
    """True if evaluating ``node`` can have no side effects (so it is safe to delete)."""
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(is_pure(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and is_pure(k) and is_pure(v) for k, v in zip(node.keys, node.values))
    if isinstance(node, ast.UnaryOp):
        return is_pure(node.operand)
    return False


def is_zero_constant(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value == 0
    )


def is_mutable_default(node: ast.AST) -> bool:
    if isinstance(node, _MUTABLE_NODES):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _MUTABLE_CALLS
        and not node.args
        and not node.keywords
    )


def mutable_defaults(func: ast.AST) -> list[tuple[ast.arg, ast.expr]]:
    """Return (argument, default) pairs whose default value is a mutable object."""
    a = func.args  # type: ignore[attr-defined]
    positional = a.posonlyargs + a.args
    pairs = list(zip(positional[len(positional) - len(a.defaults):], a.defaults))
    pairs += [(arg, d) for arg, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None]
    return [(arg, d) for arg, d in pairs if is_mutable_default(d)]


def param_names(func: ast.AST) -> list[str]:
    """Ordinary parameter names (excluding self/cls)."""
    a = func.args  # type: ignore[attr-defined]
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    return [n for n in names if n not in ("self", "cls")]


def bound_names(tree: ast.AST) -> set[str]:
    """Every name that is bound somewhere in the module (plus builtins)."""
    names = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (*FUNC_TYPES, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def callable_names(tree: ast.AST) -> set[str]:
    """Names that plausibly refer to something callable."""
    names = {n for n in dir(builtins) if callable(getattr(builtins, n))}
    for node in ast.walk(tree):
        if isinstance(node, (*FUNC_TYPES, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names
