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
    # Se dimentichi di creare il foglio "Config", l'app lo crea per te
    sheet_config = workbook.add_worksheet(title="Config", rows="100", cols="5")
    sheet_config.update('A1', 'Ticker')

# Funzioni Cloud
def carica_ticker_config():
    records = sheet_config.get_all_records()
    return [r['Ticker'].upper() for r in records if r.get('Ticker')]

def salva_lista_ticker_cloud(lista_nuova):
    # Pulisce il foglio e scrive la nuova lista
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

# --- SIDEBAR ---
st.sidebar.header("📋 Radar Setup")
lista_ticker_str = ", ".join(ticker_persistenti) if ticker_persistenti else "AAPL, NVDA, UCG.MI"
tickers_input = st.sidebar.text_area("Azioni da monitorare:", value=lista_ticker_str, height=150)
tickers_attuali = [t.strip().upper() for t in tickers_input.replace('\n', ',').split(',') if t.strip()]

if st.sidebar.button("💾 Salva Lista nel Cloud"):
    salva_lista_ticker_cloud(tickers_attuali)
    st.sidebar.success("Lista sincronizzata su GSheet!")
    st.rerun()

st.sidebar.markdown("---")
capitale_totale = st.sidebar.number_input("Capitale Totale", value=10000)
rischio_percent = st.sidebar.slider("Rischio per trade %", 1, 20, 5)
capitale_per_trade = capitale_totale * (rischio_percent / 100)

# --- TABS ---
tab_scanner, tab_diario = st.tabs(["🚀 Scanner", "📓 Diario"])

with tab_scanner:
    if st.button("🔍 Scansiona Ora", type="primary"):
        cols = st.columns(3)
        for i, ticker in enumerate(tickers_attuali):
            try:
                # Calcolo quote (da storico trade)
                quote = 0
                if not df_storico.empty:
                    st_t = df_storico[df_storico['Ticker'] == ticker]
                    quote = pd.to_numeric(st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita']).sum() - \
                            pd.to_numeric(st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita']).sum()

                # Dati Market
                s = yf.Ticker(ticker)
                h = s.history(period="2y")
                if h.empty: continue
                
                # Calcoli Tecnici Rapidi
                h['EMA'] = h['Close'].ewm(span=200, adjust=False).mean()
                sma = h['Close'].rolling(20).mean(); std = h['Close'].rolling(20).std()
                h['BBL'] = sma - (std * 2); h['BBU'] = sma + (std * 2)
                d = h['Close'].diff(); u = d.clip(lower=0); dw = -1*d.clip(upper=0)
                h['RSI'] = 100 - (100/(1+(u.ewm(com=13).mean()/dw.ewm(com=13).mean())))
                
                last = h.iloc[-1]
                px = last['Close']; rsi = last['RSI']; ema = last['EMA']; bbl = last['BBL']; bbu = last['BBU']
                
                with cols[i % 3]:
                    st.subheader(f"{ticker}")
                    val = "€" if ticker.endswith(".MI") else "$"
                    st.write(f"Prezzo: {px:.2f}{val} | RSI: {rsi:.1f}")
                    
                    if quote > 0:
                        st.info(f"💼 In Portafoglio: {int(quote)} q.te")
                        if px >= bbu or rsi > 70: st.error("🔴 VENDERE!")
                    elif (px > ema) and (px <= bbl) and (rsi < 40):
                        st.success(f"🟢 BUY! (~{int(capitale_per_trade/px)} q.te)")
                    else:
                        st.write("⚪ Neutro")
                    st.markdown("---")
            except: pass

with tab_diario:
    # (Codice del Diario uguale a prima, registra i trade su sheet_main)
    st.subheader("📝 Registra Trade")
    with st.form("trade_form", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        f_t = c1.text_input("Ticker").upper()
        f_a = c2.selectbox("Azione", ["Acquisto (Buy)", "Vendita (Sell)"])
        f_p = c3.number_input("Prezzo", min_value=0.01)
        f_q = c4.number_input("Quantità", min_value=1)
        f_v = c5.selectbox("Valuta", ["$", "€"])
        if st.form_submit_button("Salva"):
            m = -1 if f_a == "Acquisto (Buy)" else 1
            sheet_main.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), f_t, f_a, f_p, f_q, f_p*f_q*m, f_v])
            st.success("Trade salvato!"); st.rerun()
    st.dataframe(df_storico, use_container_width=True)
