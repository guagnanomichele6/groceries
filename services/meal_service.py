import json
import requests
from datetime import date
import streamlit as st
from database.connection import get_connection
from services.inventory_service import consume_inventory_item

def process_past_slots():
    """Automatically processes past unconsumed meal slots, updating inventory."""
    today_str = str(date.today())
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, meal_id, context FROM calendar_schedule WHERE date < ? AND consumed = 0", (today_str,))
    past_items = cursor.fetchall()
    
    for sid, m_id, context in past_items:
        if m_id and context in ['A Casa (Canonico)', 'Offerto da Me']:
            cursor.execute("SELECT item_name, quantity, unit FROM meal_ingredients WHERE meal_id = ?", (m_id,))
            ingredients = cursor.fetchall()
            for item_name, qty, recipe_unit in ingredients:
                consume_inventory_item(cursor, item_name, qty, recipe_unit)
        cursor.execute("UPDATE calendar_schedule SET consumed = 1 WHERE id = ?", (sid,))
    conn.commit()
    conn.close()

def parse_natural_language_schedule(text_input):
    """Sends natural language text to local Ollama instance to parse meal schedules."""
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
    """Saves parsed AI schedule events into the database."""
    conn = get_connection()
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