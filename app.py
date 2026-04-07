import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import requests

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Trading Terminal Pro", layout="wide")

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

# --- 2. SIDEBAR ---
st.sidebar.header("📋 Radar Setup")
records = sheet_config.get_all_records()
ticker_persistenti = [r['Ticker'].upper() for r in records if r.get('Ticker')]
lista_str = ", ".join(ticker_persistenti) if ticker_persistenti else "AAPL, NVDA, UCG.MI"
tickers_input = st.sidebar.text_area("Azioni da monitorare:", value=lista_str, height=150)
tickers_attuali = [t.strip().upper() for t in tickers_input.replace('\n', ',').split(',') if t.strip()]

if st.sidebar.button("💾 Salva Lista Cloud"):
    sheet_config.clear()
    sheet_config.update('A1', [['Ticker']])
    sheet_config.update('A2', [[t] for t in tickers_attuali])
    st.sidebar.success("Sincronizzata!"); st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("🎯 Strategia Attiva")
strategia = st.sidebar.radio("Seleziona Motore:", ["Pullback (RSI + Bollinger)", "Trend Crossover (MACD)"])
ema_len = st.sidebar.number_input("Periodo EMA (Trend)", value=200)

st.sidebar.markdown("---")
st.sidebar.header("💰 Money Management")
capitale_totale = st.sidebar.number_input("Capitale Totale Disponibile", value=10000)
rischio_percent = st.sidebar.slider("Investimento per trade %", 1, 20, 5)
cap_trade = capitale_totale * (rischio_percent / 100)

dati_s = sheet_main.get_all_records()
df_storico = pd.DataFrame(dati_s) if dati_s else pd.DataFrame(columns=['Data','Ticker','Azione','Prezzo','Quantita','Controvalore','Valuta'])

# --- 3. LOGICA TABS ---
st.title("📊 Trading Terminal Pro")
tab_scanner, tab_backtest, tab_diario = st.tabs(["🚀 Scanner & Portafoglio", "🧪 Backtesting", "📓 Diario"])

with tab_scanner:
    if st.button("🔍 Avvia Analisi in Tempo Reale", type="primary"):
        st.subheader("💰 Sintesi Real-Time Portafoglio")
        pnl_container = st.container()
        st.markdown("---")
        
        cols = st.columns(3)
        pnl_totale_euro = 0.0
        pnl_totale_dollaro = 0.0
        
        for i, ticker in enumerate(tickers_attuali):
            try:
                # Dati dal foglio
                quote = 0
                cash_flow = 0.0
                valuta_t = "$"
                if not df_storico.empty and 'Ticker' in df_storico.columns:
                    st_t = df_storico[df_storico['Ticker'] == ticker]
                    q_buy = pd.to_numeric(st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita']).sum()
                    q_sell = pd.to_numeric(st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita']).sum()
                    quote = q_buy - q_sell
                    cash_flow = pd.to_numeric(st_t['Controvalore']).sum()
                    if not st_t.empty: valuta_t = st_t.iloc[0]['Valuta']

                # Dati dal mercato
                s = yf.Ticker(ticker); h = s.history(period="2y")
                if h.empty: continue
                
                px = h.iloc[-1]['Close']
                valore_attuale = px * quote
                pnl_unrealized = cash_flow + valore_attuale if quote > 0 else 0.0
                
                # Accumulo P&L Totale
                if valuta_t == "€": pnl_totale_euro += pnl_unrealized
                else: pnl_totale_dollaro += pnl_unrealized

                # Calcolo Indicatori (Logica MACD/Pullback omessa qui per brevità, resta uguale a prima)
                # ... [Inserire qui i calcoli EMA, RSI, MACD come nel file precedente] ...

                with cols[i % 3]:
                    st.subheader(f"🏢 {ticker}")
                    st.write(f"Prezzo: {px:.2f} {valuta_t}")
                    
                    if quote > 0:
                        color = "green" if pnl_unrealized >= 0 else "red"
                        st.markdown(f"**P&L Attuale:** :{color}[{pnl_unrealized:.2f} {valuta_t}]")
                        st.info(f"Quantità: {int(quote)} | Valore: {valore_attuale:.2f}")
                    else:
                        st.write("⚪ Nessuna posizione aperta")
                    st.markdown("---")
            except: pass
        
        # Mostra P&L globale nel container in alto
        with pnl_container:
            c1, c2 = st.columns(2)
            c1.metric("P&L Totale Euro", f"{pnl_totale_euro:.2f} €")
            c2.metric("P&L Totale Dollaro", f"{pnl_totale_dollaro:.2f} $")

# ... [Resto del codice Backtesting e Diario uguale] ...
