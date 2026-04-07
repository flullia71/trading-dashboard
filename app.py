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

# --- 2. SIDEBAR ---
st.sidebar.header("📋 Radar Setup")
try:
    sheet_config = workbook.worksheet("Config")
except:
    sheet_config = workbook.add_worksheet(title="Config", rows="100", cols="5")
    sheet_config.update('A1', [['Ticker']])

records_config = sheet_config.get_all_records()
ticker_persistenti = [r['Ticker'].upper() for r in records_config if r.get('Ticker')]
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

# --- 3. CARICAMENTO DATI DIARIO ---
colonne_diario = ['Data', 'Ticker', 'Azione', 'Prezzo', 'Quantita', 'Controvalore', 'Valuta']
try:
    dati_s = sheet_main.get_all_records()
    if not dati_s:
        # Se il foglio è vuoto, inizializza le intestazioni
        sheet_main.update('A1', [colonne_diario])
        df_storico = pd.DataFrame(columns=colonne_diario)
    else:
        df_storico = pd.DataFrame(dati_s)
except Exception as e:
    st.error(f"Errore caricamento Diario: {e}")
    df_storico = pd.DataFrame(columns=colonne_diario)

# --- 4. INTERFACCIA TABS ---
st.title("📊 Trading Terminal Pro")
tab_scanner, tab_backtest, tab_diario = st.tabs(["🚀 Scanner & Portafoglio", "🧪 Backtesting", "📓 Diario"])

# --- TAB SCANNER & PORTAFOGLIO ---
with tab_scanner:
    if st.button("🔍 Avvia Analisi in Tempo Reale", type="primary"):
        pnl_container = st.container()
        st.markdown("---")
        cols = st.columns(3)
        p_euro, p_usd = 0.0, 0.0
        
        for i, ticker in enumerate(tickers_attuali):
            try:
                # Analisi Portafoglio per Ticker
                quote, cash_flow, valuta_t = 0, 0.0, "$"
                if not df_storico.empty and 'Ticker' in df_storico.columns:
                    st_t = df_storico[df_storico['Ticker'] == ticker].copy()
                    if not st_t.empty:
                        st_t['Quantita'] = pd.to_numeric(st_t['Quantita'], errors='coerce').fillna(0)
                        st_t['Controvalore'] = pd.to_numeric(st_t['Controvalore'], errors='coerce').fillna(0)
                        
                        q_buy = st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita'].sum()
                        q_sell = st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita'].sum()
                        quote = q_buy - q_sell
                        cash_flow = st_t['Controvalore'].sum()
                        valuta_t = st_t.iloc[0]['Valuta']

                # Market Data
                s = yf.Ticker(ticker); h = s.history(period="2y")
                if h.empty: continue
                
                px = h.iloc[-1]['Close']
                valore_attuale = px * quote
                pnl_u = cash_flow + valore_attuale if quote > 0 else 0.0
                
                if valuta_t == "€": p_euro += pnl_u
                else: p_usd += pnl_u

                with cols[i % 3]:
                    st.subheader(f"🏢 {ticker}")
                    st.write(f"Prezzo: {px:.2f} {valuta_t}")
                    if quote > 0:
                        col = "green" if pnl_u >= 0 else "red"
                        st.markdown(f"**P&L:** :{col}[{pnl_u:.2f} {valuta_t}]")
                        st.caption(f"Q.tà: {int(quote)} | Valore: {valore_attuale:.2f}")
                    st.markdown("---")
            except: pass
        
        with pnl_container:
            c1, c2 = st.columns(2)
            c1.metric("P&L Totale Euro", f"{p_euro:.2f} €")
            c2.metric("P&L Totale USD", f"{p_usd:.2f} $")

# --- TAB DIARIO (FIXED) ---
with tab_diario:
    st.subheader("📝 Registra Nuova Transazione")
    with st.form("trade_form", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        f_t = c1.text_input("Ticker").upper()
        f_a = c2.selectbox("Azione", ["Acquisto (Buy)", "Vendita (Sell)"])
        f_p = c3.number_input("Prezzo", min_value=0.01)
        f_q = c4.number_input("Quantità", min_value=1)
        f_v = c5.selectbox("Valuta", ["$", "€"])
        if st.form_submit_button("💾 Salva nel Cloud"):
            if f_t:
                m = -1 if f_a == "Acquisto (Buy)" else 1
                nuova_riga = [datetime.now().strftime("%Y-%m-%d %H:%M"), f_t, f_a, f_p, f_q, f_p*f_q*m, f_v]
                sheet_main.append_row(nuova_riga)
                st.success("Operazione registrata!")
                st.rerun()

    st.markdown("---")
    st.subheader("📓 Storico Operazioni")
