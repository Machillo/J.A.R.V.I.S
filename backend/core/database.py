import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = BASE_DIR / "database" / "jarvis.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
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