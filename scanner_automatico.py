import yfinance as yf
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import json
import os

gcp_raw = os.environ.get("GCP_SERVICE_ACCOUNT", "")
sheet_url = os.environ.get("GOOGLE_SHEET_URL", "")
token = os.environ.get("TELEGRAM_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

def manda_telegram(msg):
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={msg}&parse_mode=Markdown"
    try: requests.get(url)
    except: pass

try:
    creds_dict = json.loads(gcp_raw)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    client = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=scopes))
    
    workbook = client.open_by_url(sheet_url)
    sheet_main = workbook.sheet1
    sheet_config = workbook.worksheet("Config")
    
    tickers = [r['Ticker'].upper() for r in sheet_config.get_all_records() if r.get('Ticker')]
    df_storico = pd.DataFrame(sheet_main.get_all_records())

    for ticker in tickers:
        try:
            quote = 0
            if not df_storico.empty and 'Ticker' in df_storico.columns:
                st_t = df_storico[df_storico['Ticker'] == ticker]
                quote = pd.to_numeric(st_t[st_t['Azione'] == 'Acquisto (Buy)']['Quantita']).sum() - pd.to_numeric(st_t[st_t['Azione'] == 'Vendita (Sell)']['Quantita']).sum()

            h = yf.Ticker(ticker).history(period="2y")
            if h.empty: continue
            
            # Indicatori
            h['EMA'] = h['Close'].ewm(span=200, adjust=False).mean()
            sma = h['Close'].rolling(20).mean(); std = h['Close'].rolling(20).std()
            h['BBL'] = sma - (std * 2); h['BBU'] = sma + (std * 2)
            delta = h['Close'].diff(); up = delta.clip(lower=0); dw = -1*delta.clip(upper=0)
            h['RSI'] = 100 - (100/(1+(up.ewm(com=13, adjust=False).mean()/dw.ewm(com=13, adjust=False).mean())))
            
            h['MACD'] = h['Close'].ewm(span=12, adjust=False).mean() - h['Close'].ewm(span=26, adjust=False).mean()
            h['MACD_Signal'] = h['MACD'].ewm(span=9, adjust=False).mean()
            
            last = h.iloc[-1]; prev = h.iloc[-2]
            px = last['Close']; val = "€" if ticker.endswith(".MI") else "$"

            # Logica MACD
            macd_cross_up = (prev['MACD'] < prev['MACD_Signal']) and (last['MACD'] > last['MACD_Signal'])
            macd_cross_down = (prev['MACD'] > prev['MACD_Signal']) and (last['MACD'] < last['MACD_Signal'])

            # Elaborazione Segnali
            if quote > 0:
                if macd_cross_down:
                    manda_telegram(f"🔴 *SELL (MACD)*: {ticker} a {px:.2f}{val}")
                elif px >= last['BBU'] or last['RSI'] > 70:
                    manda_telegram(f"🔴 *SELL (Pullback)*: {ticker} a {px:.2f}{val}")
            
            elif quote == 0:
                if macd_cross_up and px > last['EMA']:
                    manda_telegram(f"🟢 *BUY (MACD)*: {ticker} a {px:.2f}{val} (Trend in partenza)")
                elif px > last['EMA'] and px <= last['BBL'] and last['RSI'] < 40:
                    manda_telegram(f"🟢 *BUY (Pullback)*: {ticker} a {px:.2f}{val} (Prezzo a sconto)")
        except:
            continue
            
except Exception as e:
    exit(1)
