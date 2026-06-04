import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


DATABASE_URL = os.getenv("DATABASE_URL")


class DatabaseConfigError(RuntimeError):
    pass


def serialize_db_value(value: Any) -> Any:
    """
    Convierte valores que PostgreSQL/psycopg2 devuelve y que FastAPI/JSON
    o cálculos con float no manejan bien directamente.
    """
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, list):
        return [serialize_db_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(serialize_db_value(item) for item in value)

    if isinstance(value, dict):
        return {key: serialize_db_value(item) for key, item in value.items()}

    return value


def serialize_row(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    return serialize_db_value(dict(row))


def serialize_rows(rows: Iterable[dict]) -> list[dict]:
    return [serialize_row(row) for row in rows]


class PostgresCursorResult:
    """
    Pequeño wrapper para mantener compatibilidad con el código actual:
    conn.execute(...).fetchone()
    conn.execute(...).fetchall()
    cursor.lastrowid
    cursor.rowcount
    """

    def __init__(self, rows=None, lastrowid=None, rowcount: int = 0):
        self.rows = rows or []
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class PostgresConnection:
    def __init__(self):
        if not DATABASE_URL:
            raise DatabaseConfigError(
                "DATABASE_URL no está configurada. J.A.R.V.I.S ahora debe usar PostgreSQL como única base de datos."
            )

        self.conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.conn.rollback()
        self.conn.close()

    def _prepare_query(self, query: str) -> str:
        """
        Adaptador temporal y global para que el código actual siga funcionando
        mientras se refactorizan los servicios a SQL PostgreSQL nativo.

        Importante:
        - Esto elimina SQLite como base de datos.
        - No abre ni lee jarvis.db.
        - Solo traduce sintaxis vieja usada por el código actual.
        """
        prepared = query.strip()

        prepared = prepared.replace("datetime('now')", "NOW()")
        prepared = prepared.replace('datetime("now")', "NOW()")

        # SQLite: INSERT OR IGNORE INTO tabla (...) VALUES (...)
        # PostgreSQL: INSERT INTO tabla (...) VALUES (...) ON CONFLICT DO NOTHING
        prepared = re.sub(
            r"INSERT\s+OR\s+IGNORE\s+INTO",
            "INSERT INTO",
            prepared,
            flags=re.IGNORECASE,
        )

        if re.search(r"INSERT\s+INTO", prepared, re.IGNORECASE) and "OR IGNORE" not in prepared.upper():
            if "ON CONFLICT" not in prepared.upper() and "settings" in prepared.lower():
                prepared = prepared.rstrip(";") + " ON CONFLICT (key) DO NOTHING"

        # El código viejo usa ? como placeholder. psycopg2 usa %s.
        prepared = prepared.replace("?", "%s")

        clean = prepared.strip().lower()

        # Para conservar cursor.lastrowid en inserts.
        if clean.startswith("insert") and " returning " not in clean:
            prepared = prepared.rstrip(";") + " RETURNING id"

        return prepared

    def execute(self, query: str, params=()):
        prepared_query = self._prepare_query(query)

        with self.conn.cursor() as cursor:
            cursor.execute(prepared_query, params)

            rows = []
            lastrowid = None

            if cursor.description:
                rows = serialize_rows(cursor.fetchall())
                if rows and isinstance(rows[0], dict) and "id" in rows[0]:
                    lastrowid = rows[0]["id"]

            return PostgresCursorResult(
                rows=rows,
                lastrowid=lastrowid,
                rowcount=cursor.rowcount,
            )

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def get_connection():
    return PostgresConnection()


def init_database():
    """
    En producción el schema se crea desde Supabase SQL Editor usando database/schema.sql.
    Esta función queda para que main.py pueda llamarla sin romper el arranque.
    """
    if not DATABASE_URL:
        raise DatabaseConfigError(
            "DATABASE_URL no está configurada. Configúrala en Render antes de iniciar el backend."
        )
    return None
