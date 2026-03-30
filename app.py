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

# --- SIDEBAR ---
st.sidebar.header("📋 Radar Setup")
records = sheet_config.get_all_records()
ticker_persistenti = [r['Ticker'].upper() for r in records if r.get('Ticker')]
lista_str = ", ".join(ticker_persistenti) if ticker_persistenti else "AAPL, NVDA, UCG.MI"
tickers_input = st.sidebar.text_area("Azioni da monitorare:", value=lista_str, height=150)
tickers_attuali = [t.strip().upper() for t in tickers_input.replace('\n', ',').split(',') if t.strip()]

if st.sidebar.button("💾 Salva Lista Cloud"):
    sheet_config.clear()
    sheet_config.update('A1', [['Ticker']])
    formattati = [[t] for t in tickers_attuali]
    sheet_config.update('A2', formattati)
    st.sidebar.success("Sincronizzata!"); st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("🎯 Motore di Ricerca")
strategia = st.sidebar.radio("Seleziona Strategia:", ["Pullback (RSI + Bollinger)", "Trend Crossover (MACD)"])

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Parametri Generali")
ema_len = st.sidebar.number_input("Periodo EMA (Trend)", value=200)
rsi_soglia_buy = st.sidebar.slider("Soglia RSI Buy (Solo Pullback)", 10, 50, 40)
rsi_soglia_sell = st.sidebar.slider("Soglia RSI Sell (Solo Pullback)", 50, 90, 70)

st.sidebar.markdown("---")
st.sidebar.header("💰 Money Management")
capitale_totale = st.sidebar.number_input("Capitale Totale Disponibile", value=10000)
rischio_percent = st.sidebar.slider("Investimento per trade %", 1, 20, 5)
capitale_per_trade = capitale_totale * (rischio_percent / 100)

dati_s = sheet_main.get_all_records()
df_storico = pd.DataFrame(dati_s) if dati_s else pd.DataFrame(columns=['Data','Ticker','Azione','Prezzo','Quantita','Controvalore','Valuta'])

# --- TABS ---
st.title("📊 Trading Terminal Pro")
tab_scanner, tab_backtest, tab_diario = st.tabs(["🚀 Scanner", "🧪 Backtesting", "📓 Diario"])

# --- SCHEDA 1: SCANNER ---
with tab_scanner:
    if st.button("🔍 Avvia Scansione Ora", type="primary"):
        st.write(f"Analisi in corso con strategia: **{strategia}**...")
        cols = st.columns(3)
        for i, ticker in enumerate(tickers_attuali):
            try:
                quote = 0
                if not df_storico.empty and 'Ticker' in df_storico.columns:
                    st_t = df_storico[df_storico['Ticker'] == ticker]
                    quote = pd.to_numeric(st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita']).sum() - pd.to_numeric(st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita']).sum()

                s = yf.Ticker(ticker); h = s.history(period="2y")
                if h.empty: continue
                
                # Calcoli Base
                h['EMA'] = h['Close'].ewm(span=ema_len, adjust=False).mean()
                
                # Calcoli Pullback (RSI + BB)
                sma = h['Close'].rolling(20).mean(); std = h['Close'].rolling(20).std()
                h['BBL'] = sma - (std * 2); h['BBU'] = sma + (std * 2)
                delta = h['Close'].diff(); up = delta.clip(lower=0); dw = -1 * delta.clip(upper=0)
                h['RSI'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / dw.ewm(com=13, adjust=False).mean())))
                
                # Calcoli MACD
                h['EMA_12'] = h['Close'].ewm(span=12, adjust=False).mean()
                h['EMA_26'] = h['Close'].ewm(span=26, adjust=False).mean()
                h['MACD'] = h['EMA_12'] - h['EMA_26']
                h['MACD_Signal'] = h['MACD'].ewm(span=9, adjust=False).mean()
                
                last = h.iloc[-1]; prev = h.iloc[-2]
                px = last['Close']; val = "€" if ticker.endswith(".MI") else "$"
                
                # Setup Logica Segnali
                msg = ""
                q_cons = int(capitale_per_trade/px)
                
                if strategia == "Trend Crossover (MACD)":
                    macd_cross_up = (prev['MACD'] < prev['MACD_Signal']) and (last['MACD'] > last['MACD_Signal'])
                    macd_cross_down = (prev['MACD'] > prev['MACD_Signal']) and (last['MACD'] < last['MACD_Signal'])
                    
                    if quote > 0 and macd_cross_down:
                        msg = f"🔴 *SELL (MACD)*: {ticker} a {px:.2f}{val}."
                    elif quote == 0 and macd_cross_up and (px > last['EMA']): # Filtro: Compra solo se sopra EMA 200
                        msg = f"🟢 *BUY (MACD)*: {ticker} a {px:.2f}{val}. Compra {q_cons} q."
                
                elif strategia == "Pullback (RSI + Bollinger)":
                    if quote > 0 and (px >= last['BBU'] or last['RSI'] > rsi_soglia_sell):
                        msg = f"🔴 *SELL (Pullback)*: {ticker} a {px:.2f}{val}."
                    elif quote == 0 and (px > last['EMA']) and (px <= last['BBL']) and (last['RSI'] < rsi_soglia_buy):
                        msg = f"🟢 *BUY (Pullback)*: {ticker} a {px:.2f}{val}. Compra {q_cons} q."

                if msg: manda_telegram(msg)

                with cols[i % 3]:
                    st.subheader(f"🏢 {ticker}")
                    st.write(f"**Prezzo:** {px:.2f}{val}")
                    if strategia == "Trend Crossover (MACD)":
                        st.write(f"MACD: {last['MACD']:.2f} | Signal: {last['MACD_Signal']:.2f}")
                    else:
                        st.write(f"RSI: {last['RSI']:.1f} | BB Inf: {last['BBL']:.2f}")
                        
                    if msg.startswith("🟢"): st.success("🟢 SEGNALE BUY!")
                    elif msg.startswith("🔴"): st.error("🔴 SEGNALE SELL!")
                    elif quote > 0: st.info(f"💼 In Portafoglio ({int(quote)} q.)")
                    else: st.write("⚪ Neutro")
                    st.markdown("---")
            except Exception as e: pass

