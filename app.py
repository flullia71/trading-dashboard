import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import requests

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Trading Terminal Pro", layout="wide")

# --- FUNZIONI UTILI ---
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

# Connessione GSheets
client = get_google_sheet_client()
sheet_url = st.secrets["google_sheet_url"]
workbook = client.open_by_url(sheet_url)
sheet_main = workbook.sheet1
try:
    sheet_config = workbook.worksheet("Config")
except:
    sheet_config = workbook.add_worksheet(title="Config", rows="100", cols="5")
    sheet_config.update('A1', [['Ticker']])

# --- SIDEBAR (PARAMETRI) ---
st.sidebar.header("📋 Setup & Parametri")
ticker_persistenti = [r['Ticker'].upper() for r in sheet_config.get_all_records() if r.get('Ticker')]
lista_str = ", ".join(ticker_persistenti) if ticker_persistenti else "AAPL, NVDA, UCG.MI"
tickers_input = st.sidebar.text_area("Ticker Monitorati:", value=lista_str, height=100)
tickers_attuali = [t.strip().upper() for t in tickers_input.replace('\n', ',').split(',') if t.strip()]

if st.sidebar.button("💾 Salva Lista Cloud"):
    sheet_config.clear()
    sheet_config.update('A1', [['Ticker']])
    sheet_config.update('A2', [[t] for t in tickers_attuali])
    st.sidebar.success("Sincronizzato!"); st.rerun()

ema_len = st.sidebar.number_input("EMA Trend", value=200)
rsi_buy = st.sidebar.slider("RSI Acquisto", 10, 50, 40)
rsi_sell = st.sidebar.slider("RSI Vendita", 50, 90, 70)
capitale_iniziale = st.sidebar.number_input("Capitale Test (Backtest)", value=10000)

# --- CARICAMENTO DATI ---
dati_s = sheet_main.get_all_records()
df_storico = pd.DataFrame(dati_s) if dati_s else pd.DataFrame(columns=['Data','Ticker','Azione','Prezzo','Quantita','Controvalore','Valuta'])

# --- INTERFACCIA TABS ---
st.title("📊 Trading Terminal Pro")
tab_scan, tab_backtest, tab_diario = st.tabs(["🚀 Scanner", "🧪 Backtesting", "📓 Diario"])

# --- TAB 1: SCANNER (Logica esistente) ---
with tab_scan:
    if st.button("🔍 Avvia Scansione", type="primary"):
        cols = st.columns(3)
        for i, ticker in enumerate(tickers_attuali):
            try:
                # Logica Portfolio e Segnali (omessa per brevità ma inclusa nel tuo codice reale)
                s = yf.Ticker(ticker); h = s.history(period="2y")
                if h.empty: continue
                # Calcoli... (EMA, RSI, BB)
                # Invio Telegram se segnale...
                with cols[i%3]: st.write(f"🏢 **{ticker}** in analisi...")
            except: pass

# --- TAB 2: BACKTESTING (NUOVA!) ---
with tab_backtest:
    st.subheader("Simulazione Strategia Storica")
    sel_ticker = st.selectbox("Scegli un ticker per il test:", tickers_attuali)
    periodo_test = st.radio("Periodo di analisi:", ["2y", "5y", "max"], horizontal=True)
    
    if st.button("🧪 Esegui Stress Test"):
        data = yf.Ticker(sel_ticker).history(period=periodo_test)
        if len(data) > ema_len:
            # Calcolo Indicatori
            data['EMA'] = data['Close'].ewm(span=ema_len, adjust=False).mean()
            sma = data['Close'].rolling(20).mean(); std = data['Close'].rolling(20).std()
            data['BBL'] = sma - (std * 2); data['BBU'] = sma + (std * 2)
            delta = data['Close'].diff()
            up = delta.clip(lower=0); dw = -1*delta.clip(upper=0)
            data['RSI'] = 100 - (100/(1+(up.ewm(com=13).mean()/dw.ewm(com=13).mean())))
            
            # Simulazione
            posizioni = []; pnl = []; capitale = capitale_iniziale; in_posizione = False; q_te = 0
            
            for i in range(ema_len, len(data)):
                row = data.iloc[i]; row_prev = data.iloc[i-1]
                # Segnale BUY
                if not in_posizione and (row['Close'] > row['EMA']) and (row['Close'] <= row['BBL']) and (row['RSI'] < rsi_buy):
                    q_te = capitale // row['Close']
                    capitale -= q_te * row['Close']
                    posizioni.append({'Entrata': row.name, 'Prezzo Entrata': row['Close']})
                    in_posizione = True
                # Segnale SELL
                elif in_posizione and (row['Close'] >= row['BBU'] or row['RSI'] > rsi_sell):
                    capitale += q_te * row['Close']
                    posizioni[-1].update({'Uscita': row.name, 'Prezzo Uscita': row['Close'], 'Profitto': (row['Close'] - posizioni[-1]['Prezzo Entrata']) * q_te})
                    in_posizione = False
            
            # Risultati
            if posizioni:
                df_res = pd.DataFrame([p for p in posizioni if 'Uscita' in p])
                if not df_res.empty:
                    st.success(f"Test Completato su {sel_ticker}!")
                    c1, c2, c3 = st.columns(3)
                    win_rate = (df_res['Profitto'] > 0).mean() * 100
                    profitto_tot = df_res['Profitto'].sum()
                    c1.metric("Profitto Totale", f"{profitto_tot:.2f} €/$")
                    c2.metric("Win Rate", f"{win_rate:.1f}%")
                    c3.metric("N° Operazioni", len(df_res))
                    
                    st.line_chart(df_res['Profitto'].cumsum())
                    st.dataframe(df_res)
                else: st.warning("Nessuna operazione chiusa nel periodo.")
            else: st.warning("La strategia non ha generato segnali nel periodo scelto.")

# --- TAB 3: DIARIO (Logica esistente) ---
with tab_diario:
    # Form salvataggio trade...
    st.dataframe(df_storico)
