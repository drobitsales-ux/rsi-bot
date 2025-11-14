import telebot
import requests
import numpy as np
import time
import os
from datetime import datetime
from threading import Thread

# Змінні
TOKEN = '8317841952:AAH1dtIYJ0oh-dhpAVhudqCVZTRrBL6it1g'
CHAT_ID = 7436397755
API_KEY = os.getenv('BINGX_API_KEY')

bot = telebot.TeleBot(TOKEN)

SYMBOLS = ['FARTCOIN-USDT', 'SOL-USDT', 'DOGE-USDT', 'BONK-USDT'] 

INTERVAL = 900
NO_SIGNAL_INTERVAL = 3600
last_no_signal = 0

def get_data(symbol):
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
    params = {'symbol': symbol, 'interval': '15m', 'limit': 100}
    headers = {'X-BX-APIKEY': API_KEY} if API_KEY else {}
    
    try:
        print(f"[REQUEST] → {symbol}")
        r = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"[RESPONSE] {symbol} → {r.status_code}")
        
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                closes = [float(x[4]) for x in data]
                print(f"[DATA] {symbol} → {len(closes)} свічок, остання: {closes[-1]:.6f}")
                return closes
            else:
                print(f"[EMPTY] {symbol} → немає даних у JSON")
        else:
            print(f"[ERROR] {symbol} → {r.status_code}: {r.text}")
        return None
    except Exception as e:
        print(f"[EXCEPTION] {symbol} → {e}")
        return None

def rsi(c):
    if len(c) < 15: return 50
    d = np.diff(c)[-14:]
    g = np.mean(d[d > 0]) if len(d[d > 0]) else 0
    l = np.mean(-d[d < 0]) if len(d[d < 0]) else 1
    return 100 - 100/(1 + g/l)

def generate_signal():
    global last_no_signal
    for sym in SYMBOLS:
        c = get_data(sym)
        if c and len(c) > 14:
            r = rsi(c)
            price = c[-1]
            if r < 40:
                msg = f"BUY {sym}\nЦіна: {price:.6f}\nRSI: {r:.1f}"
                print(f"[SIGNAL] {msg}")
                return msg
            if r > 60:
                msg = f"SELL {sym}\nЦіна: {price:.6f}\nRSI: {r:.1f}"
                print(f"[SIGNAL] {msg}")
                return msg
    return None

def monitor():
    global last_no_signal
    last_no_signal = time.time()
    print(f"[{datetime.now().strftime('%H:%M')}] МОНІТОРИНГ ЗАПУЩЕНО")
    while True:
        try:
            now = time.time()
            sig = generate_signal()
            if sig:
                bot.send_message(CHAT_ID, sig)
                last_no_signal = now
            else:
                if now - last_no_signal >= NO_SIGNAL_INTERVAL:
                    bot.send_message(CHAT_ID, "Сигналів немає")
                    print("Відправлено: Сигналів немає")
                    last_no_signal = now
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")
        time.sleep(INTERVAL)

@bot.message_handler(commands=['signal'])
def cmd_signal(m):
    sig = generate_signal()
    bot.reply_to(m, sig or "Сигналів немає")

if __name__ == '__main__':
    Thread(target=monitor, daemon=True).start()
    print("БОТ ЗАПУЩЕНО")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"[POLLING ERROR] {e}")
            time.sleep(5)
