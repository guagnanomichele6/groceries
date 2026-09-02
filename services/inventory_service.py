from database.connection import get_connection

def get_available_units():
    """Retrieves all available measurement units from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT unit_name FROM global_units ORDER BY unit_name")
    units = [row[0] for row in cursor.fetchall()]
    conn.close()
    return units if units else ["grammi", "kg", "ml", "litri", "pezzi", "bustine"]

def convert_qty(qty, from_unit, to_unit):
    """Converts quantity between compatible units based on multipliers."""
    f_u = from_unit.lower()
    t_u = to_unit.lower()
    if f_u == t_u:
        return qty
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT to_base_multiplier FROM global_units WHERE unit_name = ?", (f_u,))
    res_from = cursor.fetchone()
    cursor.execute("SELECT to_base_multiplier FROM global_units WHERE unit_name = ?", (t_u,))
    res_to = cursor.fetchone()
    conn.close()
    
    if res_from and res_to:
        base_qty = qty * res_from[0]
        return base_qty / res_to[0]
        
    if f_u == 'kg' and t_u == 'grammi': return qty * 1000.0
    if f_u == 'grammi' and t_u == 'kg': return qty / 1000.0
    if f_u == 'litri' and t_u == 'ml': return qty * 1000.0
    if f_u == 'ml' and t_u == 'litri': return qty / 1000.0
    return qty

def consume_inventory_item(cursor, item_name, qty_needed, recipe_unit):
    """Consumes an item from inventory, handles zero stock by moving it to the shopping list."""
    cleaned_name = item_name.strip().capitalize()
    cursor.execute("SELECT id, quantity, unit, category FROM inventory WHERE item_name = ?", (cleaned_name,))
    item = cursor.fetchone()
    if item:
        inv_id, inv_qty, inv_unit, inv_cat = item
        conv_qty = convert_qty(qty_needed, recipe_unit, inv_unit)
        new_qty = inv_qty - conv_qty
        
        if new_qty <= 0:
            cursor.execute("DELETE FROM inventory WHERE id = ?", (inv_id,))
            cat_to_use = inv_cat if inv_cat else "Spesa"
            cursor.execute("""
                INSERT INTO shopping_list (item_name, quantity, unit, category, checked)
                SELECT ?, 1.0, ?, ?, 0
                WHERE NOT EXISTS (SELECT 1 FROM shopping_list WHERE item_name = ?)
            """, (cleaned_name, inv_unit, cat_to_use, cleaned_name))
        else:
            cursor.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_qty, inv_id))

def add_or_update_inventory(cursor, item_name, qty, unit, category="Spesa"):
    """Adds or updates an inventory item, converting units if it already exists."""
    cleaned_name = item_name.strip().capitalize()
    cursor.execute("SELECT id, quantity, unit FROM inventory WHERE item_name = ?", (cleaned_name,))
    existing = cursor.fetchone()
    
    if existing:
        inv_id, inv_qty, inv_unit = existing
        try:
            converted_incoming_qty = convert_qty(qty, unit, inv_unit)
            new_total = inv_qty + converted_incoming_qty
            cursor.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_total, inv_id))
        except Exception:
            cursor.execute("INSERT INTO inventory (item_name, category, quantity, unit) VALUES (?, ?, ?, ?)", 
                           (cleaned_name, category, qty, unit))
    else:
        cursor.execute("INSERT INTO inventory (item_name, category, quantity, unit) VALUES (?, ?, ?, ?)", 
                       (cleaned_name, category, qty, unit))