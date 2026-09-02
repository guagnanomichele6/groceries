import streamlit as st
import shutil
import os
from datetime import datetime

# Import della struttura modulare
from database.scheme import initialize_database
from services.currency_service import get_exchange_rate
from services.meal_service import process_past_slots

# Import delle viste UI
from ui.tab_finance import render_finance_tab
from ui.tab_possessions import render_possessions_tab
from ui.tab_meals import render_meals_tab
from ui.tab_settings import render_settings_tab

# Inizializzazione database all'avvio
initialize_database()
process_past_slots()

DB_NAME = "finance_food.db"

st.set_page_config(page_title="Personal ERP", page_icon="📊", layout="wide")

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

st.title("Personal ERP")
st.caption(f"💱 Tasso di cambio live: 1 € = {eur_to_jpy:.2f} ¥")

# Le 4 tab principali
tab_finanza, tab_possedimenti, tab_pasti, tab_impostazioni = st.tabs([
    "💰 Finanza", 
    "📦 Possedimenti", 
    "🍳 Pasti", 
    "⚙️ Impostazioni"
])

with tab_finanza:
    render_finance_tab(eur_to_jpy, jpy_to_eur)

with tab_possedimenti:
    render_possessions_tab()

with tab_pasti:
    render_meals_tab(create_database_backup)

with tab_impostazioni:
    render_settings_tab(DB_NAME, create_database_backup)