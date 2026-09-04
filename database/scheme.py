import sqlite3
from database.connection import get_connection

def initialize_database():
    """Initializes the database schema by creating all required tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # --- 1. FINANCE MODULE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            balance REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            account_id INTEGER,
            total_amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR',
            category TEXT NOT NULL DEFAULT 'Spesa',
            description TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transaction_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions (id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            account_id INTEGER,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR',
            frequency TEXT NOT NULL DEFAULT 'Mensile',
            interval_value TEXT NOT NULL DEFAULT '1',
            category TEXT NOT NULL DEFAULT 'Bollette',
            op_type TEXT NOT NULL DEFAULT 'Spesa',
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    ''')
    
    # Migrazione per vecchi database che usano day_of_month
    try:
        cursor.execute("ALTER TABLE recurring_expenses ADD COLUMN interval_value TEXT NOT NULL DEFAULT '1'")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    # --- 2. POSSESSIONS & INVENTORY MODULE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Dispensa',
            quantity REAL NOT NULL,
            unit TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shopping_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Dispensa',
            checked INTEGER NOT NULL DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS global_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_name TEXT UNIQUE NOT NULL,
            unit_type TEXT NOT NULL,
            to_base_multiplier REAL NOT NULL DEFAULT 1.0
        )
    ''')
    
    default_units = [
        ('grammi', 'peso', 1.0),
        ('kg', 'peso', 1000.0),
        ('ml', 'volume', 1.0),
        ('litri', 'volume', 1000.0),
        ('pezzi', 'pezzo', 1.0),
        ('bustine', 'pezzo', 1.0),
        ('cucchiai', 'altro', 1.0),
        ('confezioni', 'pezzo', 1.0)
    ]
    cursor.executemany('''
        INSERT OR IGNORE INTO global_units (unit_name, unit_type, to_base_multiplier)
        VALUES (?, ?, ?)
    ''', default_units)
    
    # --- 3. MEALS & KITCHEN MODULE ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meal_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_id INTEGER,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            FOREIGN KEY (meal_id) REFERENCES meals (id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calendar_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            slot TEXT NOT NULL,
            meal_id INTEGER,
            context TEXT NOT NULL DEFAULT 'A Casa (Canonico)',
            consumed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (meal_id) REFERENCES meals (id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'ETF',
            account_name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0.0,
            current_value REAL NOT NULL DEFAULT 0.0,
            currency TEXT NOT NULL DEFAULT 'EUR'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calendar_slot_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            FOREIGN KEY (schedule_id) REFERENCES calendar_schedule (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    initialize_database()
    print("Database successfully initialized via scheme.py!")