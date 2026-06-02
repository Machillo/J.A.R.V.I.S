import sqlite3

conn = sqlite3.connect("jarvis.db")

cursor = conn.cursor()

cursor.execute(
    "ALTER TABLE transactions ADD COLUMN original_amount REAL"
)

cursor.execute(
    "ALTER TABLE transactions ADD COLUMN original_currency TEXT"
)

cursor.execute(
    "ALTER TABLE transactions ADD COLUMN exchange_rate REAL"
)

conn.commit()

print("Columnas agregadas correctamente")

conn.close()