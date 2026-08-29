import streamlit as st
import sqlite3
import pandas as pd
import requests
import shutil
import os
from datetime import date, timedelta, datetime
import json

DB_NAME = "finance_food.db"

st.set_page_config(page_title="Personal ERP", page_icon="📊", layout="wide")

@st.cache_data(ttl=3600)
def get_exchange_rate(base="EUR", target="JPY"):
    try:
        url = f"https://api.frankfurter.app/latest?from={base}&to={target}"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            return response.json()["rates"][target]
    except Exception:
        pass
    return 160.0

eur_to_jpy = get_exchange_rate("EUR", "JPY")
jpy_to_eur = 1.0 / eur_to_jpy

# --- SISTEMA DI BACKUP AUTOMATICO ---
def create_database_backup():
    if not os.path.exists("backups"):
        os.makedirs("backups")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"backups/finance_food_backup_{timestamp}.db"
    shutil.copy(DB_NAME, backup_filename)
    return backup_filename

# --- FUNZIONI UTILI UNITÀ E INVENTARIO ---
def get_available_units():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT unit_name FROM global_units ORDER BY unit_name")
    units = [row[0] for row in cursor.fetchall()]
    conn.close()
    return units if units else ["grammi", "kg", "ml", "litri", "pezzi", "bustine"]

def convert_qty(qty, from_unit, to_unit):
    f_u = from_unit.lower()
    t_u = to_unit.lower()
    if f_u == t_u:
        return qty
    
    conn = sqlite3.connect(DB_NAME)
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

def add_or_update_inventory(cursor, item_name, qty, unit, category="Dispensa"):
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

def process_past_slots():
    today_str = str(date.today())
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, meal_id, context FROM calendar_schedule WHERE date < ? AND consumed = 0", (today_str,))
    past_items = cursor.fetchall()
    
    for sid, m_id, context in past_items:
        if m_id and context in ['A Casa (Canonico)', 'Offerto da Me']:
            cursor.execute("SELECT item_name, quantity, unit FROM meal_ingredients WHERE meal_id = ?", (m_id,))
            ingredients = cursor.fetchall()
            for item_name, qty, recipe_unit in ingredients:
                cursor.execute("SELECT id, quantity, unit FROM inventory WHERE item_name = ?", (item_name,))
                p = cursor.fetchone()
                if p:
                    p_id, p_qty, p_unit = p
                    conv_qty = convert_qty(qty, recipe_unit, p_unit)
                    new_q = p_qty - conv_qty
                    if new_q <= 0:
                        cursor.execute("DELETE FROM inventory WHERE id = ?", (p_id,))
                    else:
                        cursor.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_q, p_id))
        cursor.execute("UPDATE calendar_schedule SET consumed = 1 WHERE id = ?", (sid,))
    conn.commit()
    conn.close()

process_past_slots()

# --- MOTORE DELL'ASSISTENTE IA CON OLLAMA ---
def parse_natural_language_schedule(text_input):
    today_str = str(date.today())
    system_prompt = f"""
    Sei un assistente di un ERP personale. Oggi è {today_str}. 
    Analizza il testo inserito dall'utente e restituisci ESCLUSIVAMENTE un oggetto JSON valido, senza aggiungere altro testo o markdown, con questa struttura esatta:
    {{
      "events": [
        {{
          "date": "YYYY-MM-DD",
          "slot": "Pranzo" o "Cena" o "Colazione",
          "meal_name": "Nome del piatto o null se non specificato",
          "context": "A Casa (Canonico)" o "Fuori Casa" o "A Casa di Altri" o "Offerto da Me"
        }}
      ]
    }}
    Riconosci i giorni relativi basandoti su oggi ({today_str}). Se il pasto è al ristorante o fuori, imposta context a 'Fuori Casa'. Se è a casa d'altri, 'A Casa di Altri'.
    Testo dell'utente: "{text_input}"
    """
    
    payload = {
        "model": "llama3",
        "prompt": system_prompt,
        "format": "json",
        "stream": False
    }
    
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=30)
        if response.status_code == 200:
            result_json_str = response.json().get("response", "{}")
            data = json.loads(result_json_str)
            return data.get("events", [])
        else:
            st.error(f"Errore di comunicazione con Ollama (Codice {response.status_code})")
            return []
    except requests.exceptions.ConnectionError:
        st.error("Impossibile connettersi a Ollama. Assicurati che Ollama sia attivo in background sul tuo computer.")
        return []
    except Exception as e:
        st.error(f"Errore imprevisto durante il parsing IA: {e}")
        return []

