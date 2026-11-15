"""Deterministic static analysis: facts the agents can rely on.

Everything here only *parses* code (``ast`` + pyflakes). Nothing is executed,
so it is safe on untrusted input. The results are given to the agents as
verified facts, which lets a small model (e.g. Haiku) start from evidence
instead of guessing, and lets the orchestrator reject malformed outputs
without paying for an LLM judgement.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from typing import Any

import pyflakes.checker

SQL_WORDS = ("select ", "insert ", "update ", "delete ", " where ")
RESOURCE_CALLS = {"open", "connect", "urlopen", "socket"}


@dataclass
class Finding:
    rule: str
    severity: str  # low | medium | high | critical
    line: int
    message: str


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _string_parts(node: ast.AST) -> str:
    """Literal text inside an expression built from strings (for SQL detection)."""
    texts = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return " ".join(texts).lower()


def _is_dynamic_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return True
    if isinstance(node, ast.Call) and _call_name(node) == "format":
        return True
    return False


def _len_target(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Name):
        return node.args[0].id
    return None


def _emptiness_guards(fn: ast.AST) -> set[str]:
    """Names tested for emptiness by an `if` that raises or returns (``if not x:``, ``if len(x) == 0:``)."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or not any(isinstance(s, (ast.Raise, ast.Return)) for s in node.body):
            continue
        test = node.test
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and isinstance(test.operand, ast.Name):
            names.add(test.operand.id)
        elif isinstance(test, ast.Compare) and _call_name(test.left) == "len" and _len_target(test.left):
            names.add(_len_target(test.left))  # type: ignore[arg-type]
    return names


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self._with_depth = 0
        self._guarded: list[set[str]] = [set()]  # names checked for emptiness, per function

    def add(self, rule: str, severity: str, node: ast.AST, message: str) -> None:
        self.findings.append(Finding(rule, severity, getattr(node, "lineno", 0), message))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for default in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.add("mutable-default", "low", default,
                         f"Mutable default argument in {node.name}(): shared between calls; use None.")
        self._guarded.append(_emptiness_guards(node))
        self.generic_visit(node)
        self._guarded.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.add("bare-except", "high", node, "Bare `except:` catches everything and hides real errors.")
        elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
            if all(isinstance(s, (ast.Pass, ast.Continue)) for s in node.body):
                self.add("swallowed-exception", "medium", node, f"`except {node.type.id}` silently ignored.")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if (isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and _call_name(node.right) == "len"
                and not _len_target(node.right) in self._guarded[-1]):
            self.add("division-by-len", "high", node,
                     "Division by len(...): raises ZeroDivisionError when the collection is empty.")
        if _is_dynamic_string(node) and any(w in _string_parts(node) for w in SQL_WORDS):
            self.add("sql-injection", "critical", node,
                     "SQL query built by string formatting: use parameter placeholders (?).")
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        if _is_dynamic_string(node) and any(w in _string_parts(node) for w in SQL_WORDS):
            self.add("sql-injection", "critical", node,
                     "SQL query built with an f-string: use parameter placeholders (?).")
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._with_depth += 1
        for item in node.items:
            self.visit(item.context_expr)
        self._with_depth -= 1
        for stmt in node.body:
            self.visit(stmt)

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call) and _call_name(node.value) in RESOURCE_CALLS and not self._with_depth:
            self.add("resource-leak", "high", node,
                     f"{_call_name(node.value)}() result is not managed by `with`: may never be closed.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name in {"eval", "exec"}:
            self.add("dangerous-call", "critical", node, f"{name}() executes arbitrary code.")
        if name == "execute" and node.args and _is_dynamic_string(node.args[0]):
            self.add("sql-injection", "critical", node, "execute() called with a formatted string.")
        self.generic_visit(node)


def _functions(tree: ast.Module) -> list[dict[str, Any]]:
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            out.append({
                "name": node.name,
                "line": node.lineno,
                "args": args,
                "has_docstring": ast.get_docstring(node) is not None,
                "has_type_hints": node.returns is not None or any(a.annotation for a in node.args.args),
            })
    return out


def analyze(code: str) -> dict[str, Any]:
    """Parse-only analysis of ``code``. Never executes it."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"syntax_ok": False, "syntax_error": f"line {exc.lineno}: {exc.msg}", "findings": [],
                "functions": []}
    visitor = _Visitor()
    visitor.visit(tree)
    for msg in pyflakes.checker.Checker(tree, "solution.py").messages:
        visitor.findings.append(Finding("pyflakes", "medium" if "undefined" in str(msg.message) else "low",
                                        msg.lineno, msg.message % msg.message_args))
    seen: set[tuple[str, int]] = set()
    findings = []
    for f in sorted(visitor.findings, key=lambda f: f.line):
        if (f.rule, f.line) not in seen:
            seen.add((f.rule, f.line))
            findings.append(asdict(f))
    return {"syntax_ok": True, "syntax_error": None, "findings": findings, "functions": _functions(tree)}


def format_for_prompt(report: dict[str, Any]) -> str:
    if not report.get("syntax_ok"):
        return f"SYNTAX ERROR ({report['syntax_error']}): the code does not parse."
    lines = []
    for fn in report["functions"]:
        flags = [] if fn["has_docstring"] else ["no docstring"]
        if not fn["has_type_hints"]:
            flags.append("no type hints")
        lines.append(f"- function {fn['name']}({', '.join(fn['args'])}) at line {fn['line']}"
                     + (f" [{', '.join(flags)}]" if flags else ""))
    if report["findings"]:
        lines.append("Findings:")
        lines += [f"- [{f['severity']}] line {f['line']} ({f['rule']}): {f['message']}" for f in report["findings"]]
    else:
        lines.append("Findings: none detected by the static checks.")
    return "\n".join(lines)


def public_names(code: str) -> set[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    return {n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith("_")}


def collect_test_names(code: str) -> set[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")}
