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
st.sidebar.header("🎯 Strategia & Indicatori")
strategia = st.sidebar.radio("Seleziona Motore Segnali:", ["Pullback (RSI + Bollinger)", "Trend Crossover (MACD)"])
ema_len = st.sidebar.number_input("Periodo EMA (Trend)", value=200)
rsi_soglia_buy = st.sidebar.slider("Soglia RSI Acquisto", 10, 50, 40)
rsi_soglia_sell = st.sidebar.slider("Soglia RSI Vendita", 50, 90, 70)

# --- 3. CARICAMENTO DATI DIARIO ---
colonne_attese = ['Data', 'Ticker', 'Azione', 'Prezzo', 'Quantita', 'Controvalore', 'Valuta']
try:
    dati_raw = sheet_main.get_all_records()
    if not dati_raw:
        df_storico = pd.DataFrame(columns=colonne_attese)
    else:
        df_storico = pd.DataFrame(dati_raw)
        df_storico['Quantita'] = pd.to_numeric(df_storico['Quantita'], errors='coerce').fillna(0)
        df_storico['Controvalore'] = pd.to_numeric(df_storico['Controvalore'], errors='coerce').fillna(0)
        df_storico['Prezzo'] = pd.to_numeric(df_storico['Prezzo'], errors='coerce').fillna(0)
        df_storico['Data'] = pd.to_datetime(df_storico['Data'], errors='coerce')
except Exception as e:
    st.error(f"Errore connessione Diario: {e}")
    df_storico = pd.DataFrame(columns=colonne_attese)

# --- 4. INTERFACCIA TABS ---
st.title("📊 Trading Terminal Pro")
tab_scanner, tab_backtest, tab_diario = st.tabs(["🚀 Scanner & Portafoglio", "🧪 Backtesting", "📓 Diario"])