def apply_ai_schedule_to_db(events):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    added_count = 0
    for ev in events:
        ev_date = ev.get("date")
        ev_slot = ev.get("slot", "Pranzo")
        ev_meal = ev.get("meal_name")
        ev_context = ev.get("context", "A Casa (Canonico)")
        
        meal_id = None
        if ev_meal and str(ev_meal).strip().lower() != "null":
            cleaned_meal_name = str(ev_meal).strip().capitalize()
            cursor.execute("SELECT id FROM meals WHERE name = ?", (cleaned_meal_name,))
            res_m = cursor.fetchone()
            if res_m:
                meal_id = res_m[0]
            else:
                cursor.execute("INSERT INTO meals (name) VALUES (?)", (cleaned_meal_name,))
                meal_id = cursor.lastrowid
                
        cursor.execute("""
            INSERT INTO calendar_schedule (date, slot, meal_id, context, consumed) 
            VALUES (?, ?, ?, ?, 0)
        """, (ev_date, ev_slot, meal_id, ev_context))
        added_count += 1
        
    conn.commit()
    conn.close()
    return added_count


st.title("Personal ERP")
st.caption(f"💱 Tasso di cambio live: 1 € = {eur_to_jpy:.2f} ¥")

tab_finanza, tab_possedimenti, tab_pasti, tab_impostazioni = st.tabs([
    "💰 Finanza", 
    "📦 Possedimenti", 
    "🍳 Pasti", 
    "⚙️ Impostazioni"
])

