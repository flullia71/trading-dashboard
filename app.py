import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Trading Terminal Pro", layout="wide")

# ---------------------------------------------------------
# CONNESSIONE A GOOGLE SHEETS
# ---------------------------------------------------------
@st.cache_resource
def get_google_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    # Carica i segreti dalla cassaforte di Streamlit
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # Apri il foglio usando l'URL salvato nei secrets
    sheet_url = st.secrets["google_sheet_url"]
    return client.open_by_url(sheet_url).sheet1

try:
    sheet = get_google_sheet()
except Exception as e:
    st.error(f"Errore di connessione a Google Sheets: Assicurati di aver configurato i Secrets correttamente. Dettagli: {e}")
    st.stop()

# Funzioni per leggere e scrivere sul database
def carica_storico():
    dati = sheet.get_all_records()
    if dati:
        return pd.DataFrame(dati)
    else:
        return pd.DataFrame(columns=['Data', 'Ticker', 'Azione', 'Prezzo', 'Quantita', 'Controvalore'])

def salva_nuovo_trade(lista_dati):
    sheet.append_row(lista_dati)

# Caricamento del portafoglio dal Cloud
df_storico = carica_storico()

# ---------------------------------------------------------
# IL RESTO DEL CODICE (Scanner e UI)
# ---------------------------------------------------------
st.title("📊 Trading Terminal Pro (Cloud Database)")
st.write("Scansione intelligente collegata in tempo reale al tuo Google Sheet.")

st.sidebar.header("💰 Money Management")
capitale_totale = st.sidebar.number_input("Capitale Totale a disposizione", min_value=100, value=10000, step=100)
rischio_percentuale = st.sidebar.slider("Quanto capitale investire per ogni segnale?", min_value=1, max_value=20, value=5, format="%d%%")
capitale_per_trade = capitale_totale * (rischio_percentuale / 100)

st.sidebar.header("📋 Gestione Azioni")
tickers_input = st.sidebar.text_area("Ticker (separati da virgola o a capo):", "CRM, AAPL, GOOGL\nUCG.MI, NVDA\nENEL.MI, ENI.MI", height=100)
tickers = [t.strip().upper() for t in tickers_input.replace('\n', ',').split(',') if t.strip()]

st.sidebar.header("⚙️ Parametri Modello")
ema_len = st.sidebar.number_input("Periodo EMA", value=200, step=10)
bb_len = st.sidebar.number_input("Periodo Bollinger", value=20, step=1)
bb_std = st.sidebar.slider("Dev. Standard Bollinger", 1.0, 4.0, 2.0, 0.1)
rsi_len = st.sidebar.number_input("Periodo RSI", value=14, step=1)
rsi_soglia_buy = st.sidebar.slider("Soglia RSI Acquisto", 10, 50, 40)
rsi_soglia_sell = st.sidebar.slider("Soglia RSI Vendita", 50, 90, 70)

tab_scanner, tab_diario = st.tabs(["🚀 Scanner Intelligente", "📓 Diario e Portafoglio"])

