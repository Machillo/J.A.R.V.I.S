"""A debt payment is bound to its idempotency key in the same transaction (CLAUDE.md, data integrity)."""
import ast
from pathlib import Path

SOURCE = Path(__file__).with_name("service.py").read_text(encoding="utf-8")


def test_every_commit_of_a_debt_payment_marks_the_operation_first():
    function = next(node for node in ast.walk(ast.parse(SOURCE))
                    if isinstance(node, ast.FunctionDef) and node.name == "apply_monthly_payment_to_debt")
    lines = SOURCE.splitlines()
    commits = [node.lineno for node in ast.walk(function)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "commit"]
    assert commits
    for line in commits:
        assert lines[line - 2].strip().startswith("mark_applied(conn)"), f"line {line}"