# --- SCHEDA 2: BACKTESTING ---
with tab_backtest:
    st.subheader(f"🧪 Simulatore - {strategia}")
    sel_ticker = st.selectbox("Seleziona Titolo per il Test:", tickers_attuali)
    periodo_test = st.radio("Orizzonte Temporale:", ["2y", "5y", "max"], horizontal=True)
    
    if st.button("🧪 Avvia Stress Test"):
        data = yf.Ticker(sel_ticker).history(period=periodo_test)
        if len(data) > ema_len:
            # Calcoli completi per il backtest
            data['EMA'] = data['Close'].ewm(span=ema_len, adjust=False).mean()
            sma = data['Close'].rolling(20).mean(); std = data['Close'].rolling(20).std()
            data['BBL'] = sma - (std * 2); data['BBU'] = sma + (std * 2)
            delta = data['Close'].diff(); up = delta.clip(lower=0); dw = -1 * delta.clip(upper=0)
            data['RSI'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / dw.ewm(com=13, adjust=False).mean())))
            data['MACD'] = data['Close'].ewm(span=12, adjust=False).mean() - data['Close'].ewm(span=26, adjust=False).mean()
            data['MACD_Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
            
            cap = capitale_totale; pos = []; in_pos = False; qty = 0
            for i in range(ema_len, len(data)):
                row = data.iloc[i]; prev = data.iloc[i-1]
                
                # Condizioni in base alla strategia scelta
                if strategia == "Trend Crossover (MACD)":
                    buy_cond = (prev['MACD'] < prev['MACD_Signal']) and (row['MACD'] > row['MACD_Signal']) and (row['Close'] > row['EMA'])
                    sell_cond = (prev['MACD'] > prev['MACD_Signal']) and (row['MACD'] < row['MACD_Signal'])
                else:
                    buy_cond = (row['Close'] > row['EMA']) and (row['Close'] <= row['BBL']) and (row['RSI'] < rsi_soglia_buy)
                    sell_cond = (row['Close'] >= row['BBU']) or (row['RSI'] > rsi_soglia_sell)

                if not in_pos and buy_cond:
                    qty = cap // row['Close']; cap -= qty * row['Close']
                    pos.append({'Entrata': row.name, 'Prezzo E': row['Close']}); in_pos = True
                elif in_pos and sell_cond:
                    cap += qty * row['Close']
                    pos[-1].update({'Uscita': row.name, 'Prezzo U': row['Close'], 'P/L': (row['Close'] - pos[-1]['Prezzo E']) * qty})
                    in_pos = False
            
            if pos and 'P/L' in pos[-1]:
                df_res = pd.DataFrame([p for p in pos if 'P/L' in p])
                st.metric("P/L Totale Strategia", f"{df_res['P/L'].sum():.2f} €/$")
                st.line_chart(df_res['P/L'].cumsum())
                st.dataframe(df_res)
            else: st.warning("Nessuna operazione conclusa nel periodo scelto.")

# --- SCHEDA 3: DIARIO ---
with tab_diario:
    st.subheader("📝 Registra Nuova Transazione")
    with st.form("trade_form", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        f_t = c1.text_input("Ticker").upper()
        f_a = c2.selectbox("Azione", ["Acquisto (Buy)", "Vendita (Sell)"])
        f_p = c3.number_input("Prezzo", min_value=0.01)
        f_q = c4.number_input("Quantità", min_value=1)
        f_v = c5.selectbox("Valuta", ["$", "€"])
        if st.form_submit_button("💾 Salva Cloud"):
            if f_t:
                m = -1 if f_a == "Acquisto (Buy)" else 1
                sheet_main.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), f_t, f_a, f_p, f_q, f_p*f_q*m, f_v])
                st.success("Salvato!"); st.rerun()
    st.dataframe(df_storico, use_container_width=True)
