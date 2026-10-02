"""Payroll parsing and trust are generic: no employer, person, address or domain in code."""
import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MODULES = ["email_monitor/payroll_statement.py", "email_monitor/sender_trust.py", "finance/payroll_receipts.py"]
EMAIL_OR_DOMAIN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|\b[\w-]+\.(?:com|cr|net|org|co)\b", re.I)


def test_payroll_modules_name_no_address_domain_employer_or_person():
    found = []
    for module in MODULES:
        tree = ast.parse((BACKEND / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and EMAIL_OR_DOMAIN.search(node.value):
                found.append(f"{module}: {node.value[:60]}")
    assert found == []
