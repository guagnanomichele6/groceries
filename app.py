import streamlit as st
import sqlite3
import pandas as pd

DB_NAME = "finance_food.db"

st.set_page_config(page_title="Personal ERP", page_icon="📊", layout="centered")

st.title("Personal ERP: Budget & Food")

# Sidebar per navigare tra le sezioni
menu = st.sidebar.selectbox("Seleziona", ["Patrimonio & Conti", "Dispensa"])

if menu == "Patrimonio & Conti":
    st.header("I tuoi Conti")
    
    conn = sqlite3.connect(DB_NAME)
    df_accounts = pd.read_sql("SELECT name AS 'Conto', type AS 'Tipo', balance AS 'Saldo (€)' FROM accounts", conn)
    conn.close()
    
    if not df_accounts.empty:
        st.dataframe(df_accounts, use_container_width=True, hide_index=True)
    else:
        st.info("Nessun conto registrato. Aggiungine uno qui sotto.")
        
    st.divider()
    
    with st.form("add_account_form", clear_on_submit=True):
        st.subheader("Aggiungi Conto")
        name = st.text_input("Nome Conto (es. Revolut, Contanti)")
        type_ = st.selectbox("Tipo", ["Conto Corrente", "Contante", "Investimenti"])
        balance = st.number_input("Saldo Iniziale (€)", value=0.0)
        
        submitted = st.form_submit_button("Aggiungi Conto")
        if submitted and name:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO accounts (name, type, balance) VALUES (?, ?, ?)", (name, type_, balance))
            conn.commit()
            conn.close()
            st.success(f"Conto '{name}' aggiunto!")
            st.rerun()

elif menu == "Dispensa":
    st.header("La mia Dispensa")
    
    conn = sqlite3.connect(DB_NAME)
    df_pantry = pd.read_sql("SELECT id, item_name AS 'Prodotto', quantity AS 'Quantità', unit AS 'Unità' FROM pantry", conn)
    conn.close()
    
    if not df_pantry.empty:
        st.subheader("Modifica Rapida Dispensa")
        st.caption("Puoi modificare direttamente i valori nella tabella qui sotto:")
        
        # Usiamo data_editor per rendere la tabella interattiva e modificabile
        edited_df = st.data_editor(
            df_pantry, 
            use_container_width=True, 
            hide_index=True,
            num_rows="dynamic", # Permette anche di eliminare righe se necessario
            key="pantry_editor"
        )
        
        # Bottone per salvare le modifiche fatte nella tabella
        if st.button("Salva Modifiche Tabella"):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            # Svuotiamo e riscriviamo la tabella per semplicità di prototipo, oppure aggiorniamo
            cursor.execute("DELETE FROM pantry")
            for _, row in edited_df.iterrows():
                if pd.notna(row['Prodotto']) and str(row['Prodotto']).strip() != "":
                    cursor.execute(
                        "INSERT INTO pantry (item_name, quantity, unit) VALUES (?, ?, ?)",
                        (str(row['Prodotto']).strip().capitalize(), float(row['Quantità']), str(row['Unità']))
                    )
            conn.commit()
            conn.close()
            st.success("Dispensa aggiornata con successo!")
            st.rerun()
            
    else:
        st.info("La dispensa è attualmente vuota.")
        
    st.divider()
    
    st.subheader("Aggiungi Nuovo Prodotto")
    # Form con valori iniziali a 0 o vuoti come richiesto
    with st.form("add_pantry_form", clear_on_submit=True):
        item = st.text_input("Nome Prodotto (es. Latte, Riso, Pollo)")
        
        col1, col2 = st.columns(2)
        with col1:
            # Valore di default a 0.0 finché non si inserisce
            qty = st.number_input("Quantità", value=0.0, step=1.0)
        with col2:
            unit = st.selectbox("Unità", ["pezzi", "grammi", "litri", "kg", "ml"])
            
        submitted = st.form_submit_button("Aggiungi in Dispensa")
        
        if submitted and item:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO pantry (item_name, quantity, unit) VALUES (?, ?, ?)", 
                (item.strip().capitalize(), qty, unit)
            )
            conn.commit()
            conn.close()
            
            st.success(f"'{item}' aggiunto!")
            st.rerun()