# ==========================================
# 1. AREA FINANZA
# ==========================================
with tab_finanza:
    st.header("Gestione Finanziaria")
    sub_f1, sub_f2, sub_f3 = st.tabs(["Depositi & Conti", "Registra Spesa / Entrata", "Storico Transazioni"])
    
    with sub_f1:
        st.subheader("I tuoi Conti e Depositi")
        conn = sqlite3.connect(DB_NAME)
        df_accounts = pd.read_sql("SELECT id, name AS 'Conto', type AS 'Tipo', balance AS 'Saldo', currency AS 'Valuta' FROM accounts", conn)
        conn.close()
        
        if not df_accounts.empty:
            total_eur = sum(row['Saldo'] * jpy_to_eur if row['Valuta'] == 'JPY' else row['Saldo'] for _, row in df_accounts.iterrows())
            st.metric(label="Patrimonio Totale Stimato", value=f"€ {total_eur:,.2f}")
            st.divider()
            
            edited_acc = st.data_editor(df_accounts, use_container_width=True, hide_index=True)
            if st.button("💾 Salva Modifiche Conti"):
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM accounts")
                for _, row in edited_acc.iterrows():
                    if pd.notna(row['Conto']) and str(row['Conto']).strip() != "":
                        cursor.execute("INSERT INTO accounts (id, name, type, balance, currency) VALUES (?, ?, ?, ?, ?)",
                                       (int(row['id']) if pd.notna(row['id']) else None, str(row['Conto']).strip(), str(row['Tipo']), float(row['Saldo']), str(row['Valuta'])))
                conn.commit()
                conn.close()
                st.success("Conti aggiornati.")
                st.rerun()
        else:
            st.info("Nessun conto registrato.")
            
        with st.form("add_acc"):
            st.markdown("**Aggiungi Nuovo Conto**")
            ac_name = st.text_input("Nome Conto (es. Portafoglio, Banca)")
            ac_type = st.selectbox("Tipo", ["Conto Corrente", "Contante", "Investimenti"])
            ac_curr = st.selectbox("Valuta", ["EUR", "JPY"])
            ac_bal = st.number_input("Saldo Iniziale", value=0.0, step=100.0)
            if st.form_submit_button("➕ Crea Conto") and ac_name:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO accounts (name, type, balance, currency) VALUES (?, ?, ?, ?)", (ac_name, ac_type, ac_bal, ac_curr))
                conn.commit()
                conn.close()
                st.success("Conto aggiunto!")
                st.rerun()

    with sub_f2:
        st.subheader("Registra Transazione Generica")
        conn = sqlite3.connect(DB_NAME)
        df_accs = pd.read_sql("SELECT id, name, currency FROM accounts", conn)
        conn.close()
        
        if df_accs.empty:
            st.warning("Crea prima un conto nella sezione Depositi.")
        else:
            acc_dict = {row['name']: {'id': row['id'], 'currency': row['currency']} for _, row in df_accs.iterrows()}
            with st.form("trans_form"):
                col_t1, col_t2 = st.columns(2)
                with col_t1: t_date = st.date_input("Data", value=date.today())
                with col_t2: sel_acc = st.selectbox("Conto di pagamento", list(acc_dict.keys()))
                
                default_curr = acc_dict[sel_acc]['currency']
                acc_id = acc_dict[sel_acc]['id']
                
                col_curr1, col_curr2 = st.columns(2)
                with col_curr1: t_desc = st.text_input("Descrizione / Negozio")
                with col_curr2:
                    curr_options = ["EUR", "JPY"]
                    default_index = curr_options.index(default_curr) if default_curr in curr_options else 0
                    t_curr = st.selectbox("Valuta", curr_options, index=default_index)
                
                t_amount = st.number_input(f"Importo Totale ({t_curr})", value=0.0, step=1.0)
                if st.form_submit_button("💾 Registra Transazione"):
                    if t_amount > 0:
                        conn = sqlite3.connect(DB_NAME)
                        cursor = conn.cursor()
                        cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (t_amount, acc_id))
                        cursor.execute("INSERT INTO transactions (date, account_id, total_amount, currency, description) VALUES (?, ?, ?, ?, ?)",
                                       (str(t_date), acc_id, t_amount, t_curr, t_desc or "Spesa"))
                        conn.commit()
                        conn.close()
                        st.success("Transazione registrata!")
                        st.rerun()

    with sub_f3:
        st.subheader("Storico Transazioni")
        conn = sqlite3.connect(DB_NAME)
        df_t = pd.read_sql("SELECT t.id, t.date AS 'Data', a.name AS 'Conto', t.total_amount AS 'Importo', t.currency AS 'Valuta', t.description AS 'Descrizione' FROM transactions t LEFT JOIN accounts a ON t.account_id = a.id ORDER BY t.date DESC", conn)
        conn.close()
        if not df_t.empty:
            st.dataframe(df_t, use_container_width=True, hide_index=True)
            del_id = st.number_input("ID Transazione da eliminare e stornare", value=0, step=1)
            if st.button("❌ Elimina Transazione e Storna"):
                if del_id > 0:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("SELECT account_id, total_amount FROM transactions WHERE id = ?", (del_id,))
                    tx = cursor.fetchone()
                    if tx:
                        cursor.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (tx[1], tx[0]))
                        cursor.execute("SELECT item_name, quantity, unit FROM transaction_items WHERE transaction_id = ?", (del_id,))
                        for i_name, i_qty, i_unit in cursor.fetchall():
                            cursor.execute("SELECT id, quantity, unit FROM inventory WHERE item_name = ?", (i_name,))
                            inv = cursor.fetchone()
                            if inv:
                                conv_q = convert_qty(i_qty, i_unit, inv[2])
                                new_q = inv[1] - conv_q
                                if new_q <= 0: cursor.execute("DELETE FROM inventory WHERE id = ?", (inv[0],))
                                else: cursor.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (new_q, inv[0]))
                        cursor.execute("DELETE FROM transactions WHERE id = ?", (del_id,))
                        conn.commit()
                        conn.close()
                        st.success("Transazione eliminata e inventario stornato.")
                        st.rerun()
        else:
            st.info("Nessuna transazione registrata.")


