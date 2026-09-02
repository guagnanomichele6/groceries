import sqlite3

DB_NAME = "finance_food.db"

def get_connection():
    """Returns an active connection to the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    # Enable foreign keys enforcement
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn