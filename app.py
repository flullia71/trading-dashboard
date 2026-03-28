import streamlit as st
import yfinance as yf
import pandas as pd

# 1. Configurazione della pagina
st.set_page_config(page_title="Trading Alert Dashboard", layout="wide")

st.title("📈 Dashboard Alert di Trading")
st.write("Scansiona il mercato in tempo reale alla ricerca di segnali basati sulla tua strategia (EMA 200, Bollinger, RSI).")

# 2. SIDEBAR: Il menu laterale per le configurazioni
st.sidebar.header("⚙️ Impostazioni Strategia")

tickers_input = st.sidebar.text_input("Azioni da monitorare (separate da virgola)", "CRM, AAPL, GOOGL, UCG.MI, NVDA, ENEL.MI, ENI.MI")
tickers = [t.strip() for t in tickers_input.split(',')]

rsi_soglia_buy = st.sidebar.slider("Soglia RSI per Acquisto (Ipervenduto)", min_value=10, max_value=50, value=40)

st.sidebar.markdown("---")
st.sidebar.write("Questa app verifica i dati di chiusura giornalieri.")

# 3. IL MOTORE: Pulsante di avvio
if st.button("🚀 Scansiona Mercato Ora", type="primary"):
    st.write("Scansione in corso. Attendere...")
    
    col1, col2, col3 = st.columns(3)
    
    for i, ticker in enumerate(tickers):
        try:
            # Scarichiamo i dati
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y", interval='1d')
            
            if df.empty or len(df) < 200:
                st.warning(f"Dati insufficienti per {ticker}")
                continue

            # ---------------------------------------------------------
            # LA NUOVA MATEMATICA NATIVA (Senza pandas_ta)
            # ---------------------------------------------------------
            
            # Calcolo EMA 200
            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            
            # Calcolo Bande di Bollinger (20, 2)
            sma_20 = df['Close'].rolling(window=20).mean()
            std_20 = df['Close'].rolling(window=20).std()
            df['BBL'] = sma_20 - (std_20 * 2) # Banda Inferiore
            df['BBU'] = sma_20 + (std_20 * 2) # Banda Superiore
            
            # Calcolo RSI 14
            delta = df['Close'].diff()
            up = delta.clip(lower=0)
            down = -1 * delta.clip(upper=0)
            ema_up = up.ewm(com=13, adjust=False).mean()
            ema_down = down.ewm(com=13, adjust=False).mean()
            rs = ema_up / ema_down
            df['RSI_14'] = 100 - (100 / (1 + rs))
            
            # Pulizia dati
            df.dropna(inplace=True)
            if df.empty:
                continue

            # ESTRAIAMO IL PRESENTE (L'ultima riga del grafico)
            ultima_riga = df.iloc[-1]
            chiusura = float(ultima_riga['Close'])
            ema_200 = float(ultima_riga['EMA_200'])
            rsi_14 = float(ultima_riga['RSI_14'])
            banda_inf = float(ultima_riga['BBL'])
            banda_sup = float(ultima_riga['BBU'])

            # LA LOGICA DEGLI ALERT
            buy_condition = (chiusura > ema_200) and (chiusura <= banda_inf) and (rsi_14 < rsi_soglia_buy)
            sell_condition = (chiusura >= banda_sup) or (rsi_14 > 70)

            # 4. L'INTERFACCIA VISIVA DEI RISULTATI
            with [col1, col2, col3][i % 3]:
                st.subheader(f"🏢 {ticker}")
                st.write(f"**Prezzo Attuale:** {chiusura:.2f}")
                st.write(f"**Valore RSI:** {rsi_14:.2f}")
                
                if buy_condition:
                    st.success("🟢 SEGNALE DI ACQUISTO (BUY)!")
                elif sell_condition:
                    st.error("🔴 SEGNALE DI VENDITA (SELL)!")
                else:
                    st.info("⚪ Nessun Segnale (Neutro)")
                
                st.markdown("---") 
                
        except Exception as e:
            st.error(f"Si è verificato un errore con {ticker}: {e}")
