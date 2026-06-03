import sqlite3

conn = sqlite3.connect("jarvis.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS allowed_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
)
""")

conn.commit()

print("Tabla allowed_users creada correctamente")

conn.close()