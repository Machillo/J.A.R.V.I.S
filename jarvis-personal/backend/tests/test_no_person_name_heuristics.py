"""Shared and Owner runtime code never decides money by a person's name.

Who owes, who paid and which card is the holder's come from workspace data (receivables,
card_aliases.is_primary), never from names written in code. This guard fails on SQL that
compares an owner/person/payer column with a quoted literal, and on code that branches on
a quoted lowercase name inside the receivable/additional-card modules.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SQL_NAME_LITERAL = re.compile(r"(owner_label|person_name|card_owner|payer)[^=\n]{0,20}?(?:=|\bNOT\s+IN\b|\bIN\b)\s*\(?\s*'[a-záéíóúñ]", re.I)
MODULES = ["finance/intelligence.py", "finance/receivable_semantics.py", "email_monitor/service.py", "ai/strategy_dashboard.py"]
NAME_BRANCH = re.compile(r"""["'][a-záéíóúñ]{3,}["']\s+in\s+(text|clean|lowered|value)\b""")


def test_no_sql_compares_a_person_column_with_a_written_name():
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SQL_NAME_LITERAL.search(line):
                offenders.append(f"{path.relative_to(BACKEND)}:{number}")
    assert offenders == []


def test_receivable_and_card_modules_do_not_branch_on_names():
    offenders = []
    for module in MODULES:
        for number, line in enumerate((BACKEND / module).read_text(encoding="utf-8").splitlines(), 1):
            match = NAME_BRANCH.search(line)
            if match and not any(word in match.group(0) for word in ("sinpe", "pago", "abono")):
                offenders.append(f"{module}:{number}: {line.strip()[:80]}")
    assert offenders == []
