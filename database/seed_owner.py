import sqlite3
from datetime import datetime

conn = sqlite3.connect("jarvis.db")
cursor = conn.cursor()

cursor.execute("""
INSERT OR IGNORE INTO allowed_users
(email, role, status, created_at)
VALUES (?, ?, ?, ?)
""", (
    "gatotico99@gmail.com",
    "owner",
    "active",
    datetime.now().isoformat()
))

conn.commit()

print("Owner agregado")

conn.close()