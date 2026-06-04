import os
import sqlite3
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = BASE_DIR / "database" / "jarvis.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

DATABASE_URL = os.getenv("DATABASE_URL")


class PostgresCursorResult:
    def __init__(self, rows=None, lastrowid=None, rowcount=0):
        self.rows = rows or []
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class PostgresConnection:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.conn.rollback()
        self.conn.close()

    def _prepare_query(self, query: str):
        query = query.replace("datetime('now')", "NOW()")
        query = query.replace("?", "%s")

        clean = query.strip().lower()

        if clean.startswith("insert") and "returning" not in clean:
            query = query.rstrip().rstrip(";") + " RETURNING id"

        return query

    def execute(self, query: str, params=()):
        query = self._prepare_query(query)

        with self.conn.cursor() as cursor:
            cursor.execute(query, params)

            rows = []
            lastrowid = None

            if cursor.description:
                rows = cursor.fetchall()

                if rows and "id" in rows[0]:
                    lastrowid = rows[0]["id"]

            return PostgresCursorResult(
                rows=rows,
                lastrowid=lastrowid,
                rowcount=cursor.rowcount
            )

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()


def get_connection():
    if DATABASE_URL:
        return PostgresConnection()

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    if DATABASE_URL:
        # En producción, Supabase/Postgres ya tiene el schema creado desde SQL Editor.
        return

    with get_connection() as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())

        user_exists = conn.execute("SELECT id FROM users LIMIT 1").fetchone()

        if not user_exists:
            conn.execute(
                """
                INSERT INTO users (name, country, timezone, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                ("Kenneth", "Costa Rica", "America/Costa_Rica")
            )

        default_settings = {
            "currency": "CRC",
            "language": "es",
            "timezone": "America/Costa_Rica"
        }

        for key, value in default_settings.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value)
                VALUES (?, ?)
                """,
                (key, value)
            )

        conn.commit()