import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import requests

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Trading Terminal Pro", layout="wide")

# --- 2. FUNZIONI CORE ---
def manda_telegram(messaggio):
    try:
        token = st.secrets["telegram_token"]
        chat_id = st.secrets["telegram_chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={messaggio}&parse_mode=Markdown"
        requests.get(url)
    except: pass

@st.cache_resource
def get_google_sheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

client = get_google_sheet_client()
sheet_url = st.secrets["google_sheet_url"]
workbook = client.open_by_url(sheet_url)
sheet_main = workbook.sheet1
try:
    sheet_config = workbook.worksheet("Config")
except:
    sheet_config = workbook.add_worksheet(title="Config", rows="100", cols="5")
    sheet_config.update('A1', [['Ticker']])

# --- 3. SIDEBAR (PANNELLO COMANDI) ---
st.sidebar.header("📋 Radar Setup")
ticker_persistenti = [r['Ticker'].upper() for r in sheet_config.get_all_records() if r.get('Ticker')]
lista_str = ", ".join(ticker_persistenti) if ticker_persistenti else "AAPL, NVDA, UCG.MI"
tickers_input = st.sidebar.text_area("Azioni da monitorare:", value=lista_str, height=150)
tickers_attuali = [t.strip().upper() for t in tickers_input.replace('\n', ',').split(',') if t.strip()]

if st.sidebar.button("💾 Salva Lista nel Cloud"):
    sheet_config.clear()
    sheet_config.update('A1', [['Ticker']])
    sheet_config.update('A2', [[t] for t in tickers_attuali])
    st.sidebar.success("Lista sincronizzata!"); st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Parametri Modello")
ema_len = st.sidebar.number_input("Periodo EMA (Trend)", value=200)
rsi_soglia_buy = st.sidebar.slider("Soglia RSI Acquisto", 10, 50, 40)
rsi_soglia_sell = st.sidebar.slider("Soglia RSI Vendita", 50, 90, 70)

st.sidebar.markdown("---")
st.sidebar.header("💰 Money Management")
capitale_totale = st.sidebar.number_input("Capitale Totale Disponibile", value=10000)
rischio_percent = st.sidebar.slider("Investimento per trade %", 1, 20, 5)
capitale_per_trade = capitale_totale * (rischio_percent / 100)

# Caricamento Dati Iniziale
dati_s = sheet_main.get_all_records()
df_storico = pd.DataFrame(dati_s) if dati_s else pd.DataFrame(columns=['Data','Ticker','Azione','Prezzo','Quantita','Controvalore','Valuta'])

# --- 4. INTERFACCIA TABS ---
st.title("📊 Trading Terminal Pro")
tab_scanner, tab_backtest, tab_diario = st.tabs(["🚀 Scanner", "🧪 Backtesting", "📓 Diario"])

# --- SCHEDA 1: SCANNER ---
with tab_scanner:
    if st.button("🔍 Avvia Scansione Ora", type="primary"):
        st.write("Analisi in corso e invio notifiche...")
        cols = st.columns(3)
        for i, ticker in enumerate(tickers_attuali):
            try:
                # Controllo Portafoglio
                quote = 0
                if not df_storico.empty and 'Ticker' in df_storico.columns:
                    st_t = df_storico[df_storico['Ticker'] == ticker]
                    q_buy = pd.to_numeric(st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita']).sum()
                    q_sell = pd.to_numeric(st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita']).sum()
                    quote = q_buy - q_sell

                # Market Data
                s = yf.Ticker(ticker); h = s.history(period="2y")
                if h.empty: continue
                
                # Calcoli Tecnici
                h['EMA'] = h['Close'].ewm(span=ema_len, adjust=False).mean()
                sma = h['Close'].rolling(20).mean(); std = h['Close'].rolling(20).std()
                h['BBL'] = sma - (std * 2); h['BBU'] = sma + (std * 2)
                delta = h['Close'].diff(); up = delta.clip(lower=0); dw = -1 * delta.clip(upper=0)
                h['RSI'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / dw.ewm(com=13, adjust=False).mean())))
                
                last = h.iloc[-1]; px = last['Close']; r