# ==========================================
# 2. AREA POSSEDIMENTI
# ==========================================
with tab_possedimenti:
    st.header("Gestione Possedimenti & Spesa")
    sub_p1, sub_p2, sub_p3 = st.tabs(["Dispensa & Inventario", "Lista della Spesa Manuale", "🤖 Cose che Mancano"])
    available_units = get_available_units()
    
    with sub_p1:
        st.subheader("Tabella Inventario & Dispensa")
        conn = sqlite3.connect(DB_NAME)
        df_inv = pd.read_sql("SELECT id, item_name AS 'Prodotto', category AS 'Categoria', quantity AS 'Quantità', unit AS 'Unità' FROM inventory", conn)
        conn.close()
        if not df_inv.empty:
            edited_inv = st.data_editor(df_inv, use_container_width=True, hide_index=True, num_rows="dynamic", key="inv_table_editor")
            if st.button("💾 Salva Modifiche Dispensa"):
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM inventory")
                for _, row in edited_inv.iterrows():
                    if pd.notna(row['Prodotto']) and str(row['Prodotto']).strip() != "":
                        cursor.execute("INSERT INTO inventory (item_name, category, quantity, unit) VALUES (?, ?, ?, ?)",
                                       (str(row['Prodotto']).strip().capitalize(), str(row['Categoria']), float(row['Quantità']), str(row['Unità'])))
                conn.commit()
                conn.close()
                st.success("Dispensa aggiornata.")
                st.rerun()
        else:
            st.info("Inventario vuoto.")
            
        with st.form("add_inv"):
            st.markdown("**Aggiungi Singolo Prodotto**")
            i_name = st.text_input("Nome Prodotto / Oggetto")
            i_cat = st.selectbox("Categoria", ["Dispensa", "Elettronica", "Abbigliamento", "Collezionabili", "Altro"])
            c_col1, c_col2 = st.columns(2)
            with c_col1: i_qty = st.number_input("Quantità", value=1.0, step=1.0)
            with c_col2: i_unit = st.selectbox("Unità", available_units)
            if st.form_submit_button("➕ Aggiungi") and i_name:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                add_or_update_inventory(cursor, i_name, i_qty, i_unit, i_cat)
                conn.commit()
                conn.close()
                st.success("Aggiunto/Aggiornato!")
                st.rerun()

    with sub_p2:
        st.subheader("Lista della Spesa")
        conn = sqlite3.connect(DB_NAME)
        df_shop = pd.read_sql("SELECT id, item_name AS 'Prodotto', quantity AS 'Quantità', unit AS 'Unità', category AS 'Categoria' FROM shopping_list", conn)
        conn.close()
        edited_shop = st.data_editor(df_shop, use_container_width=True, hide_index=True, num_rows="dynamic", key="shop_table_editor")
        if st.button("💾 Salva Lista della Spesa"):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM shopping_list")
            for _, row in edited_shop.iterrows():
                if pd.notna(row['Prodotto']) and str(row['Prodotto']).strip() != "":
                    cursor.execute("INSERT INTO shopping_list (item_name, quantity, unit, category, checked) VALUES (?, ?, ?, ?, 0)",
                                   (str(row['Prodotto']).strip().capitalize(), float(row['Quantità']), str(row['Unità']), str(row['Categoria'])))
            conn.commit()
            conn.close()
            st.success("Lista salvata!")
            st.rerun()
            
        st.divider()
        st.subheader("Checkout / Acquista")
        conn = sqlite3.connect(DB_NAME)
        df_accs = pd.read_sql("SELECT id, name, currency FROM accounts", conn)
        conn.close()
        if not df_accs.empty and not df_shop.empty:
            chk_acc_dict = {row['name']: {'id': row['id'], 'currency': row['currency']} for _, row in df_accs.iterrows()}
            with st.form("checkout_form"):
                col_chk1, col_chk2 = st.columns(2)
                with col_chk1: chk_date = st.date_input("Data Spesa", value=date.today())
                with col_chk2: chk_sel_acc = st.selectbox("Paga con Conto:", list(chk_acc_dict.keys()))
                
                chk_default_curr = chk_acc_dict[chk_sel_acc]['currency']
                chk_acc_id = chk_acc_dict[chk_sel_acc]['id']
                
                col_chk_sub1, col_chk_sub2 = st.columns(2)
                with col_chk_sub1: chk_desc = st.text_input("Negozio", value="Spesa")
                with col_chk_sub2:
                    chk_curr_options = ["EUR", "JPY"]
                    chk_default_idx = chk_curr_options.index(chk_default_curr) if chk_default_curr in chk_curr_options else 0
                    chk_curr = st.selectbox("Valuta Spesa", chk_curr_options, index=chk_default_idx, key="chk_currency_select")
                
                chk_total = st.number_input(f"Totale pagato ({chk_curr})", value=0.0, step=1.0)
                if st.form_submit_button("💳 Paga, Aggiorna Dispensa e Svuota Lista"):
                    if chk_total > 0:
                        conn = sqlite3.connect(DB_NAME)
                        cursor = conn.cursor()
                        cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (chk_total, chk_acc_id))
                        cursor.execute("INSERT INTO transactions (date, account_id, total_amount, currency, description) VALUES (?, ?, ?, ?, ?)",
                                       (str(chk_date), chk_acc_id, chk_total, chk_curr, chk_desc))
                        t_id = cursor.lastrowid
                        cursor.execute("SELECT item_name, quantity, unit, category FROM shopping_list")
                        for iname, iq, iu, icat in cursor.fetchall():
                            cursor.execute("INSERT INTO transaction_items (transaction_id, item_name, quantity, unit) VALUES (?, ?, ?, ?)", (t_id, iname, iq, iu))
                            add_or_update_inventory(cursor, iname, iq, iu, icat)
                        cursor.execute("DELETE FROM shopping_list")
                        conn.commit()
                        conn.close()
                        st.success("Spesa registrata e dispensa aggiornata!")
                        st.rerun()

    with sub_p3:
        st.subheader("Rilevamento Automatico Scorte")
        conn = sqlite3.connect(DB_NAME)
        df_missing = pd.read_sql("SELECT item_name, category, quantity, unit FROM inventory WHERE quantity <= 1", conn)
        conn.close()
        if not df_missing.empty:
            selected_to_copy = []
            for idx, row in df_missing.iterrows():
                p_name, p_cat, p_qty, p_unit = row['item_name'], row['category'], row['quantity'], row['unit']
                if st.checkbox(f"{p_name} ({p_qty} {p_unit})", value=True, key=f"missing_{idx}"):
                    selected_to_copy.append((p_name, p_cat, p_unit))
            if st.button("📥 Copia selezionati nella Lista della Spesa"):
                if selected_to_copy:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    for p_name, p_cat, p_unit in selected_to_copy:
                        cursor.execute("""
                            INSERT INTO shopping_list (item_name, quantity, unit, category, checked) 
                            SELECT ?, 1.0, ?, ?, 0 
                            WHERE NOT EXISTS (SELECT 1 FROM shopping_list WHERE item_name = ?)
                        """, (p_name, p_unit, p_cat, p_name))
                    conn.commit()
                    conn.close()
                    st.success("Copiato!")
                    st.rerun()


