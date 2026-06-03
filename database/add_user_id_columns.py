import sqlite3

DB_PATH = "jarvis.db"
OWNER_ID = 1

tables = [
    "transactions",
    "debts",
    "savings",
    "investments",
    "financial_goals",
    "expenses",
]

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

for table in tables:
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        print(f"user_id agregado a {table}")
    except sqlite3.OperationalError as error:
        if "duplicate column name" in str(error):
            print(f"{table} ya tiene user_id")
        else:
            print(f"Error en {table}: {error}")

    cursor.execute(
        f"""
        UPDATE {table}
        SET user_id = ?
        WHERE user_id IS NULL
        """,
        (OWNER_ID,)
    )

    print(f"Datos existentes de {table} asignados al owner")

conn.commit()
conn.close()

print("Migración user_id completada")