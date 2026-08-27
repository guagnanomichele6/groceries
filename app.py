from datetime import date
import os
import sqlite3
from database import DB_NAME, init_db
import pandas as pd
import requests
import streamlit as st

# Allinea il DB all'avvio
init_db()

st.set_page_config(page_title="Personal ERP", page_icon="📊", layout="centered")


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

st.title("Personal ERP: Budget & Food")
st.caption(f"💱 Tasso di cambio live: 1 € = {eur_to_jpy:.2f} ¥")

menu = st.sidebar.selectbox(
    "Seleziona",
    ["Patrimonio & Conti", "Dispensa", "Registra Spesa", "Storico Spese"],
)

# ==========================================
# SEZIONE: PATRIMONIO & CONTI
# ==========================================
if menu == "Patrimonio & Conti":
  st.header("I tuoi Conti")

  conn = sqlite3.connect(DB_NAME)
  df_accounts = pd.read_sql(
      "SELECT id, name AS 'Conto', type AS 'Tipo', balance AS 'Saldo', currency"
      " AS 'Valuta' FROM accounts",
      conn,
  )
  conn.close()

  if not df_accounts.empty:
    total_in_eur = 0.0
    for _, row in df_accounts.iterrows():
      if row["Valuta"] == "JPY":
        total_in_eur += row["Saldo"] * jpy_to_eur
      else:
        total_in_eur += row["Saldo"]

    st.metric(label="Patrimonio Totale Stimato", value=f"€ {total_in_eur:,.2f}")
    st.divider()

    st.subheader("Modifica Rapida Conti")
    with st.form("accounts_editor_form"):
      edited_accounts = st.data_editor(
          df_accounts, use_container_width=True, hide_index=True
      )
      save_acc = st.form_submit_button("Salva Modifiche Conti")

      if save_acc:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accounts")
        for _, row in edited_accounts.iterrows():
          if pd.notna(row["Conto"]) and str(row["Conto"]).strip() != "":
            cursor.execute(
                "INSERT INTO accounts (id, name, type, balance, currency)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    int(row["id"]) if pd.notna(row["id"]) else None,
                    str(row["Conto"]).strip(),
                    (
                        str(row["Tipo"])
                        if pd.notna(row["Tipo"])
                        else "Conto Corrente"
                    ),
                    float(row["Saldo"]) if pd.notna(row["Saldo"]) else 0.0,
                    str(row["Valuta"]) if pd.notna(row["Valuta"]) else "EUR",
                ),
            )
        conn.commit()
        conn.close()
        st.success("Conti aggiornati con successo!")
        st.rerun()
  else:
    st.info("Nessun conto registrato.")

  st.divider()
  with st.form("add_account_form", clear_on_submit=True):
    st.subheader("Aggiungi Nuovo Conto")
    name = st.text_input("Nome Conto (es. Revolut, MUFG, Contanti)")
    type_ = st.selectbox(
        "Tipo", ["Conto Corrente", "Contante", "Investimenti"]
    )
    currency = st.selectbox("Valuta", ["EUR", "JPY"])
    balance = st.number_input("Saldo Iniziale", value=0.0, step=100.0)

    submitted = st.form_submit_button("Aggiungi Conto")
    if submitted and name:
      conn = sqlite3.connect(DB_NAME)
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO accounts (name, type, balance, currency) VALUES (?,"
          " ?, ?, ?)",
          (name.strip(), type_, balance, currency),
      )
      conn.commit()
      conn.close()
      st.success(f"Conto '{name}' aggiunto!")
      st.rerun()

