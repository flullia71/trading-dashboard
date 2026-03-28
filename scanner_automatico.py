import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import json
import os

# Carico le credenziali gestendo eventuali errori di stringa
gcp_json = os.environ.get("GCP_SERVICE_ACCOUNT")
if not gcp_json:
    raise ValueError("Il segreto GCP_SERVICE_ACCOUNT è vuoto o non trovato!")

creds_dict = json.loads(gcp_json)
sheet_url = os.environ.get("GOOGLE_SHEET_URL")
token = os.environ.get("TELEGRAM_TOKEN")
chat_id = os.environ.get("TELEGRAM_CHAT_ID")

def manda_telegram(msg):
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}&parse_mode=Markdown"
    requests.get(url)

# Connessione GSheets
scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)
workbook = client.open_by_url(sheet_url)
sheet_main = workbook.sheet1
sheet_config = workbook.worksheet("Config")

# Carico Ticker e Storico
tickers = [r['Ticker'].upper() for r in sheet_config.get_all_records() if r.get('Ticker')]
df_storico = pd.DataFrame(sheet_main.get_all_records())

for ticker in tickers:
    try:
        # Calcolo quote
        quote = 0
        if not df_storico.empty:
            st_t = df_storico[df_storico['Ticker'] == ticker]
            quote = pd.to_numeric(st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita']).sum() - \
                    pd.to_numeric(st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita']).sum()

        # Analisi Tecnica
        h = yf.Ticker(ticker).history(period="2y")
        h['EMA'] = h['Close'].ewm(span=200, adjust=False).mean()
        sma = h['Close'].rolling(20).mean(); std = h['Close'].rolling(20).std()
        h['BBL'] = sma - (std * 2); h['BBU'] = sma + (std * 2)
        d = h['Close'].diff(); u = d.clip(lower=0); dw = -1*d.clip(upper=0)
        h['RSI'] = 100 - (100/(1+(u.ewm(com=13).mean()/dw.ewm(com=13).mean())))
        
        last = h.iloc[-1]
        px = last['Close']; rsi = last['RSI']; ema = last['EMA']; bbl = last['BBL']; bbu = last['BBU']

        if quote > 0 and (px >= bbu or rsi > 70):
            manda_telegram(f"🔴 *BOT AUTO*: Vendi {ticker} a {px:.2f}. RSI: {rsi:.1f}")
        elif quote == 0 and (px > ema and px <= bbl and rsi < 40):
            manda_telegram(f"🟢 *BOT AUTO*: Compra {ticker} a {px:.2f}. RSI: {rsi:.1f}")
    except:
        continue
