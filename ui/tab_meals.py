import streamlit as st
import pandas as pd
from datetime import date, timedelta
from database.connection import get_connection
from services.inventory_service import consume_inventory_item, restore_inventory_item, get_available_units
from services.meal_service import parse_natural_language_schedule, apply_ai_schedule_to_db

def render_meals_tab(create_backup_callback):
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
                conn = get_connection()
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
        
        conn = get_connection()
        df_meals = pd.read_sql("SELECT id, name AS 'Piatto' FROM meals ORDER BY Piatto", conn)
        conn.close()
        
        if not df_meals.empty:
            for _, m_row in df_meals.iterrows():
                m_id = m_row['id']
                m_name = m_row['Piatto']
                
                with st.expander(f"🍲 {m_name}"):
                    conn = get_connection()
                    df_ing = pd.read_sql("SELECT id, item_name AS 'Ingrediente', quantity AS 'Quantità', unit AS 'Unità' FROM meal_ingredients WHERE meal_id = ? ORDER BY item_name ASC", conn, params=(m_id,))
                    conn.close()
                    
                    edited_ing = st.data_editor(df_ing, use_container_width=True, hide_index=True, num_rows="dynamic", key=f"ing_edit_{m_id}")
                    
                    col_sav, col_del = st.columns(2)
                    with col_sav:
                        if st.button("💾 Salva Modifiche Piatto", key=f"save_meal_{m_id}"):
                            conn = get_connection()
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
                            conn = get_connection()
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
                
                conn = get_connection()
                df_m = pd.read_sql("SELECT id, name FROM meals ORDER BY name ASC", conn)
                available_units = get_available_units()
                conn.close()
                m_dict = {row['name']: row['id'] for _, row in df_m.iterrows()} if not df_m.empty else {}
                
                sel_meals = st.multiselect("Seleziona Piatti dall'Archivio (opzionale)", list(m_dict.keys()))
                
                st.markdown("**O aggiungi singoli ingredienti al volo:**")
                if "sched_extra_ingredients" not in st.session_state:
                    st.session_state.sched_extra_ingredients = pd.DataFrame(columns=["Ingrediente", "Quantità", "Unità"])
                
                edited_extra_ings = st.data_editor(
                    st.session_state.sched_extra_ingredients, 
                    num_rows="dynamic", 
                    use_container_width=True, 
                    key="sched_extra_editor",
                    column_config={
                        "Unità": st.column_config.SelectboxColumn("Unità", options=available_units, required=True)
                    }
                )
                
                if st.form_submit_button("Pianifica nel Calendario"):
                    if sel_meals or not edited_extra_ings.empty:
                        conn = get_connection()
                        cursor = conn.cursor()
                        
                        if sel_meals:
                            for m_label in sel_meals:
                                cursor.execute("""
                                    INSERT INTO calendar_schedule (date, slot, meal_id, context, consumed) 
                                    VALUES (?, ?, ?, ?, 0)
                                """, (str(s_date), s_slot, m_dict[m_label], s_context))
                                schedule_id = cursor.lastrowid
                                
                                for _, row in edited_extra_ings.iterrows():
                                    if pd.notna(row['Ingrediente']) and str(row['Ingrediente']).strip() != "":
                                        cursor.execute("""
                                            INSERT INTO calendar_slot_ingredients (schedule_id, item_name, quantity, unit)
                                            VALUES (?, ?, ?, ?)
                                        """, (schedule_id, str(row['Ingrediente']).strip().capitalize(), 
                                              float(row['Quantità']) if pd.notna(row['Quantità']) else 1.0, 
                                              str(row['Unità'])))
                        else:
                            cursor.execute("""
                                INSERT INTO calendar_schedule (date, slot, meal_id, context, consumed) 
                                VALUES (?, ?, NULL, ?, 0)
                            """, (str(s_date), s_slot, s_context))
                            schedule_id = cursor.lastrowid
                            
                            for _, row in edited_extra_ings.iterrows():
                                if pd.notna(row['Ingrediente']) and str(row['Ingrediente']).strip() != "":
                                    cursor.execute("""
                                        INSERT INTO calendar_slot_ingredients (schedule_id, item_name, quantity, unit)
                                        VALUES (?, ?, ?, ?)
                                    """, (schedule_id, str(row['Ingrediente']).strip().capitalize(), 
                                          float(row['Quantità']) if pd.notna(row['Quantità']) else 1.0, 
                                          str(row['Unità'])))
                            
                        conn.commit()
                        conn.close()
                        st.success("Pianificato con successo!")
                        st.session_state.sched_extra_ingredients = pd.DataFrame(columns=["Ingrediente", "Quantità", "Unità"])
                        st.rerun()
                    else:
                        st.warning("Seleziona almeno un piatto o inserisci un ingrediente.")
                        
        st.divider()
        days_c = st.columns(7)
        d_names = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        for i in range(7):
            curr_d = s_week + timedelta(days=i)
            d_str = str(curr_d)
            with days_c[i]:
                st.markdown(f"**{d_names[i]}**<br><span style='font-size:0.85em; color:gray;'>{curr_d.strftime('%d/%m')}</span>", unsafe_allow_html=True)
                st.divider()
                conn = get_connection()
                df_ds = pd.read_sql("SELECT DISTINCT slot, context, consumed FROM calendar_schedule WHERE date = ? ORDER BY slot", conn, params=(d_str,))
                conn.close()
                if not df_ds.empty:
                    for _, row in df_ds.iterrows():
                        slot_n, slot_ctx, slot_st = row['slot'], row['context'], row['consumed']
                        conn = get_connection()
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
                            
                            # Mostra i piatti dall'archivio
                            for _, _, m_n in s_items: 
                                if m_n != 'Piatto non trovato':
                                    st.markdown(f"<small>- {m_n}</small>", unsafe_allow_html=True)
                            
                            # Mostra gli ingredienti extra al volo per questo slot
                            for sid, _, _ in s_items:
                                conn_ex = get_connection()
                                cursor_ex = conn_ex.cursor()
                                cursor_ex.execute("SELECT item_name, quantity, unit FROM calendar_slot_ingredients WHERE schedule_id = ?", (sid,))
                                extra_ings = cursor_ex.fetchall()
                                conn_ex.close()
                                for einame, eiq, eiunit in extra_ings:
                                    st.markdown(f"<small style='color: #0288d1;'>- [Extra] {einame} ({eiq} {eiunit})</small>", unsafe_allow_html=True)
                            
                            with st.expander("✏️ Modifica"):
                                with st.form(f"edit_slot_form_{d_str}_{slot_n}"):
                                    new_ctx = st.selectbox("Nuovo Contesto", ["A Casa (Canonico)", "Fuori Casa", "A Casa di Altri", "Offerto da Me"], 
                                                           index=["A Casa (Canonico)", "Fuori Casa", "A Casa di Altri", "Offerto da Me"].index(slot_ctx) if slot_ctx in ["A Casa (Canonico)", "Fuori Casa", "A Casa di Altri", "Offerto da Me"] else 0,
                                                           key=f"ed_ctx_{d_str}_{slot_n}")
                                    
                                    conn_m = get_connection()
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
                                            conn = get_connection()
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
                                        conn_acc = get_connection()
                                        df_accs = pd.read_sql("SELECT id, name, currency FROM accounts", conn_acc)
                                        conn_acc.close()
                                        
                                        acc_dict_o = {r['name']: {'id': r['id'], 'currency': r['currency']} for _, r in df_accs.iterrows()} if not df_accs.empty else {}
                                        
                                        if acc_dict_o:
                                            sel_ac_o = st.selectbox("Paga con:", list(acc_dict_o.keys()), key=f"acc_o_{d_str}_{slot_n}")
                                            def_cur_o = acc_dict_o[sel_ac_o]['currency']
                                            ac_id_o = acc_dict_o[sel_ac_o]['id']
                                            cost_o = st.number_input(f"Costo ({def_cur_o})", value=0.0, step=100.0, key=f"cost_o_{d_str}_{slot_n}")
                                            
                                            if st.form_submit_button("💳 Paga e Registra"):
                                                conn = get_connection()
                                                cursor = conn.cursor()
                                                cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (cost_o, ac_id_o))
                                                cursor.execute("INSERT INTO transactions (date, account_id, total_amount, currency, category, description) VALUES (?, ?, ?, ?, ?, ?)",
                                                               (d_str, ac_id_o, cost_o, def_cur_o, "Mangiare/Bere fuori", f"Pasto fuori casa ({slot_n})"))
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
                                        conn = get_connection()
                                        cursor = conn.cursor()
                                        for sid, _, _ in s_items:
                                            cursor.execute("SELECT meal_id, context FROM calendar_schedule WHERE id = ?", (sid,))
                                            res_slot = cursor.fetchone()
                                            if res_slot:
                                                mid, ctx = res_slot
                                                if ctx in ['A Casa (Canonico)', 'Offerto da Me']:
                                                    # Consuma ingredienti del piatto da archivio
                                                    if mid:
                                                        cursor.execute("SELECT item_name, quantity, unit FROM meal_ingredients WHERE meal_id = ?", (mid,))
                                                        for iname, iq, iunit in cursor.fetchall():
                                                            consume_inventory_item(cursor, iname, iq, iunit)
                                                    
                                                    # Consuma ingredienti extra al volo
                                                    cursor.execute("SELECT item_name, quantity, unit FROM calendar_slot_ingredients WHERE schedule_id = ?", (sid,))
                                                    for einame, eiq, eiunit in cursor.fetchall():
                                                        consume_inventory_item(cursor, einame, eiq, eiunit)
                                                        
                                            cursor.execute("UPDATE calendar_schedule SET consumed = 1 WHERE id = ?", (sid,))
                                        conn.commit()
                                        conn.close()
                                        st.rerun()
                                        
                            if st.button("❌ Elimina Slot", key=f"d_{d_str}_{slot_n}"):
                                conn = get_connection()
                                cursor = conn.cursor()
                                
                                for sid, meal_id_val, _ in s_items:
                                    cursor.execute("SELECT consumed, meal_id, context FROM calendar_schedule WHERE id = ?", (sid,))
                                    row_data = cursor.fetchone()
                                    
                                    if row_data:
                                        is_consumed, m_id, ctx = row_data
                                        if is_consumed == 1 and ctx in ['A Casa (Canonico)', 'Offerto da Me']:
                                            # Ripristina ingredienti del piatto archiviato
                                            if m_id:
                                                cursor.execute("SELECT item_name, quantity, unit FROM meal_ingredients WHERE meal_id = ?", (m_id,))
                                                ingredients = cursor.fetchall()
                                                for iname, iq, iunit in ingredients:
                                                    restore_inventory_item(cursor, iname, iq, iunit)
                                            
                                            # Ripristina ingredienti extra
                                            cursor.execute("SELECT item_name, quantity, unit FROM calendar_slot_ingredients WHERE schedule_id = ?", (sid,))
                                            extra_ings = cursor.fetchall()
                                            for einame, eiq, eiunit in extra_ings:
                                                restore_inventory_item(cursor, einame, eiq, eiunit)
                                                
                                    cursor.execute("DELETE FROM calendar_schedule WHERE id = ?", (sid,))
                                    
                                conn.commit()
                                conn.close()
                                st.success("Slot eliminato e dispensa aggiornata correttamente!")
                                st.rerun()

    with sub_m3:
        st.subheader("🤖 Assistente IA Locale (Ollama)")
        st.caption("Incolla la tua pianificazione. Verrà creato un backup automatico, e l'IA interpreterà il testo per aggiornare il calendario.")
        ai_input_text = st.text_area("Testo della pianificazione:", placeholder="es. Domani pranzo a casa di altri, domani sera yakisoba a casa, lunedì sushi fuori a Toyosu...")
        
        if st.button("🚀 Esegui con Ollama"):
            if ai_input_text.strip():
                b_file = create_backup_callback()
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