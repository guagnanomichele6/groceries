import os
import sqlite3

# Imposta percorso assoluto garantito
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "finance_food.db")


def init_db():
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()

  # 1. Tabella Conti
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            balance REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR'
        )
    """)

  # 2. Tabella Dispensa
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS pantry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL UNIQUE,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL
        )
    """)

  # 3. Tabella Transazioni
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            account_id INTEGER,
            total_amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR',
            description TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    """)

  # 4. Tabella Dettaglio Articoli per Transazione (permette il rollback automatico)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaction_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions (id) ON DELETE CASCADE
        )
    """)

  # Migrazione sicura se mancano colonne nei vecchi file
  try:
    cursor.execute(
        "ALTER TABLE accounts ADD COLUMN currency TEXT NOT NULL DEFAULT 'EUR'"
    )
  except sqlite3.OperationalError:
    pass

  try:
    cursor.execute(
        "ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT"
        " 'EUR'"
    )
  except sqlite3.OperationalError:
    pass

  conn.commit()
  conn.close()


if __name__ == "__main__":
  init_db()
  print("Database pronto e allineato con tracciamento articoli spesa!")