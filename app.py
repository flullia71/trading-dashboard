import streamlit as st
import yfinance as yf
import pandas_ta as ta
import pandas as pd

# 1. Configurazione della pagina (Titolo e layout largo)
st.set_page_config(page_title="Trading Alert Dashboard", layout="wide")

st.title("📈 Dashboard Alert di Trading")
st.write("Scansiona il mercato in tempo reale alla ricerca di segnali basati sulla tua strategia (EMA 200, Bollinger, RSI).")

# 2. SIDEBAR: Il menu laterale per le configurazioni
st.sidebar.header("⚙️ Impostazioni Strategia")

# Casella di testo per aggiungere/rimuovere azioni al volo
tickers_input = st.sidebar.text_input("Azioni da monitorare (separate da virgola)", "CRM, AAPL, GOOGL, UCG.MI, NVDA, ENEL.MI, ENI.MI")
tickers = [t.strip() for t in tickers_input.split(',')]

# Uno slider interattivo per cambiare l'RSI senza toccare il codice!
rsi_soglia_buy = st.sidebar.slider("Soglia RSI per Acquisto (Ipervenduto)", min_value=10, max_value=50, value=40)

st.sidebar.markdown("---")
st.sidebar.write("Questa app verifica i dati di chiusura giornalieri.")

# 3. IL MOTORE: Pulsante di avvio
if st.button("🚀 Scansiona Mercato Ora", type="primary"):
    st.write("Scansione in corso. Attendere...")
    
    # Creiamo 3 colonne invisibili per affiancare i risultati come in una vera dashboard
    col1, col2, col3 = st.columns(3)
    
    for i, ticker in enumerate(tickers):
        try:
            # Scarichiamo un anno di dati (basta per calcolare l'EMA a 200 giorni)
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y", interval='1d')
            
            if df.empty or len(df) < 200:
                st.warning(f"Dati insufficienti per {ticker}")
                continue

            # Calcoli matematici
            df.ta.ema(length=200, append=True)
            df.ta.rsi(length=14, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.dropna(inplace=True)
            
            if df.empty:
                continue

            # Troviamo le colonne dinamicamente
            ema_col = [col for col in df.columns if col.startswith('EMA')][0]
            rsi_col = [col for col in df.columns if col.startswith('RSI')][0]
            bbl_col = [col for col in df.columns if col.startswith('BBL')][0]
            bbu_col = [col for col in df.columns if col.startswith('BBU')][0]

            # ESTRAIAMO IL PRESENTE (L'ultima riga del grafico)
            ultima_riga = df.iloc[-1]
            chiusura = float(ultima_riga['Close'])
            ema_200 = float(ultima_riga[ema_col])
            rsi_14 = float(ultima_riga[rsi_col])
            banda_inf = float(ultima_riga[bbl_col])
            banda_sup = float(ultima_riga[bbu_col])

            # LA LOGICA DEGLI ALERT (usando lo slider per l'RSI!)
            buy_condition = (chiusura > ema_200) and (chiusura <= banda_inf) and (rsi_14 < rsi_soglia_buy)
            sell_condition = (chiusura >= banda_sup) or (rsi_14 > 70)

            # 4. L'INTERFACCIA VISIVA DEI RISULTATI
            # Distribuiamo i blocchi di testo nelle 3 colonne
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
                
                st.markdown("---") # Linea di separazione
                
        except Exception as e:
            st.error(f"Si è verificato un errore con {ticker}: {e}")