with tab_scanner:
    if st.button("🔍 Avvia Scansione", type="primary"):
        col1, col2, col3 = st.columns(3)
        for i, ticker in enumerate(tickers):
            try:
                # Lettura intelligente del portafoglio da Google Sheets
                quote_possedute = 0
                if not df_storico.empty:
                    storico_ticker = df_storico[df_storico['Ticker'] == ticker]
                    acquisti = pd.to_numeric(storico_ticker[storico_ticker['Azione'] == 'Acquisto (Buy)']['Quantita']).sum()
                    vendite = pd.to_numeric(storico_ticker[storico_ticker['Azione'] == 'Vendita (Sell)']['Quantita']).sum()
                    quote_possedute = acquisti - vendite
                
                valuta = "€" if ticker.endswith(".MI") or ticker.endswith(".DE") else "$"
                stock = yf.Ticker(ticker)
                df = stock.history(period="2y", interval='1d')
                
                if df.empty or len(df) < ema_len:
                    continue

                df['EMA'] = df['Close'].ewm(span=ema_len, adjust=False).mean()
                sma = df['Close'].rolling(window=bb_len).mean()
                std = df['Close'].rolling(window=bb_len).std()
                df['BBL'] = sma - (std * bb_std)
                df['BBU'] = sma + (std * bb_std)
                
                delta = df['Close'].diff()
                up = delta.clip(lower=0)
                down = -1 * delta.clip(upper=0)
                ema_up = up.ewm(com=rsi_len-1, adjust=False).mean()
                ema_down = down.ewm(com=rsi_len-1, adjust=False).mean()
                rs = ema_up / ema_down
                df['RSI'] = 100 - (100 / (1 + rs))
                
                df.dropna(inplace=True)
                if df.empty: continue

                ultima_riga = df.iloc[-1]
                chiusura = float(ultima_riga['Close'])
                ema_val = float(ultima_riga['EMA'])
                rsi_val = float(ultima_riga['RSI'])
                banda_inf = float(ultima_riga['BBL'])
                banda_sup = float(ultima_riga['BBU'])

                condizione_matematica_buy = (chiusura > ema_val) and (chiusura <= banda_inf) and (rsi_val < rsi_soglia_buy)
                condizione_matematica_sell = (chiusura >= banda_sup) or (rsi_val > rsi_soglia_sell)

                azioni_consigliate = int(capitale_per_trade / chiusura) if chiusura > 0 else 0

                with [col1, col2, col3][i % 3]:
                    st.subheader(f"🏢 {ticker}")
                    st.write(f"**Prezzo:** {chiusura:.2f} {valuta}")
                    st.write(f"**RSI:** {rsi_val:.2f} | **EMA:** {'🟢' if chiusura > ema_val else '🔴'}")
                    
                    if quote_possedute > 0:
                        st.info(f"💼 Possiedi **{int(quote_possedute)} quote**.")
                        if condizione_matematica_sell:
                            st.error(f"🔴 SEGNALE VENDITA! Incassa!")
                        else:
                            st.write("⏳ In attesa delle condizioni di vendita...")
                    elif quote_possedute == 0:
                        if condizione_matematica_buy:
                            st.success(f"🟢 BUY! Acquista circa {azioni_consigliate} quote")
                        else:
                            st.write("⚪ Neutro")
                    st.markdown("---")
            except Exception as e:
                pass

with tab_diario:
    st.subheader("📝 Registra una nuova operazione")
    with st.form("form_trade", clear_on_submit=True):
        col_t, col_a, col_p, col_q = st.columns(4)
        form_ticker = col_t.text_input("Ticker (es. AAPL)").upper()
        form_azione = col_a.selectbox("Azione", ["Acquisto (Buy)", "Vendita (Sell)"])
        form_prezzo = col_p.number_input("Prezzo di esecuzione", min_value=0.01, format="%.2f")
        form_quantita = col_q.number_input("Quantità (Quote)", min_value=1, step=1)
        
        inviato = st.form_submit_button("💾 Salva in Google Sheets")
        
        if inviato and form_ticker:
            moltiplicatore = -1 if form_azione == "Acquisto (Buy)" else 1
            controvalore = form_prezzo * form_quantita * moltiplicatore
            data_corrente = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Scrittura diretta su Google Sheets
            salva_nuovo_trade([data_corrente, form_ticker, form_azione, form_prezzo, form_quantita, controvalore])
            
            st.success("Operazione registrata PERMANENTEMENTE nel cloud!")
            st.rerun()

    st.markdown("---")
    st.subheader("📚 Il tuo Portafoglio (Live da Google Sheets)")
    
    if not df_storico.empty:
        st.dataframe(df_storico, use_container_width=True)
        flusso_di_cassa = pd.to_numeric(df_storico['Controvalore']).sum()
        
        if flusso_di_cassa < 0:
            st.warning(f"💸 **Flusso di Cassa:** {flusso_di_cassa:.2f}")
        else:
            st.success(f"💰 **Flusso di Cassa:** +{flusso_di_cassa:.2f}")
    else:
        st.write("Nessuna operazione registrata. Il database è vuoto.")
