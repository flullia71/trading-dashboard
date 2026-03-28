import streamlit as st
import yfinance as yf
import pandas as pd

# 1. Configurazione della pagina
st.set_page_config(page_title="Trading Alert Dashboard", layout="wide")

st.title("📈 Dashboard Alert di Trading (Versione Pro)")
st.write("Scansiona il mercato in tempo reale personalizzando ogni singolo parametro del tuo modello matematico.")

# ---------------------------------------------------------
# 2. SIDEBAR: LA PLANCIA DI COMANDO
# ---------------------------------------------------------
st.sidebar.header("📋 Gestione Azioni")
# Usiamo una text_area spaziosa per permettere il copia-incolla in blocco
tickers_input = st.sidebar.text_area(
    "Inserisci i Ticker (separati da virgola o a capo):", 
    "CRM, AAPL, GOOGL\nUCG.MI, NVDA\nENEL.MI, ENI.MI",
    height=150
)
# Puliamo l'input: sostituiamo gli "a capo" con virgole e creiamo la lista pulita
tickers = [t.strip().upper() for t in tickers_input.replace('\n', ',').split(',') if t.strip()]


st.sidebar.header("⚙️ Parametri Modello")
st.sidebar.subheader("1. Trend (Semaforo)")
ema_len = st.sidebar.number_input("Periodo EMA (Media Mobile)", min_value=10, max_value=300, value=200, step=10)

st.sidebar.subheader("2. Volatilità (Sconti)")
bb_len = st.sidebar.number_input("Periodo Bande di Bollinger", min_value=5, max_value=100, value=20, step=1)
bb_std = st.sidebar.slider("Deviazione Standard Bollinger", min_value=1.0, max_value=4.0, value=2.0, step=0.1)

st.sidebar.subheader("3. Momentum (Grilletto)")
rsi_len = st.sidebar.number_input("Periodo RSI", min_value=5, max_value=50, value=14, step=1)
rsi_soglia_buy = st.sidebar.slider("Soglia RSI Acquisto (< Ipervenduto)", min_value=10, max_value=50, value=40)
rsi_soglia_sell = st.sidebar.slider("Soglia RSI Vendita (> Ipercomprato)", min_value=50, max_value=90, value=70)

st.sidebar.markdown("---")
st.sidebar.write(f"📊 Azioni in monitoraggio: **{len(tickers)}**")

# ---------------------------------------------------------
# 3. IL MOTORE DI SCANSIONE
# ---------------------------------------------------------
if st.button("🚀 Scansiona Mercato Ora", type="primary"):
    if not tickers:
        st.warning("Inserisci almeno un'azione da monitorare!")
    else:
        st.write("Scansione in corso. Attendere...")
        
        col1, col2, col3 = st.columns(3)
        
        for i, ticker in enumerate(tickers):
            try:
                # Scarichiamo 2 anni di dati per assicurarci di avere storico sufficiente
                stock = yf.Ticker(ticker)
                df = stock.history(period="2y", interval='1d')
                
                if df.empty or len(df) < ema_len:
                    st.warning(f"Dati storici insufficienti per {ticker} (servono almeno {ema_len} giorni)")
                    continue

                # --- MATEMATICA DINAMICA BASATA SUI TUOI INPUT ---
                
                # EMA Personalizzata
                df['EMA'] = df['Close'].ewm(span=ema_len, adjust=False).mean()
                
                # Bollinger Personalizzate
                sma = df['Close'].rolling(window=bb_len).mean()
                std = df['Close'].rolling(window=bb_len).std()
                df['BBL'] = sma - (std * bb_std)
                df['BBU'] = sma + (std * bb_std)
                
                # RSI Personalizzato
                delta = df['Close'].diff()
                up = delta.clip(lower=0)
                down = -1 * delta.clip(upper=0)
                ema_up = up.ewm(com=rsi_len-1, adjust=False).mean()
                ema_down = down.ewm(com=rsi_len-1, adjust=False).mean()
                rs = ema_up / ema_down
                df['RSI'] = 100 - (100 / (1 + rs))
                
                df.dropna(inplace=True)
                if df.empty:
                    continue

                # Estraiamo i dati di OGGI
                ultima_riga = df.iloc[-1]
                chiusura = float(ultima_riga['Close'])
                ema_val = float(ultima_riga['EMA'])
                rsi_val = float(ultima_riga['RSI'])
                banda_inf = float(ultima_riga['BBL'])
                banda_sup = float(ultima_riga['BBU'])

                # LA TUA LOGICA DEGLI ALERT CON PARAMETRI DINAMICI
                buy_condition = (chiusura > ema_val) and (chiusura <= banda_inf) and (rsi_val < rsi_soglia_buy)
                sell_condition = (chiusura >= banda_sup) or (rsi_val > rsi_soglia_sell)

                # 4. L'INTERFACCIA VISIVA DEI RISULTATI
                with [col1, col2, col3][i % 3]:
                    st.subheader(f"🏢 {ticker}")
                    st.write(f"**Prezzo:** {chiusura:.2f}")
                    st.write(f"**RSI ({rsi_len}):** {rsi_val:.2f}")
                    st.write(f"**Trend EMA ({ema_len}):** {'🟢 Rialzista' if chiusura > ema_val else '🔴 Ribassista'}")
                    
                    if buy_condition:
                        st.success("🟢 SEGNALE DI ACQUISTO (BUY)!")
                    elif sell_condition:
                        st.error("🔴 SEGNALE DI VENDITA (SELL)!")
                    else:
                        st.info("⚪ Neutro")
                    
                    st.markdown("---") 
                    
            except Exception as e:
                st.error(f"Si è verificato un errore con {ticker}: {e}")
