import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# 1. Configurazione della pagina
st.set_page_config(page_title="Trading Terminal Pro", layout="wide")

# Inizializziamo la "Memoria" per il Diario di Trading
if 'storico_trade' not in st.session_state:
    st.session_state['storico_trade'] = pd.DataFrame(columns=['Data', 'Ticker', 'Azione', 'Prezzo', 'Quantità', 'Controvalore'])

st.title("📊 Trading Terminal Pro")
st.write("Scansione, Money Management e Diario Operazioni in un'unica app.")

# ---------------------------------------------------------
# 2. SIDEBAR: LA PLANCIA DI COMANDO
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# 3. INTERFACCIA A SCHEDE (TABS)
# ---------------------------------------------------------
tab_scanner, tab_diario = st.tabs(["🚀 Scanner di Mercato", "📓 Diario Operazioni (P&L)"])

# --- SCHEDA 1: LO SCANNER ---
with tab_scanner:
    if st.button("🔍 Avvia Scansione", type="primary"):
        st.write("Scansione in corso...")
        col1, col2, col3 = st.columns(3)
        
        for i, ticker in enumerate(tickers):
            try:
                # Gestione Valuta Veloce
                valuta = "€" if ticker.endswith(".MI") or ticker.endswith(".DE") else "$"

                stock = yf.Ticker(ticker)
                df = stock.history(period="2y", interval='1d')
                
                if df.empty or len(df) < ema_len:
                    st.warning(f"Dati insufficienti per {ticker}")
                    continue

                # Matematica
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

                buy_condition = (chiusura > ema_val) and (chiusura <= banda_inf) and (rsi_val < rsi_soglia_buy)
                sell_condition = (chiusura >= banda_sup) or (rsi_val > rsi_soglia_sell)

                # Suggerimento Azioni da comprare in base al capitale
                azioni_consigliate = int(capitale_per_trade / chiusura) if chiusura > 0 else 0

                with [col1, col2, col3][i % 3]:
                    st.subheader(f"🏢 {ticker}")
                    st.write(f"**Prezzo:** {chiusura:.2f} {valuta}")
                    st.write(f"**RSI:** {rsi_val:.2f} | **EMA:** {'🟢' if chiusura > ema_val else '🔴'}")
                    
                    if buy_condition:
                        st.success(f"🟢 BUY! Investimento suggerito: {capitale_per_trade:.2f} {valuta} (Circa {azioni_consigliate} quote)")
                    elif sell_condition:
                        st.error("🔴 SEGNALE DI VENDITA (SELL)!")
                    else:
                        st.info("⚪ Neutro")
                    st.markdown("---")
            except Exception as e:
                st.error(f"Errore con {ticker}: {e}")

# --- SCHEDA 2: IL DIARIO DI TRADING E P&L ---
with tab_diario:
    st.subheader("📝 Registra una nuova operazione")
    
    # Form per inserire un trade
    with st.form("form_trade", clear_on_submit=True):
        col_t, col_a, col_p, col_q = st.columns(4)
        form_ticker = col_t.text_input("Ticker (es. AAPL)")
        form_azione = col_a.selectbox("Azione", ["Acquisto (Buy)", "Vendita (Sell)"])
        form_prezzo = col_p.number_input("Prezzo di esecuzione", min_value=0.01, format="%.2f")
        form_quantita = col_q.number_input("Quantità (Quote)", min_value=1, step=1)
        
        inviato = st.form_submit_button("💾 Salva Operazione")
        
        if inviato and form_ticker:
            # Calcolo del controvalore (negativo se compri, positivo se vendi)
            moltiplicatore = -1 if form_azione == "Acquisto (Buy)" else 1
            controvalore = form_prezzo * form_quantita * moltiplicatore
            
            nuovo_trade = pd.DataFrame([{
                'Data': datetime.now().strftime("%Y-%m-%d %H:%M"),
                'Ticker': form_ticker.upper(),
                'Azione': form_azione,
                'Prezzo': form_prezzo,
                'Quantità': form_quantita,
                'Controvalore': controvalore
            }])
            
            # Aggiungiamo il trade alla memoria della sessione
            st.session_state['storico_trade'] = pd.concat([st.session_state['storico_trade'], nuovo_trade], ignore_index=True)
            st.success("Operazione registrata con successo!")

    st.markdown("---")
    st.subheader("📚 Il tuo Storico e P&L (Temporaneo)")
    
    if not st.session_state['storico_trade'].empty:
        # Mostriamo la tabella
        st.dataframe(st.session_state['storico_trade'], use_container_width=True)
        
        # Calcolo molto base del flusso di cassa (Uscite vs Entrate)
        flusso_di_cassa = st.session_state['storico_trade']['Controvalore'].sum()
        
        st.info("💡 *Nota sul Controvalore: i numeri negativi (rossi) sono i soldi spesi per comprare. I numeri positivi sono i soldi incassati vendendo.*")
        if flusso_di_cassa < 0:
            st.warning(f"💸 **Flusso di Cassa Attuale:** {flusso_di_cassa:.2f} (Hai più capitale investito che ritirato)")
        else:
            st.success(f"💰 **Flusso di Cassa Attuale:** +{flusso_di_cassa:.2f} (Hai incassato più di quanto hai speso!)")
            
        if st.button("🗑️ Cancella tutto lo storico"):
             st.session_state['storico_trade'] = pd.DataFrame(columns=['Data', 'Ticker', 'Azione', 'Prezzo', 'Quantità', 'Controvalore'])
             st.rerun()
    else:
        st.write("Nessuna operazione registrata. Quando esegui un trade, inseriscilo nel modulo qui sopra!")
