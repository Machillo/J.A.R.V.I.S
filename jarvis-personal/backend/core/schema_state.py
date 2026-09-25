"""Read-only checks of whether versioned migrations have created a relation.

Request paths never create or alter schema: DDL takes relation-level locks on
every call and concurrent requests deadlock (see product_ops.ensure_schema).
Schema belongs in database/migrations. A path whose tables may not exist yet
asks here and degrades explicitly instead of creating them.
"""
from __future__ import annotations

from typing import Iterable


def missing_tables(conn, tables: Iterable[str]) -> list[str]:
    names = list(tables)
    if not names:
        return []
    row = conn.execute(
        "SELECT array_agg(t ORDER BY t) AS missing FROM unnest(%s::text[]) AS t "
        "WHERE to_regclass('public.' || t) IS NULL",
        (names,),
    ).fetchone() or {}
    return list(row.get("missing") or [])


def tables_exist(conn, tables: Iterable[str]) -> bool:
    return not missing_tables(conn, tables)