# ==========================================
# SEZIONE: DISPENSA
# ==========================================
elif menu == "Dispensa":
  st.header("La mia Dispensa")

  conn = sqlite3.connect(DB_NAME)
  df_pantry = pd.read_sql(
      "SELECT id, item_name AS 'Prodotto', quantity AS 'Quantità', unit AS"
      " 'Unità' FROM pantry",
      conn,
  )
  conn.close()

  if not df_pantry.empty:
    st.subheader("Modifica Rapida Dispensa")
    with st.form("pantry_editor_form"):
      edited_df = st.data_editor(
          df_pantry, use_container_width=True, hide_index=True
      )
      save_pantry = st.form_submit_button("Salva Modifiche Dispensa")

      if save_pantry:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pantry")
        for _, row in edited_df.iterrows():
          if (
              pd.notna(row["Prodotto"])
              and str(row["Prodotto"]).strip() != ""
              and float(row["Quantità"]) > 0
          ):
            cursor.execute(
                "INSERT INTO pantry (item_name, quantity, unit) VALUES (?,"
                " ?, ?)",
                (
                    str(row["Prodotto"]).strip().capitalize(),
                    float(row["Quantità"]),
                    str(row["Unità"]),
                ),
            )
        conn.commit()
        conn.close()
        st.success("Dispensa aggiornata!")
        st.rerun()
  else:
    st.info("Dispensa vuota.")

  st.divider()
  st.subheader("Aggiungi Prodotto Singolo")
  with st.form("add_pantry_form", clear_on_submit=True):
    item = st.text_input("Nome Prodotto")
    col1, col2 = st.columns(2)
    with col1:
      qty = st.number_input("Quantità", value=1.0, min_value=0.1, step=1.0)
    with col2:
      unit = st.selectbox("Unità", ["pezzi", "grammi", "litri", "kg", "ml"])

    submitted = st.form_submit_button("Aggiungi")
    if submitted and item:
      conn = sqlite3.connect(DB_NAME)
      cursor = conn.cursor()
      p_name = item.strip().capitalize()

      cursor.execute(
          "SELECT id, quantity FROM pantry WHERE item_name = ?", (p_name,)
      )
      existing = cursor.fetchone()

      if existing:
        cursor.execute(
            "UPDATE pantry SET quantity = quantity + ?, unit = ? WHERE id = ?",
            (qty, unit, existing[0]),
        )
      else:
        cursor.execute(
            "INSERT INTO pantry (item_name, quantity, unit) VALUES (?, ?, ?)",
            (p_name, qty, unit),
        )

      conn.commit()
      conn.close()
      st.success(f"'{p_name}' aggiornato in dispensa!")
      st.rerun()

# ==========================================
# SEZIONE: REGISTRA SPESA
# ==========================================
elif menu == "Registra Spesa":
  st.header("Registra Nuova Spesa (Multi-Articolo)")

  conn = sqlite3.connect(DB_NAME)
  df_accounts = pd.read_sql("SELECT id, name, currency FROM accounts", conn)
  conn.close()

  if df_accounts.empty:
    st.warning("Crea prima un conto nella sezione 'Patrimonio & Conti'.")
  else:
    col_a, col_b = st.columns(2)
    with col_a:
      expense_date = st.date_input("Data Spesa", value=date.today())
    with col_b:
      account_dict = {
          row["name"]: (row["id"], row["currency"])
          for _, row in df_accounts.iterrows()
      }
      selected_account_name = st.selectbox(
          "Paga con conto:", list(account_dict.keys())
      )
      acc_id, acc_currency = account_dict[selected_account_name]

    description = st.text_input(
        "Descrizione / Negozio (es. Supermercato, Konbini)"
    )
    total_amount = st.number_input(
        f"Costo Totale dello Scontrino ({acc_currency})",
        value=0.0,
        min_value=0.0,
        step=100.0 if acc_currency == "JPY" else 1.0,
    )

    st.divider()
    st.subheader("Articoli acquistati da aggiungere alla dispensa")

    if "cart_data" not in st.session_state:
      st.session_state.cart_data = pd.DataFrame(
          columns=["Prodotto", "Quantità", "Unità"]
      )

    with st.form("shopping_form"):
      edited_cart = st.data_editor(
          st.session_state.cart_data,
          num_rows="dynamic",
          use_container_width=True,
      )
      submit_expense = st.form_submit_button("Conferma e Registra Spesa")

      if submit_expense:
        if total_amount <= 0:
          st.error("Inserisci un importo totale valido per la spesa.")
        else:
          conn = sqlite3.connect(DB_NAME)
          cursor = conn.cursor()

          # 1. Scala importo dal conto
          cursor.execute(
              "UPDATE accounts SET balance = balance - ? WHERE id = ?",
              (total_amount, acc_id),
          )

          # 2. Registra transazione
          cursor.execute(
              "INSERT INTO transactions (date, account_id, total_amount,"
              " currency, description) VALUES (?, ?, ?, ?, ?)",
              (
                  str(expense_date),
                  acc_id,
                  total_amount,
                  acc_currency,
                  description or "Spesa",
              ),
          )
          tx_id = cursor.lastrowid

          # 3. Inserisci articoli e tracciali per eventuale rimozione futura
          added_count = 0
          for _, row in edited_cart.iterrows():
            if pd.notna(row["Prodotto"]) and str(row["Prodotto"]).strip() != "":
              p_name = str(row["Prodotto"]).strip().capitalize()
              p_qty = (
                  float(row["Quantità"]) if pd.notna(row["Quantità"]) else 1.0
              )
              p_unit = str(row["Unità"]) if pd.notna(row["Unità"]) else "pezzi"

              # Salva legame transazione <-> prodotto
              cursor.execute(
                  "INSERT INTO transaction_items (transaction_id, item_name,"
                  " quantity, unit) VALUES (?, ?, ?, ?)",
                  (tx_id, p_name, p_qty, p_unit),
              )

              # Aggiorna dispensa
              cursor.execute(
                  "SELECT id, quantity FROM pantry WHERE item_name = ?",
                  (p_name,),
              )
              existing = cursor.fetchone()
              if existing:
                cursor.execute(
                    "UPDATE pantry SET quantity = quantity + ?, unit = ?"
                    " WHERE id = ?",
                    (p_qty, p_unit, existing[0]),
                )
              else:
                cursor.execute(
                    "INSERT INTO pantry (item_name, quantity, unit) VALUES (?,"
                    " ?, ?)",
                    (p_name, p_qty, p_unit),
                )
              added_count += 1

          conn.commit()
          conn.close()

          st.session_state.cart_data = pd.DataFrame(
              columns=["Prodotto", "Quantità", "Unità"]
          )
          st.success(
              f"Spesa registrata! {added_count} articoli aggiunti e collegati"
              " alla transazione."
          )
          st.rerun()

