import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import json
import os

# Caricamento sicuro delle variabili
gcp_raw = os.environ.get("GCP_SERVICE_ACCOUNT", "")
sheet_url = os.environ.get("GOOGLE_SHEET_URL", "")
token = os.environ.get("TELEGRAM_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

if not gcp_raw:
    print("ERRORE: La variabile GCP_SERVICE_ACCOUNT è vuota!")
    exit(1)

try:
    creds_dict = json.loads(gcp_raw)
except Exception as e:
    print(f"ERRORE: Il segreto GCP_SERVICE_ACCOUNT non è un JSON valido. Dettaglio: {e}")
    print(f"Contenuto ricevuto (primi 10 caratteri): {gcp_raw[:10]}")
    exit(1)

# ... resto del codice uguale a prima ...
