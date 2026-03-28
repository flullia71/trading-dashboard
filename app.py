import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Trading Terminal Pro", layout="wide")

# --- CONNESSIONE GOOGLE SHEETS ---
@st.cache_resource
def get_google_sheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

client = get_google_sheet_client()
sheet_url = st.secrets["google_sheet_url"]
workbook = client.open_by_url(sheet_url)
sheet_main = workbook.sheet1 # Foglio dei Trade

try:
    sheet_config = workbook.worksheet("Config") # Foglio dei Ticker
except:
    sheet_config = workbook.add_worksheet(title="Config", rows="100", cols="5")
    sheet_config.update('A1', [['Ticker']])

# Funzioni Cloud
def carica_ticker_config():
    records = sheet_config.get_all_records()
    return [r['Ticker'].upper() for r in records if r.get('Ticker')]

def salva_lista_ticker_cloud(lista_nuova):
    sheet_config.clear()
    sheet_config.update('A1', [['Ticker']])
    formattati = [[t] for t in lista_nuova]
    sheet_config.update('A2', formattati)

def carica_storico():
    dati = sheet_main.get_all_records()
    return pd.DataFrame(dati) if dati else pd.DataFrame(columns=['Data', 'Ticker', 'Azione', 'Prezzo', 'Quantita', 'Controvalore', 'Valuta'])

# --- CARICAMENTO DATI ---
ticker_persistenti = carica_ticker_config()
df_storico = carica_storico()

# --- SIDEBAR (PARAMETRI RIPRISTINATI) ---
st.sidebar.header("📋 Radar Setup")
lista_ticker_str = ", ".join(ticker_persistenti) if ticker_persistenti else "AAPL, NVDA, UCG.MI"
tickers_input = st.sidebar.text_area("Azioni da monitorare:", value=lista_ticker_str, height=150)
tickers_attuali = [t.strip().upper() for t in tickers_input.replace('\n', ',').split(',') if t.strip()]

if st.sidebar.button("💾 Salva Lista nel Cloud"):
    salva_lista_ticker_cloud(tickers_attuali)
    st.sidebar.success("Lista sincronizzata!")
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Parametri Modello")
ema_len = st.sidebar.number_input("Periodo EMA (Trend)", value=200)
bb_std = st.sidebar.slider("Dev. Standard Bollinger", 1.0, 4.0, 2.0, 0.1)
rsi_soglia_buy = st.sidebar.slider("Soglia RSI Acquisto", 10, 50, 40)
rsi_soglia_sell = st.sidebar.slider("Soglia RSI Vendita", 50, 90, 70)

st.sidebar.markdown("---")
capitale_totale = st.sidebar.number_input("Capitale Totale", value=10000)
rischio_percent = st.sidebar.slider("Investimento per trade %", 1, 20, 5)
capitale_per_trade = capitale_totale * (rischio_percent / 100)

# --- TABS ---
tab_scanner, tab_diario = st.tabs(["🚀 Scanner", "📓 Diario"])

with tab_scanner:
    if st.button("🔍 Scansiona Ora", type="primary"):
        cols = st.columns(3)
        for i, ticker in enumerate(tickers_attuali):
            try:
                # Controllo Portafoglio
                quote = 0
                if not df_storico.empty:
                    st_t = df_storico[df_storico['Ticker'] == ticker]
                    quote = pd.to_numeric(st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita']).sum() - \
                            pd.to_numeric(st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita']).sum()

                # Dati Market
                s = yf.Ticker(ticker)
                h = s.history(period="2y")
                if h.empty: continue
                
                # Calcoli Tecnici
                h['EMA'] = h['Close'].ewm(span=ema_len, adjust=False).mean()
                sma = h['Close'].rolling(20).mean(); std = h['Close'].rolling(20).std()
                h['BBL'] = sma - (std * bb_std); h['BBU'] = sma + (std * bb_std)
                d = h['Close'].diff(); u = d.clip(lower=0); dw = -1*d.clip(upper=0)
                h['RSI'] = 100 - (100/(1+(u.ewm(com=13).mean()/dw.ewm(com=13).mean())))
                
                last = h.iloc[-1]
                px = last['Close']; rsi = last['RSI']; ema_val = last['EMA']; bbl = last['BBL']; bbu = last['BBU']
