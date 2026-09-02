import requests
import streamlit as st

@st.cache_data(ttl=3600)
def get_exchange_rate(base="EUR", target="JPY"):
    """Fetches live exchange rate using Frankfurter API with caching."""
    try:
        url = f"https://api.frankfurter.app/latest?from={base}&to={target}"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            return response.json()["rates"][target]
    except Exception:
        pass
    return 184.98