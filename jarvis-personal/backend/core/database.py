import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


DATABASE_URL = os.getenv("DATABASE_URL")


class DatabaseConfigError(RuntimeError):
    pass


class DatabaseQueryError(RuntimeError):
    pass


def serialize_db_value(value: Any) -> Any:
    """
    Convierte tipos que psycopg2 devuelve desde PostgreSQL a valores seguros
    para FastAPI/JSON y para operaciones normales en el backend.
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
    Wrapper pequeño para mantener esta forma en los servicios:

        conn.execute(...).fetchone()
        conn.execute(...).fetchall()
        cursor.lastrowid
        cursor.rowcount

    La diferencia es que ahora todo es PostgreSQL nativo.
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
                "DATABASE_URL no está configurada. J.A.R.V.I.S debe usar PostgreSQL/Supabase como única base de datos."
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

    def _validate_postgres_query(self, query: str) -> str:
        prepared = query.strip()

        blocked_fragments = [
            "datetime('now')",
            'datetime("now")',
            "INSERT OR IGNORE",
            "AUTOINCREMENT",
        ]

        upper_query = prepared.upper()
        for fragment in blocked_fragments:
            if fragment.upper() in upper_query:
                raise DatabaseQueryError(
                    f"SQL incompatible con PostgreSQL detectado: {fragment}. "
                    "Actualiza ese query a sintaxis PostgreSQL nativa."
                )

        if "?" in prepared:
            raise DatabaseQueryError(
                "Placeholder SQLite '?' detectado. Usa placeholders PostgreSQL/psycopg2: %s."
            )

        clean = prepared.lower()
        if clean.startswith("insert") and " returning " not in clean:
            prepared = prepared.rstrip(";") + " RETURNING id"

        return prepared

    def execute(self, query: str, params=()):
        prepared_query = self._validate_postgres_query(query)

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
    En producción el schema se ejecuta desde Supabase SQL Editor usando database/schema.sql.
    Esta función queda para que main.py pueda llamarla sin crear tablas automáticamente.
    """
    if not DATABASE_URL:
        raise DatabaseConfigError(
            "DATABASE_URL no está configurada. Configúrala en Render antes de iniciar el backend."
        )
    return None
