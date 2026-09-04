import streamlit as st
import pandas as pd
from datetime import date
from database.connection import get_connection
from services.inventory_service import get_available_units, add_or_update_inventory

def render_possessions_tab():
    st.header("Gestione Possedimenti & Spesa")
    sub_p1, sub_p2, sub_p3 = st.tabs(["Dispensa & Inventario", "Lista della Spesa Manuale", "🤖 Cose che Mancano"])
    available_units = get_available_units()
    
    with sub_p1:
        st.subheader("Tabella Inventario & Dispensa")
        conn = get_connection()
        df_inv = pd.read_sql("SELECT id, item_name AS 'Prodotto', category AS 'Categoria', quantity AS 'Quantità', unit AS 'Unità' FROM inventory ORDER BY item_name ASC", conn)
        conn.close()
        if not df_inv.empty:
            edited_inv = st.data_editor(df_inv, use_container_width=True, hide_index=True, num_rows="dynamic", key="inv_table_editor")
            if st.button("💾 Salva Modifiche Dispensa"):
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM inventory")
                for _, row in edited_inv.iterrows():
                    if pd.notna(row['Prodotto']) and str(row['Prodotto']).strip() != "":
                        cat_val = str(row['Categoria']).strip() if pd.notna(row['Categoria']) and str(row['Categoria']).strip() != "" else "Spesa"
                        qty_val = float(row['Quantità']) if pd.notna(row['Quantità']) else 0.0
                        p_name = str(row['Prodotto']).strip().capitalize()
                        p_unit = str(row['Unità'])
                        
                        if qty_val <= 0:
                            cursor.execute("""
                                INSERT INTO shopping_list (item_name, quantity, unit, category, checked)
                                SELECT ?, 1.0, ?, ?, 0
                                WHERE NOT EXISTS (SELECT 1 FROM shopping_list WHERE item_name = ?)
                            """, (p_name, p_unit, cat_val, p_name))
                        else:
                            cursor.execute("INSERT INTO inventory (item_name, category, quantity, unit) VALUES (?, ?, ?, ?)",
                                           (p_name, cat_val, qty_val, p_unit))
                conn.commit()
                conn.close()
                st.success("Dispensa aggiornata.")
                st.rerun()
        else:
            st.info("Inventario vuoto.")
            
        with st.form("add_inv"):
            st.markdown("**Aggiungi Singolo Prodotto**")
            i_name = st.text_input("Nome Prodotto / Oggetto")
            i_cat = st.selectbox("Categoria", ["Spesa", "Altro", "Elettronica", "Abbigliamento", "Collezionabili"], index=0)
            c_col1, c_col2 = st.columns(2)
            with c_col1: i_qty = st.number_input("Quantità", value=1.0, step=1.0)
            with c_col2: i_unit = st.selectbox("Unità", available_units)
            if st.form_submit_button("➕ Aggiungi") and i_name:
                conn = get_connection()
                cursor = conn.cursor()
                add_or_update_inventory(cursor, i_name, i_qty, i_unit, i_cat)
                conn.commit()
                conn.close()
                st.success("Aggiunto/Aggiornato!")
                st.rerun()

    with sub_p2:
        st.subheader("Lista della Spesa")
        conn = get_connection()
        df_shop = pd.read_sql("SELECT id, item_name AS 'Prodotto', quantity AS 'Quantità', unit AS 'Unità', category AS 'Categoria' FROM shopping_list ORDER BY item_name ASC", conn)
        conn.close()
        edited_shop = st.data_editor(df_shop, use_container_width=True, hide_index=True, num_rows="dynamic", key="shop_table_editor")
        if st.button("💾 Salva Lista della Spesa"):
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM shopping_list")
            for _, row in edited_shop.iterrows():
                if pd.notna(row['Prodotto']) and str(row['Prodotto']).strip() != "":
                    cat_val = str(row['Categoria']).strip() if pd.notna(row['Categoria']) and str(row['Categoria']).strip() != "" else "Spesa"
                    cursor.execute("INSERT INTO shopping_list (item_name, quantity, unit, category, checked) VALUES (?, ?, ?, ?, 0)",
                                   (str(row['Prodotto']).strip().capitalize(), float(row['Quantità']), str(row['Unità']), cat_val))
            conn.commit()
            conn.close()
            st.success("Lista salvata!")
            st.rerun()
            
        st.divider()
        st.subheader("Checkout / Acquista")
        conn = get_connection()
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
                with col_chk_sub1: chk_desc = st.text_input("Negozio / Dettaglio", value="Spesa")
                with col_chk_sub2:
                    chk_curr_options = ["EUR", "JPY"]
                    chk_default_idx = chk_curr_options.index(chk_default_curr) if chk_default_curr in chk_curr_options else 0
                    chk_curr = st.selectbox("Valuta Spesa", chk_curr_options, index=chk_default_idx, key="chk_currency_select")
                
                chk_total = st.number_input(f"Totale pagato ({chk_curr})", value=0.0, step=1.0)
                if st.form_submit_button("💳 Paga, Aggiorna Dispensa e Svuota Lista"):
                    if chk_total > 0:
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (chk_total, chk_acc_id))
                        cursor.execute("INSERT INTO transactions (date, account_id, total_amount, currency, category, description) VALUES (?, ?, ?, ?, ?, ?)",
                                       (str(chk_date), chk_acc_id, chk_total, chk_curr, "Spesa", f"Checkout spesa: {chk_desc}"))
                        t_id = cursor.lastrowid
                        cursor.execute("SELECT item_name, quantity, unit, category FROM shopping_list")
                        for iname, iq, iu, icat in cursor.fetchall():
                            cursor.execute("INSERT INTO transaction_items (transaction_id, item_name, quantity, unit) VALUES (?, ?, ?, ?)", (t_id, iname, iq, iu))
                            add_or_update_inventory(cursor, iname, iq, iu, icat if icat else "Spesa")
                        cursor.execute("DELETE FROM shopping_list")
                        conn.commit()
                        conn.close()
                        st.success("Spesa registrata e dispensa aggiornata!")
                        st.rerun()

    with sub_p3:
        st.subheader("Rilevamento Automatico Scorte")
        conn = get_connection()
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
                    conn = get_connection()
                    cursor = conn.cursor()
                    for p_name, p_cat, p_unit in selected_to_copy:
                        cat_to_use = p_cat if p_cat else "Spesa"
                        cursor.execute("""
                            INSERT INTO shopping_list (item_name, quantity, unit, category, checked) 
                            SELECT ?, 1.0, ?, ?, 0 
                            WHERE NOT EXISTS (SELECT 1 FROM shopping_list WHERE item_name = ?)
                        """, (p_name, p_unit, cat_to_use, p_name))
                    conn.commit()
                    conn.close()
                    st.success("Copiato!")
                    st.rerun()