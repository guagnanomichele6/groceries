import sqlite3
import pandas as pd

DB_NAME = "finance_food.db"

def init_db():
    """Crea le tabelle del database se non esistono già."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Tabella dei Conti (Patrimonio)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL, -- es. Contante, Conto Corrente, Investimento
            balance REAL NOT NULL
        )
    ''')
    
    # 2. Tabella della Dispensa (Alimentazione)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pantry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL, -- es. grammi, litri, pezzi
            calories_per_100g REAL,
            protein_per_100g REAL
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database SQLite inizializzato con successo!")