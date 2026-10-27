#!/usr/bin/env python3
"""Check the response of POST /financial-history/cron (.github/workflows/financial-history.yml).

Prints only counts, the date, the status and error classes (never amounts, names or ids) and
exits 1 when the run reports a failure: a workspace that failed (`failed`) or the Owner's debt
installments that could not be applied (`installments_failed`). The installment step commits
once at its end, so a failed run leaves nothing half-applied and a rerun is safe.

Usage: financial_history_result.py body.json
"""
from __future__ import annotations

import json
import re
import sys

REPORTED = ("status", "date", "eligible", "recorded", "strategy_changed", "failed",
            "debt_installments", "installments_failed", "installments_errors")
ERROR_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,59}$")


def _count(data: dict, key: str) -> int:
    value = data.get(key)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 1  # an unreadable count is a failure, never a silent zero
    try:
        return max(int(value), 0)
    except ValueError:
        return 1


def evaluate(data: dict) -> tuple[list[str], int]:
    """The log lines and the exit code for one response body."""
    errors = [str(item) for item in data.get("installments_errors") or [] if ERROR_CLASS.match(str(item))]
    summary = {key: data.get(key) for key in REPORTED if key != "installments_errors"}
    summary["installments_errors"] = errors
    lines = [str(summary)]
    code = 0
    if data.get("status") != "OK":
        lines.append(f"::error::Unexpected status {str(data.get('status'))[:40]!r}.")
        code = 1
    failed = _count(data, "failed")
    if failed:
        lines.append(f"::error::{failed} workspace(s) failed; see the backend logs (error class only).")
        code = 1
    if "installments_failed" not in data:
        lines.append("::warning::The backend did not report the Owner's debt installments (it predates that step).")
    else:
        installments_failed = _count(data, "installments_failed")
        if installments_failed:
            classes = ", ".join(errors) or "unknown"
            lines.append(f"::error::The Owner's debt installments failed ({classes}); nothing was half-applied, "
                         "rerun the workflow after fixing the cause.")
            code = 1
    return lines, code


def main(argv: list[str]) -> int:
    try:
        with open(argv[1], encoding="utf-8") as handle:
            data = json.load(handle)
    except (IndexError, OSError, ValueError):
        print("::error::The financial-history response is not readable JSON.")
        return 1
    if not isinstance(data, dict):
        print("::error::The financial-history response is not a JSON object.")
        return 1
    lines, code = evaluate(data)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
