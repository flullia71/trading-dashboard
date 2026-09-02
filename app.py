import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import requests
import time
import finnhub

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Trading Terminal Pro", layout="wide")

def manda_telegram(messaggio):
    try:
        token = st.secrets["telegram_token"]
        chat_id = st.secrets["telegram_chat_id"]
        url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={messaggio}&parse_mode=Markdown"
        requests.get(url, timeout=5)
    except: 
        pass

@st.cache_resource
def get_google_sheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource
def get_finnhub_client():
    api_key = st.secrets["finnhub_key"]
    return finnhub.Client(api_key=api_key)

client = get_google_sheet_client()
sheet_url = st.secrets["google_sheet_url"]
workbook = client.open_by_url(sheet_url)
sheet_main = workbook.sheet1

finnhub_client = get_finnhub_client()

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
    st.sidebar.success("Sincronizzata!")
    st.rerun()

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

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, ticker in enumerate(tickers_attuali):
            status_text.text(f"⚡ Recupero quotazione API per {ticker} ({i+1}/{len(tickers_attuali)})...")
            progress_bar.progress((i + 1) / len(tickers_attuali))
            
            # 1. ELABORAZIONE DIARIO GOOGLE SHEETS
            current_quote = 0.0
            current_pmc = 0.0
            cumulative_realized = 0.0
            valuta_t = "$"
            
            if not df_storico.empty and 'Ticker' in df_storico.columns:
                history_t = df_storico[df_storico['Ticker'].astype(str).str.strip().str.upper() == ticker].sort_values('Data')
                for _, row in history_t.iterrows():
                    valuta_t = str(row.get('Valuta', '$')).strip() if pd.notna(row.get('Valuta')) and str(row.get('Valuta')).strip() != '' else "$"
                    tipo = str(row.get('Azione', '')).strip().lower()
                    px_trade = float(row.get('Prezzo', 0.0))
                    qty_trade = float(row.get('Quantita', 0.0))
                    
                    if "acquis" in tipo or "buy" in tipo:
                        total_cost = (current_quote * current_pmc) + (qty_trade * px_trade)
                        current_quote += qty_trade
                        current_pmc = total_cost / current_quote if current_quote > 0 else 0.0
                    elif "vend" in tipo or "sell" in tipo:
                        profit_on_sale = (px_trade - current_pmc) * qty_trade
                        cumulative_realized += profit_on_sale
                        current_quote -= qty_trade
                        if current_quote <= 0:
                            current_quote = 0.0
                            current_pmc = 0.0

            # 2. SCARICAMENTO PREZZO LIVE DA FINNHUB
            px_now = None
            try:
                res = finnhub_client.quote(ticker)
                if res and 'c' in res and res['c'] != 0:
                    px_now = float(res['c']) # Prezzo corrente di mercato
            except Exception:
                px_now = None

            # 3. CALCOLO P&L E COMPOSIZIONE PORTAFOGLIO
            pnl_unrealized = 0.0
            res_perc = 0.0

            if current_quote > 0:
                if px_now is not None:
                    pnl_unrealized = (px_now - current_pmc) * current_quote
                    res_perc = ((px_now - current_pmc) / current_pmc * 100) if current_pmc > 0 else 0.0
                
                portafoglio_aperto.append({
                    "Ticker": ticker,
                    "Quantità": int(current_quote),
                    "Prezzo Carico (PMC)": round(current_pmc, 2),
                    "Prezzo Attuale": round(px_now, 2) if px_now is not None else "N/D",
                    "P&L Attivo": round(pnl_unrealized, 2) if px_now is not None else "N/D",
                    "Resa %": f"{res_perc:+.2f}%" if px_now is not None else "N/D",
                    "Valuta": valuta_t
                })

            if valuta_t == "€":
                tot_eur_unrealized += pnl_unrealized
                tot_eur_realized += cumulative_realized
            else:
                tot_usd_unrealized += pnl_unrealized
                tot_usd_realized += cumulative_realized

            # 4. RENDERING CARD TITOLO
            with cols[i % 3]:
                st.subheader(f"🏢 {ticker}")
                
                if px_now is not None:
                    st.write(f"Prezzo Attuale (Finnhub): **{px_now:.2f} {valuta_t}**")
                else:
                    st.warning("⚠️ Quotazione Finnhub non disponibile.")

                if current_quote > 0:
                    st.write(f"Quantità in carico: **{int(current_quote)} pz**")
                    st.write(f"Prezzo di Carico (PMC): **{current_pmc:.2f} {valuta_t}**")
                    if px_now is not None:
                        c = "green" if pnl_unrealized >= 0 else "red"
                        st.markdown(f"**P&L Attivo:** :{c}[{pnl_unrealized:.2f} {valuta_t}] ({res_perc:+.2f}%)")
                elif cumulative_realized != 0:
                    c_real = "green" if cumulative_realized > 0 else "red"
                    st.markdown(f"**Realizzato Storico:** :{c_real}[{cumulative_realized:.2f} {valuta_t}]")
                else:
                    st.write("⚪ In monitoraggio")
                
                st.markdown("---")

        status_text.empty()
        progress_bar.empty()

       # 5. TABELLA SINTESI PORTAFOGLIO
        with pnl_sum:
            st.markdown("### 💰 Sintesi Portafoglio")
            if portafoglio_aperto:
                df_portafoglio = pd.DataFrame(portafoglio_aperto)
                
                # Funzione sicura per applicare il colore rosso/verde
                def colora_pnl(valore):
                    try:
                        val_num = float(valore)
                        if val_num > 0:
                            return 'color: #00CC00; font-weight: bold;'
                        elif val_num < 0:
                            return 'color: #FF0000; font-weight: bold;'
                    except (ValueError, TypeError):
                        pass
                    return ''
        
                # Applicazione dello stile con gestione sicura dei tipi
                st.dataframe(
                    df_portafoglio.style.applymap(colora_pnl, subset=['P&L Attivo']),
                    use_container_width=True, 
                    hide_index=True
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
            st.success("Registrato!")
            st.rerun()

    st.markdown("---")
    st.subheader("📓 Storico Operazioni")
    if df_storico.empty:
        st.info("Nessuna operazione trovata.")
    else:
        st.dataframe(df_storico, use_container_width=True)

with tab_backtest:
    st.subheader(f"🧪 Simulatore - {strategia}")
    st.info("La tab Backtesting è pronta per essere configurata con le candele storiche di Finnhub.")