# ==========================================
# 3. AREA PASTI
# ==========================================
with tab_pasti:
    st.header("Gestione Pasti & Cucina")
    sub_m1, sub_m2, sub_m3 = st.tabs(["Ricette", "Calendario Slot", "🤖 Assistente IA"])
    
    with sub_m1:
        st.subheader("Archivio Piatti & Ricette")
        st.caption("Crea o modifica i tuoi piatti. Clicca su un piatto per visualizzare o modificare i suoi ingredienti.")
        
        with st.form("meal_form"):
            meal_name = st.text_input("Nome Nuovo Piatto (es. Yakisoba, Riso al curry)")
            if "meal_cart" not in st.session_state:
                st.session_state.meal_cart = pd.DataFrame(columns=["Ingrediente", "Quantità", "Unità"])
            edited_m_items = st.data_editor(st.session_state.meal_cart, num_rows="dynamic", use_container_width=True, key="new_meal_editor")
            
            if st.form_submit_button("💾 Salva Piatto nell'Archivio") and meal_name:
                cleaned_meal_name = meal_name.strip().capitalize()
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO meals (name) VALUES (?)", (cleaned_meal_name,))
                cursor.execute("SELECT id FROM meals WHERE name = ?", (cleaned_meal_name,))
                res_fetch = cursor.fetchone()
                if res_fetch:
                    m_id = res_fetch[0]
                    for _, row in edited_m_items.iterrows():
                        if pd.notna(row['Ingrediente']) and str(row['Ingrediente']).strip() != "":
                            cursor.execute("INSERT INTO meal_ingredients (meal_id, item_name, quantity, unit) VALUES (?, ?, ?, ?)",
                                           (m_id, str(row['Ingrediente']).strip().capitalize(), float(row['Quantità']) if pd.notna(row['Quantità']) else 1.0, str(row['Unità'])))
                    conn.commit()
                conn.close()
                st.success(f"Piatto '{cleaned_meal_name}' salvato con successo!")
                st.session_state.meal_cart = pd.DataFrame(columns=["Ingrediente", "Quantità", "Unità"])
                st.rerun()
                
        st.divider()
        st.subheader("I tuoi Piatti Esistenti")
        
        conn = sqlite3.connect(DB_NAME)
        df_meals = pd.read_sql("SELECT id, name AS 'Piatto' FROM meals ORDER BY Piatto", conn)
        conn.close()
        
        if not df_meals.empty:
            for _, m_row in df_meals.iterrows():
                m_id = m_row['id']
                m_name = m_row['Piatto']
                
                with st.expander(f"🍲 {m_name}"):
                    conn = sqlite3.connect(DB_NAME)
                    df_ing = pd.read_sql("SELECT id, item_name AS 'Ingrediente', quantity AS 'Quantità', unit AS 'Unità' FROM meal_ingredients WHERE meal_id = ?", conn, params=(m_id,))
                    conn.close()
                    
                    edited_ing = st.data_editor(df_ing, use_container_width=True, hide_index=True, num_rows="dynamic", key=f"ing_edit_{m_id}")
                    
                    col_sav, col_del = st.columns(2)
                    with col_sav:
                        if st.button("💾 Salva Modifiche Piatto", key=f"save_meal_{m_id}"):
                            conn = sqlite3.connect(DB_NAME)
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM meal_ingredients WHERE meal_id = ?", (m_id,))
                            for _, i_row in edited_ing.iterrows():
                                if pd.notna(i_row['Ingrediente']) and str(i_row['Ingrediente']).strip() != "":
                                    cursor.execute("INSERT INTO meal_ingredients (meal_id, item_name, quantity, unit) VALUES (?, ?, ?, ?)",
                                                   (m_id, str(i_row['Ingrediente']).strip().capitalize(), float(i_row['Quantità']) if pd.notna(i_row['Quantità']) else 1.0, str(i_row['Unità'])))
                            conn.commit()
                            conn.close()
                            st.success(f"Ricetta '{m_name}' aggiornata!")
                            st.rerun()
                    with col_del:
                        if st.button("❌ Elimina Piatto dall'Archivio", key=f"del_meal_{m_id}"):
                            conn = sqlite3.connect(DB_NAME)
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM meals WHERE id = ?", (m_id,))
                            conn.commit()
                            conn.close()
                            st.warning(f"Piatto '{m_name}' eliminato.")
                            st.rerun()
        else:
            st.info("Nessun piatto presente nell'archivio. Creane uno qui sopra!")

    with sub_m2:
        st.subheader("Calendario & Slot")
        if "cal_off" not in st.session_state: st.session_state.cal_off = 0
        col_n1, col_n2, col_n3 = st.columns([1, 2, 1])
        with col_n1:
            if st.button("⬅️ Indietro"): st.session_state.cal_off -= 1; st.rerun()
        with col_n2:
            s_week = date.today() - timedelta(days=date.today().weekday()) + timedelta(weeks=st.session_state.cal_off)
            e_week = s_week + timedelta(days=6)
            st.markdown(f"<h4 style='text-align: center;'>📅 {s_week.strftime('%d %b')} - {e_week.strftime('%d %b %Y')}</h4>", unsafe_allow_html=True)
        with col_n3:
            if st.button("Avanti ➡️"): st.session_state.cal_off += 1; st.rerun()
            
        st.divider()
        
        with st.expander("➕ Pianifica Slot nel Calendario"):
            with st.form("sched_form_safe"):
                c_d1, c_d2, c_d3 = st.columns(3)
                with c_d1: s_date = st.date_input("Data", value=date.today())
                with c_d2: s_slot = st.selectbox("Slot", ["Colazione", "Pranzo", "Cena"])
                with c_d3: s_context = st.selectbox("Contesto", ["A Casa (Canonico)", "Fuori Casa", "A Casa di Altri", "Offerto da Me"])
                
                conn = sqlite3.connect(DB_NAME)
                df_m = pd.read_sql("SELECT id, name FROM meals ORDER BY name", conn)
                conn.close()
                m_dict = {row['name']: row['id'] for _, row in df_m.iterrows()} if not df_m.empty else {}
                
                sel_meals = st.multiselect("Seleziona Piatti dall'Archivio", list(m_dict.keys()))
                
                if st.form_submit_button("Pianifica nel Calendario"):
                    if sel_meals:
                        conn = sqlite3.connect(DB_NAME)
                        cursor = conn.cursor()
                        for m_label in sel_meals:
                            cursor.execute("INSERT INTO calendar_schedule (date, slot, meal_id, context, consumed) VALUES (?, ?, ?, ?, 0)", 
                                           (str(s_date), s_slot, m_dict[m_label], s_context))
                        conn.commit()
                        conn.close()
                        st.success("Pianificato con successo!")
                        st.rerun()
                    else:
                        st.warning("Seleziona almeno un piatto.")

        st.divider()
        days_c = st.columns(7)
        d_names = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        for i in range(7):
            curr_d = s_week + timedelta(days=i)
            d_str = str(curr_d)
            with days_c[i]:
                st.markdown(f"**{d_names[i]}**<br><span style='font-size:0.85em; color:gray;'>{curr_d.strftime('%d/%m')}</span>", unsafe_allow_html=True)
                st.divider()
                conn = sqlite3.connect(DB_NAME)
                df_ds = pd.read_sql("SELECT DISTINCT slot, context, consumed FROM calendar_schedule WHERE date = ? ORDER BY slot", conn, params=(d_str,))
                conn.close()
                if not df_ds.empty:
                    for _, row in df_ds.iterrows():
                        slot_n, slot_ctx, slot_st = row['slot'], row['context'], row['consumed']
                        conn = sqlite3.connect(DB_NAME)
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT cs.id, cs.meal_id, COALESCE(m.name, 'Piatto non trovato') 
                            FROM calendar_schedule cs 
                            LEFT JOIN meals m ON cs.meal_id = m.id 
                            WHERE cs.date = ? AND cs.slot = ? AND cs.context = ?
                        """, (d_str, slot_n, slot_ctx))
                        s_items = cursor.fetchall()
                        conn.close()
                        
                        emoji = "🟡" if slot_st == 0 else ("🟢" if slot_st == 1 else "🔴")
                        with st.container(border=True):
                            st.markdown(f"**{emoji} {slot_n}**")
                            st.markdown(f"<small style='color:gray;'>{slot_ctx}</small>", unsafe_allow_html=True)
                            for _, _, m_n in s_items: 
                                st.markdown(f"<small>- {m_n}</small>", unsafe_allow_html=True)
                            
                            # --- MODIFICA / AGGIORNAMENTO SLOT ---
                            with st.expander("✏️ Modifica"):
                                with st.form(f"edit_slot_form_{d_str}_{slot_n}"):
                                    new_ctx = st.selectbox("Nuovo Contesto", ["A Casa (Canonico)", "Fuori Casa", "A Casa di Altri", "Offerto da Me"], 
                                                           index=["A Casa (Canonico)", "Fuori Casa", "A Casa di Altri", "Offerto da Me"].index(slot_ctx) if slot_ctx in ["A Casa (Canonico)", "Fuori Casa", "A Casa di Altri", "Offerto da Me"] else 0,
                                                           key=f"ed_ctx_{d_str}_{slot_n}")
                                    
                                    conn_m = sqlite3.connect(DB_NAME)
                                    df_all_m = pd.read_sql("SELECT id, name FROM meals ORDER BY name", conn_m)
                                    conn_m.close()
                                    all_m_dict = {r['name']: r['id'] for _, r in df_all_m.iterrows()} if not df_all_m.empty else {}
                                    
                                    current_meal_name = s_items[0][2] if s_items and s_items[0][2] != 'Piatto non trovato' else list(all_m_dict.keys())[0] if all_m_dict else ""
                                    def_idx = list(all_m_dict.keys()).index(current_meal_name) if current_meal_name in all_m_dict else 0
                                    
                                    new_meal_label = st.selectbox("Cambia Piatto", list(all_m_dict.keys()) if all_m_dict else ["Nessun piatto"], 
                                                                  index=def_idx if all_m_dict else 0, 
                                                                  key=f"ed_meal_{d_str}_{slot_n}")
                                    
                                    if st.form_submit_button("💾 Aggiorna Slot"):
                                        if all_m_dict and new_meal_label in all_m_dict:
                                            new_m_id = all_m_dict[new_meal_label]
                                            conn = sqlite3.connect(DB_NAME)
                                            cursor = conn.cursor()
                                            for sid, _, _ in s_items:
                                                cursor.execute("UPDATE calendar_schedule SET context = ?, meal_id = ? WHERE id = ?", 
                                                               (new_ctx, new_m_id, sid))
                                            conn.commit()
                                            conn.close()
                                            st.success("Aggiornato!")
                                            st.rerun()

                            if slot_st == 0:
                                if slot_ctx == 'Fuori Casa':
                                    with st.form(f"eat_out_form_{d_str}_{slot_n}"):
                                        conn_acc = sqlite3.connect(DB_NAME)
                                        df_accs = pd.read_sql("SELECT id, name, currency FROM accounts", conn_acc)
                                        conn_acc.close()
                                        
                                        acc_dict_o = {r['name']: {'id': r['id'], 'currency': r['currency']} for _, r in df_accs.iterrows()} if not df_accs.empty else {}
                                        
                                        if acc_dict_o:
                                            sel_ac_o = st.selectbox("Paga con:", list(acc_dict_o.keys()), key=f"acc_o_{d_str}_{slot_n}")
                                            def_cur_o = acc_dict_o[sel_ac_o]['currency']
                                            ac_id_o = acc_dict_o[sel_ac_o]['id']
                                            cost_o = st.number_input(f"Costo ({def_cur_o})", value=0.0, step=100.0, key=f"cost_o_{d_str}_{slot_n}")
                                            
                                            if st.form_submit_button("💳 Paga e Registra"):
                                                conn = sqlite3.connect(DB_NAME)
                                                cursor = conn.cursor()
                                                cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (cost_o, ac_id_o))
                                                cursor.execute("INSERT INTO transactions (date, account_id, total_amount, currency, description) VALUES (?, ?, ?, ?, ?)",
                                                               (d_str, ac_id_o, cost_o, def_cur_o, f"Pasto fuori casa ({slot_n})"))
                                                for sid, _, _ in s_items:
                                                    cursor.execute("UPDATE calendar_schedule SET consumed = 1 WHERE id = ?", (sid,))
                                                conn.commit()
                                                conn.close()
                                                st.success("Registrato!")
                                                st.rerun()
                                        else:
                                            st.warning("Crea prima un conto in Finanza.")
                                else:
                                    if st.button("🍽️ Consuma", key=f"e_{d_str}_{slot_n}"):
                                        conn = sqlite3.connect(DB_NAME)
                                        cursor = conn.cursor()
                                        for sid, _, _ in s_items:
                                            cursor.execute("SELECT meal_id, context FROM calendar_schedule WHERE id = ?", (sid,))
                                            res_slot = cursor.fetchone()
                                            if res_slot:
                                                mid, ctx = res_slot
                                                if mid and ctx in ['A Casa (Canonico)', 'Offerto da Me']:
                                                    cursor.execute("SELECT item_name, quantity, unit FROM meal_ingredients WHERE meal_id = ?", (mid,))
                                                    for iname, iq, iunit in cursor.fetchall():
                                                        cursor.execute("SELECT id, quantity, unit FROM inventory WHERE item_name = ?", (iname,))
                                                        inv = cursor.fetchone()
                                                        if inv:
                                                            cq = convert_qty(iq, iunit, inv[2])
                                                            nq = inv[1] - cq
                                                            if nq <= 0: cursor.execute("DELETE FROM inventory WHERE id = ?", (inv[0],))
                                                            else: cursor.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (nq, inv[0]))
                                            cursor.execute("UPDATE calendar_schedule SET consumed = 1 WHERE id = ?", (sid,))
                                        conn.commit()
                                        conn.close()
                                        st.rerun()
                                        
                            if st.button("❌ Elimina Slot", key=f"d_{d_str}_{slot_n}"):
                                conn = sqlite3.connect(DB_NAME)
                                cursor = conn.cursor()
                                for sid, _, _ in s_items:
                                    cursor.execute("DELETE FROM calendar_schedule WHERE id = ?", (sid,))
                                conn.commit()
                                conn.close()
                                st.rerun()

    with sub_m3:
        st.subheader("🤖 Assistente IA Locale (Ollama)")
        st.caption("Incolla la tua pianificazione. Verrà creato un backup automatico, e l'IA interpreterà il testo per aggiornare il calendario.")
        ai_input_text = st.text_area("Testo della pianificazione:", placeholder="es. Domani pranzo a casa di altri, domani sera yakisoba a casa, lunedì sushi fuori a Toyosu...")
        
        if st.button("🚀 Esegui con Ollama"):
            if ai_input_text.strip():
                b_file = create_database_backup()
                st.info(f"🛡️ Backup di sicurezza creato in: `{b_file}`")
                
                with st.spinner("L'intelligenza artificiale locale (Ollama) sta elaborando il testo..."):
                    events = parse_natural_language_schedule(ai_input_text)
                    if events:
                        applied_count = apply_ai_schedule_to_db(events)
                        st.success(f"✨ Fatto! Aggiunti con successo {applied_count} eventi al calendario.")
                        st.rerun()
                    else:
                        st.warning("Nessun evento estratto o problema di connessione con Ollama.")
            else:
                st.warning("Inserisci del testo prima di avviare l'assistente.")

# ==========================================
# 4. AREA IMPOSTAZIONI
# ==========================================
with tab_impostazioni:
    st.header("Impostazioni & Sicurezza")
    st.subheader("💾 Gestione Backup Database")
    st.caption("Crea una copia di sicurezza del database o ripristina uno stato precedente.")
    
    if st.button("📥 Crea Backup Manuale Adesso"):
        b_file = create_database_backup()
        st.success(f"Backup creato in: `{b_file}`")
        
    st.divider()
    st.markdown("**Backup Disponibili:**")
    if os.path.exists("backups"):
        backups = sorted(os.listdir("backups"), reverse=True)
        if backups:
            selected_backup = st.selectbox("Seleziona backup da ripristinare", backups)
            if st.button("🔄 Ripristina questo Backup"):
                shutil.copy(f"backups/{selected_backup}", DB_NAME)
                st.success(f"Database ripristinato con successo da `{selected_backup}`!")
                st.rerun()
        else:
            st.info("Nessun backup presente.")
    else:
        st.info("Cartella backup vuota.")