with tab_scanner:
    if st.button("🔍 Avvia Analisi e Calcola Profitti", type="primary"):
        pnl_sum = st.container()
        st.markdown("---")
        st.subheader("📡 Radar Segnali di Mercato")
        
        cols = st.columns(3)
        tot_usd_unrealized, tot_usd_realized = 0.0, 0.0
        tot_eur_unrealized, tot_eur_realized = 0.0, 0.0
        portafoglio_aperto = []
        
        for i, ticker in enumerate(tickers_attuali):
            try:
                current_quote = 0
                current_pmc = 0.0
                cumulative_realized = 0.0
                valuta_t = "$"
                segnale_ui = ""
                
                if not df_storico.empty:
                    history_t = df_storico[df_storico['Ticker'] == ticker].sort_values('Data')
                    for _, row in history_t.iterrows():
                        valuta_t = row['Valuta']
                        tipo = row['Azione']
                        px_trade = row['Prezzo']
                        qty_trade = row['Quantita']
                        
                        if "Acquisto" in tipo:
                            total_cost = (current_quote * current_pmc) + (qty_trade * px_trade)
                            current_quote += qty_trade
                            current_pmc = total_cost / current_quote if current_quote > 0 else 0
                        elif "Vendita" in tipo:
                            profit_on_sale = (px_trade - current_pmc) * qty_trade
                            cumulative_realized += profit_on_sale
                            current_quote -= qty_trade
                            if current_quote <= 0:
                                current_quote = 0
                                current_pmc = 0.0

                s = yf.Ticker(ticker); h = s.history(period="2y")
                if h.empty: 
                    with cols[i % 3]:
                        st.subheader(f"🏢 {ticker}")
                        st.warning("⚠️ Simbolo non trovato.")
                        st.markdown("---")
                    continue
                
                h['EMA'] = h['Close'].ewm(span=ema_len, adjust=False).mean()
                sma = h['Close'].rolling(20).mean(); std = h['Close'].rolling(20).std()
                h['BBL'] = sma - (std * 2); h['BBU'] = sma + (std * 2)
                delta = h['Close'].diff(); up = delta.clip(lower=0); dw = -1 * delta.clip(upper=0)
                h['RSI'] = 100 - (100 / (1 + (up.ewm(com=13, adjust=False).mean() / dw.ewm(com=13, adjust=False).mean())))
                
                h['MACD'] = h['Close'].ewm(span=12, adjust=False).mean() - h['Close'].ewm(span=26, adjust=False).mean()
                h['MACD_Signal'] = h['MACD'].ewm(span=9, adjust=False).mean()
                
                last = h.iloc[-1]; prev = h.iloc[-2]
                px_now = last['Close']
                
                if strategia == "Trend Crossover (MACD)":
                    macd_cross_up = (prev['MACD'] < prev['MACD_Signal']) and (last['MACD'] > last['MACD_Signal'])
                    macd_cross_down = (prev['MACD'] > prev['MACD_Signal']) and (last['MACD'] < last['MACD_Signal'])
                    if current_quote > 0 and macd_cross_down:
                        segnale_ui = f"🔴 *SELL (MACD)*: {ticker} a {px_now:.2f} {valuta_t}"
                    elif current_quote == 0 and macd_cross_up and (px_now > last['EMA']):
                        segnale_ui = f"🟢 *BUY (MACD)*: {ticker} a {px_now:.2f} {valuta_t}"
                elif strategia == "Pullback (RSI + Bollinger)":
                    if current_quote > 0 and (px_now >= last['BBU'] or last['RSI'] > rsi_soglia_sell):
                        segnale_ui = f"🔴 *SELL (Pullback)*: {ticker} a {px_now:.2f} {valuta_t}"
                    elif current_quote == 0 and (px_now > last['EMA']) and (px_now <= last['BBL']) and (last['RSI'] < rsi_soglia_buy):
                        segnale_ui = f"🟢 *BUY (Pullback)*: {ticker} a {px_now:.2f} {valuta_t}"

                if segnale_ui: manda_telegram(segnale_ui)

                pnl_unrealized = (px_now - current_pmc) * current_quote if current_quote > 0 else 0.0
                
                if current_quote > 0:
                    res_perc = ((px_now - current_pmc) / current_pmc * 100) if current_pmc > 0 else 0.0
                    portafoglio_aperto.append({
                        "Ticker": ticker, 
                        "Quantità": int(current_quote), 
                        "Prezzo Acquisto": round(current_pmc, 2),
                        "Prezzo Attuale": round(px_now, 2), 
                        "P&L Attivo": round(pnl_unrealized, 2),
                        "Resa %": round(res_perc, 2), 
                        "Valuta": valuta_t
                    })
                
                if valuta_t == "€":
                    tot_eur_unrealized += pnl_unrealized; tot_eur_realized += cumulative_realized
                else:
                    tot_usd_unrealized += pnl_unrealized; tot_usd_realized += cumulative_realized

                with cols[i % 3]:
                    st.subheader(f"🏢 {ticker}")
                    st.write(f"Prezzo: {px_now:.2f} {valuta_t}")
                    if segnale_ui.startswith("🟢"): st.success(segnale_ui.replace("*", ""))
                    elif segnale_ui.startswith("🔴"): st.error(segnale_ui.replace("*", ""))
                    
                    if current_quote > 0:
                        c = "green" if pnl_unrealized >= 0 else "red"
                        st.markdown(f"**P&L Attivo:** :{c}[{pnl_unrealized:.2f} {valuta_t}]")
                    elif cumulative_realized != 0:
                        c_real = "green" if cumulative_realized > 0 else "red"
                        st.markdown(f"**Realizzato Storico:** :{c_real}[{cumulative_realized:.2f} {valuta_t}]")
                    elif not segnale_ui:
                        st.write("⚪ In monitoraggio")
                    st.markdown("---")
            except: pass
        
        with pnl_sum:
            st.markdown("### 💰 Sintesi Portafoglio")
            if portafoglio_aperto:
                df_portafoglio = pd.DataFrame(portafoglio_aperto)
                st.dataframe(
                    df_portafoglio.style.map(
                        lambda x: 'color: #00CC00' if isinstance(x, (int, float)) and x > 0 else ('color: #FF0000' if isinstance(x, (int, float)) and x < 0 else ''),
                        subset=['P&L Attivo', 'Resa %']
                    ),
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("Nessuna azione attualmente in portafoglio.")
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.markdown("#### 💵 Bilancio USD ($)")
            c1.metric("P&L Attivo", f"{tot_usd_unrealized:.2f} $")
            c1.metric("P&L Realizzato", f"{tot_usd_realized:.2f} $")
            c2.markdown("#### 💶 Bilancio EUR (€)")
            c2.metric("P&L Attivo", f"{tot_eur_unrealized:.2f} €")
            c2.metric("P&L Realizzato", f"{tot_eur_realized:.2f} €")

with tab_diario:
    st.subheader("📝 Registra Operazione")
    with st.form("new_trade", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        f_t = c1.text_input("Ticker").upper()
        f_a = c2.selectbox("Azione", ["Acquisto (Buy)", "Vendita (Sell)"])
        f_p = c3.number_input("Prezzo", min_value=0.01)
        f_q = c4.number_input("Quantità", min_value=1)
        f_v = c5.selectbox("Valuta", ["$", "€"])
        if st.form_submit_button("💾 Salva"):
            m = -1 if f_a == "Acquisto (Buy)" else 1
            riga = [datetime.now().strftime("%Y-%m-%d %H:%M"), f_t, f_a, f_p, f_q, f_p*f_q*m, f_v]
            sheet_main.append_row(riga)
            st.success("Registrato!"); st.rerun()

    st.markdown("---")
    st.subheader("📓 Storico Operazioni")
    if df_storico.empty:
        st.info("Nessuna operazione trovata.")
    else:
        st.dataframe(df_storico, use_container_width=True)

with tab_backtest:
    st.subheader(f"🧪 Simulatore - {strategia}")
    sel_ticker = st.selectbox("Seleziona Titolo per il Test:", tickers_attuali)
    periodo_test = st.radio("Orizzonte Temporale:", ["2y", "5y", "max"], horizontal=True)
    capitale_totale = st.number_input("Capitale Iniziale Backtest", value=10000)
    
    if st.button("🧪 Avvia Stress Test"):
        data = yf.Ticker(sel_ticker).history(period=periodo_test)
        if len(data) > ema_len:
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
                st.metric("P/L Totale Strategia", f"{df_res['P/L'].sum():.2f}")
                st.line_chart(df_res['P/L'].cumsum())
                st.dataframe(df_res)
            else: st.warning("Nessuna operazione conclusa nel periodo scelto.")
