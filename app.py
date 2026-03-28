import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Trading Terminal Pro", layout="wide")

# --- 2. CONNESSIONE GOOGLE SHEETS ---
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
    if dati:
        return pd.DataFrame(dati)
    else:
        return pd.DataFrame(columns=['Data', 'Ticker', 'Azione', 'Prezzo', 'Quantita', 'Controvalore', 'Valuta'])

# Caricamento Dati Iniziale
ticker_persistenti = carica_ticker_config()
df_storico = carica_storico()

# --- 3. SIDEBAR (PANNELLO COMANDI) ---
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

# --- 4. INTERFACCIA PRINCIPALE (TABS) ---
st.title("📊 Trading Terminal Pro")
tab_scanner, tab_diario = st.tabs(["🚀 Scanner di Mercato", "📓 Diario Operazioni"])

with tab_scanner:
    if st.button("🔍 Scansiona Ora", type="primary"):
        st.write("Analisi in corso...")
        cols = st.columns(3)
        for i, ticker in enumerate(tickers_attuali):
            try:
                # 1. Calcolo quote in portafoglio
                quote = 0
                if not df_storico.empty and 'Ticker' in df_storico.columns:
                    st_t = df_storico[df_storico['Ticker'] == ticker]
                    q_buy = pd.to_numeric(st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita']).sum()
                    q_sell = pd.to_numeric(st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita']).sum()
                    quote = q_buy - q_sell

                # 2. Scarico Dati da Yahoo
                s = yf.Ticker(ticker)
                h = s.history(period="2y")
                if h.empty:
                    continue
                
                # 3. Calcoli Tecnici
                h['EMA'] = h['Close'].ewm(span=ema_len, adjust=False).mean()
                sma = h['Close'].rolling(20).mean()
                std = h['Close'].rolling(20).std()
                h['BBL'] = sma - (std * bb_std)
                h['BBU'] = sma + (std * bb_std)
                
                delta = h['Close'].diff()
                up = delta.clip(lower=0)
                dw = -1 * delta.clip(upper=0)
                ema_up = up.ewm(com=13, adjust=False).mean()
                ema_dw = dw.ewm(com=13, adjust=False).mean()
                h['RSI'] = 100 - (100 / (1 + (ema_up / ema_dw)))
                
                last = h.iloc[-1]
                px = last['Close']
                rsi_v = last['RSI']
                ema_v = last['EMA']
                bbl = last['BBL']
                bbu = last['BBU']
                
                # 4. Visualizzazione Card
                with cols[i % 3]:
                    st.subheader(f"🏢 {ticker}")
                    val = "€" if ticker.endswith(".MI") else "$"
                    st.write(f"**Prezzo:** {px:.2f}{val} | **RSI:** {rsi_v:.1f}")
                    st.write(f"**EMA {ema_len}:** {'🟢' if px > ema_v else '🔴'}")
                    
                    if quote > 0:
                        st.info(f"💼 Possiedi **{int(quote)}** quote.")
                        if px >= bbu or rsi_v > rsi_soglia_sell:
                            st.error("🔴 SEGNALE VENDITA!")
                        else:
                            st.write("⏳ In attesa di segnale d'uscita...")
                    elif (px > ema_v) and (px <= bbl) and (rsi_v < rsi_soglia_buy):
                        st.success(f"🟢 BUY! Suggerite: {int(capitale_per_trade/px)} q.te")
                    else:
                        st.write("⚪ Neutro")
                    st.markdown("---")

            except Exception as e:
                st.error(f"Errore su {ticker}: {e}")

with tab_diario:
    st.subheader("📝 Registra Nuova Transazione")
    with st.form("trade_form", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        f_t = c1.text_input("Ticker").upper()
        f_a = c2.selectbox("Azione", ["Acquisto (Buy)", "Vendita (Sell)"])
        f_p = c3.number_input("Prezzo", min_value=0.01, format="%.2f")
        f_q = c4.number_input("Quantità", min_value=1, step=1)
        f_v = c5.selectbox("Valuta", ["$", "€"])
        
        if st.form_submit_button("💾 Salva nel Cloud"):
            if f_t:
                m = -1 if f_a == "Acquisto (Buy)" else 1
                data_ora = datetime.now().strftime("%Y-%m-%d %H:%M")
                sheet_main.append_row([data_ora, f_t, f_a, f_p, f_q, f_p*f_q*m, f_v])
                st.success(f"Operazione su {f_t} salvata!")
                st.rerun()
            else:
                st.error("Inserisci un Ticker!")

    st.markdown("---")
    st.subheader("📚 Riepilogo Trade")
    if not df_storico.empty:
        st.dataframe(df_storico, use_container_width=True)
    else:
        st.write("Database vuoto.")