# ==========================================
# SEZIONE: STORICO SPESE
# ==========================================
elif menu == "Storico Spese":
  st.header("Storico Transazioni")

  conn = sqlite3.connect(DB_NAME)
  df_trans = pd.read_sql(
      """
        SELECT t.id, t.date AS 'Data', t.account_id, a.name AS 'Conto', t.total_amount AS 'Importo', t.currency AS 'Valuta', t.description AS 'Descrizione'
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        ORDER BY t.date DESC
    """,
      conn,
  )
  conn.close()

  if not df_trans.empty:
    st.dataframe(
        df_trans[
            ["id", "Data", "Conto", "Descrizione", "Importo", "Valuta"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.subheader("Elimina Transazione Errata")
    st.caption(
        "Eliminando la transazione: l'importo verrà rimborsato sul conto e i"
        " prodotti acquistati verranno scalati/rimossi dalla dispensa."
    )

    with st.form("delete_trans_form"):
      trans_id_to_delete = st.number_input(
          "Inserisci l'ID della transazione da eliminare", value=0, step=1
      )
      delete_btn = st.form_submit_button(
          "Elimina transazione, ripristina saldo e rimuovi articoli"
      )

      if delete_btn and trans_id_to_delete > 0:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT account_id, total_amount FROM transactions WHERE id = ?",
            (trans_id_to_delete,),
        )
        tx = cursor.fetchone()

        if tx:
          acc_id, amount = tx

          # 1. Rimborsa il saldo sul conto
          cursor.execute(
              "UPDATE accounts SET balance = balance + ? WHERE id = ?",
              (amount, acc_id),
          )

          # 2. Recupera e scala gli articoli comprati con questa spesa
          cursor.execute(
              "SELECT item_name, quantity FROM transaction_items WHERE"
              " transaction_id = ?",
              (trans_id_to_delete,),
          )
          purchased_items = cursor.fetchall()

          for item_name, qty in purchased_items:
            cursor.execute(
                "SELECT id, quantity FROM pantry WHERE item_name = ?",
                (item_name,),
            )
            pantry_item = cursor.fetchone()
            if pantry_item:
              p_id, curr_qty = pantry_item
              new_qty = curr_qty - qty
              if new_qty > 0:
                cursor.execute(
                    "UPDATE pantry SET quantity = ? WHERE id = ?",
                    (new_qty, p_id),
                )
              else:
                cursor.execute("DELETE FROM pantry WHERE id = ?", (p_id,))

          # 3. Elimina il dettaglio articoli e la transazione
          cursor.execute(
              "DELETE FROM transaction_items WHERE transaction_id = ?",
              (trans_id_to_delete,),
          )
          cursor.execute(
              "DELETE FROM transactions WHERE id = ?", (trans_id_to_delete,)
          )

          conn.commit()
          conn.close()
          st.success(
              f"Transazione #{trans_id_to_delete} cancellata: saldo"
              " ripristinato e dispensa allineata!"
          )
          st.rerun()
        else:
          conn.close()
          st.error("ID transazione non trovato.")
  else:
    st.info("Nessuna spesa registrata finora.")