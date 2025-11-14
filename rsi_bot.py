import telebot
import requests
import numpy as np
import time
import os
from datetime import datetime
from flask import Flask, request
from threading import Thread

# === НАЛАШТУВАННЯ ===
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = int(os.getenv('CHAT_ID'))
BINGX_API_KEY = os.getenv('BINGX_API_KEY')  # ДОДАЙ В RENDER!

WEBHOOK_URL = f"https://rsi-bot-4vaj.onrender.com/bot"  # ЗМІНЮЙ ПРИ РЕДЕПЛОЇ

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === СПИСОК ПАР ===
SYMBOLS = ['FARTCOIN-USDT', 'SOL-USDT', 'DOGE-USDT', 'BONK-USDT']

INTERVAL = 900  # 15 хв
NO_SIGNAL_INTERVAL = 3600  # 1 година
last_no_signal = time.time()

# === ОТРИМАННЯ ДАНИХ ===
def get_data(symbol):
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
    params = {'symbol': symbol, 'interval': '15m', 'limit': 100}
    headers = {'X-BX-APIKEY': BINGX_API_KEY} if BINGX_API_KEY else {}
    
    try:
        print(f"[REQUEST] → {symbol}")
        r = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"[RESPONSE] {symbol} → {r.status_code}")
        
        if r.status_code == 200:
            json_data = r.json()
            data = json_data.get('data', [])
            if data:
                closes = [float(x[4]) for x in data]  # close
                print(f"[DATA OK] {symbol} → {len(closes)} свічок | Остання: {closes[-1]:.6f}")
                return closes
            else:
                print(f"[EMPTY DATA] {symbol} → {json_data}")
        else:
            print(f"[ERROR] {symbol} → {r.status_code}: {r.text}")
        return None
    except Exception as e:
        print(f"[EXCEPTION] {symbol} → {e}")
        return None

# === ІНДИКАТОРИ ===
def rsi(c):
    if len(c) < 15: return 50
    d = np.diff(c)[-14:]
    g = np.mean(d[d > 0]) if len(d[d > 0]) else 0
    l = np.mean(-d[d < 0]) if len(d[d < 0]) else 1
    return 100 - 100/(1 + g/l)

# === СИГНАЛ ===
def generate_signal():
    global last_no_signal
    for sym in SYMBOLS:
        c = get_data(sym)
        if c and len(c) >= 15:
            r = rsi(c)
            price = c[-1]
            print(f"[RSI] {sym} → {r:.1f} | Ціна: {price:.6f}")
            if r < 40:
                msg = f"BUY {sym}\nЦіна: {price:.6f}\nRSI: {r:.1f}"
                print(f"[SIGNAL] {msg}")
                return msg
            if r > 60:
                msg = f"SELL {sym}\nЦіна: {price:.6f}\nRSI: {r:.1f}"
                print(f"[SIGNAL] {msg}")
                return msg
    print("[NO SIGNAL] Жоден актив не відповідає умовам")
    return None

# === МОНІТОРИНГ ===
def monitor():
    global last_no_signal
    print(f"[{datetime.now().strftime('%H:%M')}] МОНІТОРИНГ ЗАПУЩЕНО")
    while True:
        try:
            now = time.time()
            sig = generate_signal()
            if sig:
                bot.send_message(CHAT_ID, sig)
                last_no_signal = now
                print(f"[{datetime.now().strftime('%H:%M')}] Сигнал відправлено!")
            else:
                if now - last_no_signal >= NO_SIGNAL_INTERVAL:
                    bot.send_message(CHAT_ID, "Сигналів немає")
                    last_no_signal = now
                    print(f"[{datetime.now().strftime('%H:%M')}] Відправлено: Сигналів немає")
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")
        time.sleep(INTERVAL)

# === WEBHOOK ===
@app.route('/')
def index():
    print(f"[{datetime.now().strftime('%H:%M')}] Головна сторінка відкрита")
    return "RSI Bot живий! Webhook: /bot"

@app.route('/bot', methods=['POST'])
def webhook():
    print(f"[{datetime.now().strftime('%H:%M')}] Отримано update від Telegram")
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Invalid', 403

# === КОМАНДИ ===
@bot.message_handler(commands=['signal'])
def cmd_signal(m):
    sig = generate_signal()
    bot.reply_to(m, sig or "Сигналів немає")

# === ЗАПУСК ===
if __name__ == '__main__':
    try:
        bot.remove_webhook()
        time.sleep(2)
        print("Старий webhook видалено")
    except:
        pass

    try:
        bot.set_webhook(url=WEBHOOK_URL)
        print(f"Webhook встановлено: {WEBHOOK_URL}")
    except Exception as e:
        print(f"ПОМИЛКА webhook: {e}")

    Thread(target=monitor, daemon=True).start()
    print("Моніторинг запущено")

    app.run(host='0.0.0.0', port=10000)
