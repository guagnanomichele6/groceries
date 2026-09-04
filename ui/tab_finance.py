import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
from database.connection import get_connection

def render_finance_tab(eur_to_jpy, jpy_to_eur):
    st.header("Gestione Finanziaria")
    
    conn = get_connection()
    df_accs_global = pd.read_sql("SELECT id, name, currency FROM accounts", conn)
    conn.close()
    
    acc_global_dict = {row['name']: {'id': row['id'], 'currency': row['currency']} for _, row in df_accs_global.iterrows()} if not df_accs_global.empty else {}
    acc_global_names = list(acc_global_dict.keys()) if acc_global_dict else []

    expense_categories = [
        "Spesa", "Mangiare/Bere fuori", "Bollette", "Trasporti", 
        "Abbonamenti", "Sport", "Telefonia/Internet", "Viaggi", 
        "Investimenti", "Trasferimento ad Altri", "Giroconto", "Regali", "Altro"
    ]

    sub_f1, sub_f2, sub_f3, sub_f4, sub_f5, sub_f6 = st.tabs([
        "Depositi & Conti (e Broker)", 
        "Registra Spesa / Entrata", 
        "Giroconto / Trasferimento", 
        "Spese & Entrate Ricorrenti", 
        "Storico Transazioni",
        "📊 Riepilogo Mensile"
    ])
    
    with sub_f1:
        st.subheader("I tuoi Conti, Contanti e Portafogli di Investimento")
        st.caption("Gestisci sia i conti correnti che i conti di investimento (es. Directa, Binance).")
        
        conn = get_connection()
        df_accounts = pd.read_sql("SELECT id, name AS 'Conto', type AS 'Tipo', balance AS 'Saldo', currency AS 'Valuta' FROM accounts", conn)
        conn.close()
        
        if not df_accounts.empty:
            total_eur = sum(row['Saldo'] * jpy_to_eur if row['Valuta'] == 'JPY' else row['Saldo'] for _, row in df_accounts.iterrows())
            st.metric(label="Patrimonio Totale Stimato", value=f"€ {total_eur:,.2f}")
            st.divider()
            
            edited_acc = st.data_editor(df_accounts, use_container_width=True, hide_index=True)
            if st.button("💾 Salva Modifiche Conti"):
                conn = get_connection()
                cursor = conn.cursor()
                for _, row in edited_acc.iterrows():
                    if pd.notna(row['Conto']) and str(row['Conto']).strip() != "":
                        acc_id = int(row['id']) if pd.notna(row['id']) else None
                        acc_name = str(row['Conto']).strip()
                        acc_type = str(row['Tipo'])
                        acc_bal = float(row['Saldo'])
                        acc_curr = str(row['Valuta'])
                        
                        if acc_id:
                            cursor.execute("""
                                UPDATE accounts 
                                SET name = ?, type = ?, balance = ?, currency = ? 
                                WHERE id = ?
                            """, (acc_name, acc_type, acc_bal, acc_curr, acc_id))
                        else:
                            cursor.execute("""
                                INSERT INTO accounts (name, type, balance, currency) 
                                VALUES (?, ?, ?, ?)
                            """, (acc_name, acc_type, acc_bal, acc_curr))
                conn.commit()
                conn.close()
                st.success("Conti aggiornati.")
                st.rerun()
        else:
            st.info("Nessun conto registrato.")
            
        with st.form("add_acc"):
            st.markdown("**Aggiungi Nuovo Conto / Broker**")
            ac_name = st.text_input("Nome (es. Conto Corrente, Portafoglio, Directa, Binance)")
            ac_type = st.selectbox("Tipo", ["Conto Corrente", "Contante", "Investimenti"])
            ac_curr = st.selectbox("Valuta", ["EUR", "JPY"])
            ac_bal = st.number_input("Saldo Iniziale / Capitale di partenza", value=0.0, step=100.0)
            if st.form_submit_button("➕ Crea Conto") and ac_name:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO accounts (name, type, balance, currency) VALUES (?, ?, ?, ?)", (ac_name, ac_type, ac_bal, ac_curr))
                conn.commit()
                conn.close()
                st.success("Conto aggiunto!")
                st.rerun()

    with sub_f2:
        st.subheader("Registra Transazione (Spesa / Entrata)")
        if not acc_global_dict:
            st.warning("Crea prima un conto nella sezione Depositi & Conti.")
        else:
            with st.form("trans_form"):
                col_t1, col_t2 = st.columns(2)
                with col_t1: t_date = st.date_input("Data", value=date.today())
                with col_t2: sel_acc = st.selectbox("Conto", acc_global_names)
                
                default_curr = acc_global_dict[sel_acc]['currency']
                acc_id = acc_global_dict[sel_acc]['id']
                
                col_curr1, col_curr2, col_curr3 = st.columns(3)
                with col_curr1: t_type = st.selectbox("Tipo", ["Spesa (Uscita)", "Entrata"])
                with col_curr2: t_cat = st.selectbox("Categoria", expense_categories, index=0)
                with col_curr3:
                    curr_options = ["EUR", "JPY"]
                    default_index = curr_options.index(default_curr) if default_curr in curr_options else 0
                    t_curr = st.selectbox("Valuta", curr_options, index=default_index)
                
                t_desc = st.text_input("Descrizione / Dettaglio (opzionale)")
                t_amount = st.number_input(f"Importo ({t_curr})", value=0.0, step=1.0)
                
                if st.form_submit_button("💾 Registra Movimento"):
                    if t_amount > 0:
                        conn = get_connection()
                        cursor = conn.cursor()
                        if t_type == "Spesa (Uscita)":
                            cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (t_amount, acc_id))
                        else:
                            cursor.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (t_amount, acc_id))
                            
                        cursor.execute("INSERT INTO transactions (date, account_id, total_amount, currency, category, description) VALUES (?, ?, ?, ?, ?, ?)",
                                       (str(t_date), acc_id, t_amount, t_curr, t_cat, t_desc.strip() if t_desc else t_type))
                        conn.commit()
                        conn.close()
                        st.success("Movimento registrato con successo!")
                        st.rerun()

    with sub_f3:
        st.subheader("Giroconto / Trasferimento tra Miei Conti")
        st.caption("Sposta denaro tra i tuoi conti (es. Conto Corrente -> Conto Directa o Portafoglio). Non incide sulle spese mensili.")
        if len(acc_global_names) < 2:
            st.warning("Hai bisogno di almeno 2 conti registrati per poter fare un trasferimento.")
        else:
            with st.form("transfer_form"):
                tr_date = st.date_input("Data Trasferimento", value=date.today())
                col_tr1, col_tr2 = st.columns(2)
                with col_tr1: from_acc = st.selectbox("Dal conto (Mittente)", acc_global_names, index=0)
                with col_tr2: 
                    to_acc_index = 1 if len(acc_global_names) > 1 else 0
                    to_acc = st.selectbox("Al conto (Destinatario)", acc_global_names, index=to_acc_index)
                
                tr_amount = st.number_input("Importo da trasferire", value=0.0, step=10.0)
                tr_note = st.text_input("Causale", value="Giroconto / Spostamento su Broker")
                
                if st.form_submit_button("🔄 Esegui Giroconto"):
                    if from_acc == to_acc:
                        st.error("I conti devono essere differenti!")
                    elif tr_amount <= 0:
                        st.error("Inserisci un importo valido.")
                    else:
                        from_id = acc_global_dict[from_acc]['id']
                        from_curr = acc_global_dict[from_acc]['currency']
                        to_id = acc_global_dict[to_acc]['id']
                        to_curr = acc_global_dict[to_acc]['currency']
                        
                        final_to_amount = tr_amount
                        if from_curr != to_curr:
                            if from_curr == "EUR" and to_curr == "JPY": final_to_amount = tr_amount * eur_to_jpy
                            elif from_curr == "JPY" and to_curr == "EUR": final_to_amount = tr_amount * jpy_to_eur
                            
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (tr_amount, from_id))
                        cursor.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (final_to_amount, to_id))
                        cursor.execute("INSERT INTO transactions (date, account_id, total_amount, currency, category, description) VALUES (?, ?, ?, ?, ?, ?)",
                                       (str(tr_date), from_id, tr_amount, from_curr, "Giroconto", f"Da {from_acc} a {to_acc} - {tr_note}"))
                        conn.commit()
                        conn.close()
                        st.success("Giroconto eseguito con successo!")
                        st.rerun()

    with sub_f4:
        st.subheader("Spese & Entrate Ricorrenti (Modelli)")
        st.caption("Configura qui i flussi periodici (es. Stipendio in entrata, Affitto o Abbonamenti in uscita).")
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recurring_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                account_id INTEGER,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'EUR',
                frequency TEXT NOT NULL DEFAULT 'Mensile',
                day_of_month INTEGER NOT NULL DEFAULT 1,
                category TEXT NOT NULL DEFAULT 'Bollette',
                op_type TEXT NOT NULL DEFAULT 'Spesa',
                FOREIGN KEY (account_id) REFERENCES accounts (id)
            )
        ''')
        for col_def in [("category", "TEXT DEFAULT 'Bollette'"), ("op_type", "TEXT DEFAULT 'Spesa'")]:
            try:
                cursor.execute(f"ALTER TABLE recurring_expenses ADD COLUMN {col_def[0]} {col_def[1]}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            
        df_rec = pd.read_sql("""
            SELECT r.id, r.name AS 'Nome', r.op_type AS 'Tipo', a.name AS 'Conto', r.account_id, r.amount AS 'Importo', r.currency AS 'Valuta', r.category AS 'Categoria', r.day_of_month AS 'Giorno'
            FROM recurring_expenses r 
            LEFT JOIN accounts a ON r.account_id = a.id
        """, conn)
        conn.close()
        
        if not df_rec.empty:
            st.markdown("**Modifica Diretta Modelli Ricorrenti:**")
            edited_rec_df = st.data_editor(
                df_rec.drop(columns=['account_id']),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Spesa", "Entrata"], required=True),
                    "Categoria": st.column_config.SelectboxColumn("Categoria", options=expense_categories, required=True)
                },
                key="rec_data_editor"
            )
            
            if st.button("💾 Salva Modifiche Modelli"):
                conn = get_connection()
                cursor = conn.cursor()
                for _, row in edited_rec_df.iterrows():
                    r_id = row['id']
                    r_name = str(row['Nome']).strip().capitalize()
                    r_type = row['Tipo']
                    r_amt = float(row['Importo'])
                    r_curr = row['Valuta']
                    r_cat = row['Categoria']
                    r_day = int(row['Giorno'])
                    
                    cursor.execute("""
                        UPDATE recurring_expenses 
                        SET name = ?, op_type = ?, amount = ?, currency = ?, category = ?, day_of_month = ? 
                        WHERE id = ?
                    """, (r_name, r_type, r_amt, r_curr, r_cat, r_day, r_id))
                conn.commit()
                conn.close()
                st.success("Modelli ricorrenti aggiornati!")
                st.rerun()
            
            st.divider()
            st.markdown("**Esegui flusso ricorrente per questo mese:**")
            rec_dict = {row['Nome']: {'id': row['id'], 'type': row['Tipo'], 'amount': row['Importo'], 'currency': row['Valuta'], 'category': row['Categoria']} for _, row in df_rec.iterrows()}
            
            if rec_dict and acc_global_names:
                with st.form("pay_recurring_form"):
                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1: sel_rec_item = st.selectbox("Seleziona Modello", list(rec_dict.keys()))
                    with col_p2: sel_pay_acc = st.selectbox("Conto interessato", acc_global_names)
                    with col_p3: pay_date = st.date_input("Data", value=date.today())
                    
                    rec_info = rec_dict[sel_rec_item]
                    rec_type = rec_info['type']
                    rec_amt = rec_info['amount']
                    rec_curr = rec_info['currency']
                    rec_cat = rec_info['category']
                    
                    if st.form_submit_button("⚡ Esegui e Registra"):
                        acc_id_pay = acc_global_dict[sel_pay_acc]['id']
                        conn = get_connection()
                        cursor = conn.cursor()
                        
                        if rec_type == "Spesa":
                            cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (rec_amt, acc_id_pay))
                        else:
                            cursor.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (rec_amt, acc_id_pay))
                            
                        cursor.execute("INSERT INTO transactions (date, account_id, total_amount, currency, category, description) VALUES (?, ?, ?, ?, ?, ?)",
                                       (str(pay_date), acc_id_pay, rec_amt, rec_curr, rec_cat, f"Ricorrente ({rec_type}): {sel_rec_item}"))
                        conn.commit()
                        conn.close()
                        st.success(f"Flusso ricorrente '{sel_rec_item}' registrato con successo!")
                        st.rerun()
            
            st.divider()
            with st.form("del_rec_form"):
                st.markdown("**Elimina Modello Ricorrente**")
                del_rec_id = st.number_input("ID Modello da eliminare", value=0, step=1)
                if st.form_submit_button("❌ Elimina Modello"):
                    if del_rec_id > 0:
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM recurring_expenses WHERE id = ?", (del_rec_id,))
                        conn.commit()
                        conn.close()
                        st.success("Modello eliminato.")
                        st.rerun()
        else:
            st.info("Nessun flusso ricorrente configurato.")
            
        st.divider()
        if not acc_global_names:
            st.warning("Crea prima un conto.")
        else:
            with st.form("add_recurring_form"):
                st.markdown("**Crea Nuovo Modello Ricorrente (Spesa o Entrata)**")
                r_name = st.text_input("Nome (es. Stipendio, Affitto, Abbonamento Annuale)")
                col_r1, col_r2, col_r3 = st.columns(3)
                with col_r1: r_type = st.selectbox("Tipo", ["Spesa", "Entrata"])
                with col_r2: r_acc_name = st.selectbox("Conto", acc_global_names)
                with col_r3: r_curr = st.selectbox("Valuta", ["EUR", "JPY"])
                    
                col_r4, col_r5, col_r6 = st.columns(3)
                with col_r4: r_cat = st.selectbox("Categoria", expense_categories, index=2)
                with col_r5: r_amount = st.number_input("Importo", value=0.0, step=10.0)
                
                # NUOVA GESTIONE FREQUENZA FLUIDA
                with col_r6: 
                    r_freq = st.selectbox("Frequenza", ["Giornaliera", "Settimanale", "Mensile", "Annuale"])

                # Adattiamo il selettore del "giorno/intervallo" in base alla frequenza scelta
                if r_freq == "Giornaliera":
                    r_interval = 1
                    st.caption("🔄 Si ripeterà ogni giorno.")
                elif r_freq == "Settimanale":
                    r_interval = st.selectbox("Giorno della settimana", [
                        "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"
                    ])
                    # Mappiamo in un intero da 0 a 6
                    days_map = {"Lunedì": 0, "Martedì": 1, "Mercoledì": 2, "Giovedì": 3, "Venerdì": 4, "Sabato": 5, "Domenica": 6}
                    r_interval = days_map[r_interval]
                elif r_freq == "Mensile":
                    r_interval = st.number_input("Giorno del mese", value=1, min_value=1, max_value=31, step=1)
                else: # Annuale
                    r_interval = st.date_input("Data di riferimento annuale", value=date.today())
                    # Per semplicità di salvataggio SQLite, possiamo salvare la stringa "MM-DD" o trasformarla in un formato gestibile, oppure mantenere una data formattata come stringa nel DB.

                if st.form_submit_button("➕ Salva Modello") and r_name:
                    r_acc_id = acc_global_dict[r_acc_name]['id']
                    # Se annuale salviamo la data come stringa o gestiamo l'intervallo
                    val_to_save = str(r_interval) if r_freq == "Annuale" else int(r_interval)
                    
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO recurring_expenses (name, account_id, amount, currency, frequency, interval_value, category, op_type) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (r_name.strip().capitalize(), r_acc_id, r_amount, r_curr, r_freq, val_to_save, r_cat, r_type))
                    conn.commit()
                    conn.close()
                    st.success("Modello ricorrente flessibile aggiunto!")
                    st.rerun()

    with sub_f5:
        st.subheader("Storico Transazioni & Modifica Diretta")
        st.caption("Modifica direttamente le celle nella tabella sottostante.")
        
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE transactions ADD COLUMN category TEXT DEFAULT 'Spesa'")
            conn.commit()
        except sqlite3.OperationalError:
            pass
            
        df_t = pd.read_sql("""
            SELECT t.id, t.date AS 'Data', t.account_id, a.name AS 'Conto', t.total_amount AS 'Importo', t.currency AS 'Valuta', t.category AS 'Categoria', t.description AS 'Descrizione'
            FROM transactions t 
            LEFT JOIN accounts a ON t.account_id = a.id 
            ORDER BY t.date DESC
        """, conn)
        conn.close()
        
        if not df_t.empty:
            edited_df = st.data_editor(
                df_t.drop(columns=['account_id']),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Categoria": st.column_config.SelectboxColumn(
                        "Categoria",
                        options=expense_categories,
                        required=True
                    )
                },
                key="tx_data_editor"
            )
            
            if st.button("💾 Salva Modifiche Tabella Storico"):
                conn = get_connection()
                cursor = conn.cursor()
                
                for _, row in edited_df.iterrows():
                    tx_id = row['id']
                    new_date = str(row['Data'])
                    new_amount = float(row['Importo'])
                    new_cat = row['Categoria']
                    new_desc = str(row['Descrizione']) if pd.notna(row['Descrizione']) else ""
                    
                    cursor.execute("SELECT total_amount, account_id FROM transactions WHERE id = ?", (tx_id,))
                    old_rec = cursor.fetchone()
                    if old_rec:
                        old_amount, acc_id = old_rec
                        if old_amount != new_amount:
                            diff = old_amount - new_amount
                            cursor.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (diff, acc_id))
                            
                    cursor.execute("""
                        UPDATE transactions 
                        SET date = ?, total_amount = ?, category = ?, description = ? 
                        WHERE id = ?
                    """, (new_date, new_amount, new_cat, new_desc, tx_id))
                    
                conn.commit()
                conn.close()
                st.success("Modifiche salvate con successo!")
                st.rerun()
                
            st.divider()
            
            with st.form("del_tx_form_safe"):
                st.markdown("**Elimina Transazione e Storna Saldo**")
                del_id = st.number_input("ID Transazione da eliminare", value=0, step=1, key="del_tx_input_safe")
                if st.form_submit_button("❌ Elimina Transazione"):
                    if del_id > 0:
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT account_id, total_amount, description FROM transactions WHERE id = ?", (del_id,))
                        tx = cursor.fetchone()
                        if tx:
                            acc_id_tx, amt_tx, desc_tx = tx
                            cursor.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (amt_tx, acc_id_tx))
                            cursor.execute("DELETE FROM transactions WHERE id = ?", (del_id,))
                            conn.commit()
                            conn.close()
                            st.success("Transazione eliminata e saldo stornato.")
                            st.rerun()
                        else:
                            st.warning("ID transazione non trovato.")
        else:
            st.info("Nessuna transazione registrata.")

    with sub_f6:
        st.subheader("📊 Riepilogo Spese per Categoria")
        st.caption("Analizza quanto hai speso nel mese selezionato (i giroconti interni sono esclusi dal totale delle spese).")
        
        conn = get_connection()
        df_summary = pd.read_sql("""
            SELECT date, total_amount, currency, category AS 'Categoria' 
            FROM transactions
        """, conn)
        conn.close()
        
        if not df_summary.empty:
            df_summary['AnnoMese'] = df_summary['date'].astype(str).str.slice(0, 7)
            available_months = sorted(df_summary['AnnoMese'].unique(), reverse=True)
            
            selected_month = st.selectbox("Seleziona Mese", available_months, key="sum_month_sel")
            
            df_filtered = df_summary[(df_summary['AnnoMese'] == selected_month) & (df_summary['Categoria'] != 'Giroconto')]
            
            if not df_filtered.empty:
                st.markdown(f"### 📅 Report per il mese di: `{selected_month}`")
                
                grouped = df_filtered.groupby(['Categoria', 'currency'])['total_amount'].sum().reset_index()
                grouped.columns = ['Categoria', 'Valuta', 'Totale Speso']
                
                col_sum1, col_sum2 = st.columns([2, 1])
                with col_sum1:
                    st.dataframe(grouped, use_container_width=True, hide_index=True)
                    
                with col_sum2:
                    total_eur_calc = 0
                    for _, r in grouped.iterrows():
                        amt = r['Totale Speso']
                        curr = r['Valuta']
                        if curr == 'JPY':
                            total_eur_calc += amt * jpy_to_eur
                        else:
                            total_eur_calc += amt
                            
                    st.metric(label="Spesa Totale Stimata in EUR", value=f"€ {total_eur_calc:,.2f}")
            else:
                st.info(f"Nessuna transazione registrata per il mese {selected_month}.")
        else:
            st.info("Nessuna transazione registrata nello storico.")