import telebot
import requests
import numpy as np
import time
import os
from flask import Flask, request
from threading import Thread
from datetime import datetime

# === ЗМІННІ ===
TOKEN = '8317841952:AAH1dtIYJ0oh-dhpAVhudqCVZTRrBL6it1g'
CHAT_ID = 7436397755
WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL') + '/bot'  # Render дасть URL

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === ПАРИ (42 + FARTCOIN) ===
SYMBOLS = [
    'FARTCOIN-USDT', 'SOL-USDT', 'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'ADA-USDT',
    'ORDI-USDT', 'AVAX-USDT', 'SHIB-USDT', 'LINK-USDT', 'DOT-USDT', 'BCH-USDT',
    'NEAR-USDT', 'MATIC-USDT', 'UNI-USDT', 'KAS-USDT', 'FET-USDT', 'ETC-USDT',
    'XLM-USDT', 'APT-USDT', 'HBAR-USDT', 'SUI-USDT', 'FIL-USDT', 'MKR-USDT',
    'ATOM-USDT', 'INJ-USDT', 'GRT-USDT', 'LDO-USDT', 'VET-USDT', 'OP-USDT',
    'ARB-USDT', 'SEI-USDT', 'THETA-USDT', 'GT-USDT', 'RENDER-USDT', 'FLKI-USDT',
    'PYTH-USDT', 'BONK-USDT', 'AAVE-USDT', 'JUP-USDT', 'ONDO-USDT', 'WIF-USDT'
]

INTERVAL = 900
last_no_signal = 0
NO_SIGNAL_INTERVAL = 3600

# === ДАНІ ===
def get_data(symbol):
    try:
        url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
        r = requests.get(url, params={'symbol': symbol, 'interval': '15m', 'limit': 100}, timeout=10)
        time.sleep(0.7)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                return [float(c[4]) for c in data]
        print(f"[BingX] {r.status_code} | {symbol}")
        return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

# === RSI ===
def rsi(prices):
    if len(prices) < 15: return 50
    deltas = np.diff(prices)[-14:]
    gain = np.mean(deltas[deltas > 0]) if np.any(deltas > 0) else 0
    loss = np.mean(-deltas[deltas < 0]) if np.any(deltas < 0) else 1
    return 100 - 100 / (1 + gain / loss)

# === СИГНАЛ ===
def generate_signal():
    global last_no_signal
    for sym in SYMBOLS:
        prices = get_data(sym)
        if prices and len(prices) > 14:
            r = rsi(prices)
            price = prices[-1]
            if r < 35:
                return f"BUY {sym}\nЦіна: {price:.4f}\nRSI: {r:.1f}"
            if r > 65:
                return f"SELL {sym}\nЦіна: {price:.4f}\nRSI: {r:.1f}"

    now = time.time()
    if now - last_no_signal >= NO_SIGNAL_INTERVAL:
        last_no_signal = now
        return "Сигналів немає"
    return None

# === МОНІТОРИНГ ===
def monitor():
    print(f"[{datetime.now().strftime('%H:%M')}] WEBHOOK БОТ ЗАПУЩЕНО")
    while True:
        try:
            sig = generate_signal()
            if sig:
                bot.send_message(CHAT_ID, sig)
                print(f"Відправлено: {sig}")
        except Exception as e:
            print(f"Помилка: {e}")
        time.sleep(INTERVAL)

# === WEBHOOK ===
@app.route('/bot', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Invalid', 403

@bot.message_handler(commands=['signal'])
def cmd_signal(m):
    sig = generate_signal()
    bot.reply_to(m, sig or "Сигналів немає")

# === ЗАПУСК ===
if __name__ == '__main__':
    # Очистити старий webhook
    try:
        bot.remove_webhook()
        time.sleep(2)
    except:
        pass

    # Встановити новий
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"Webhook встановлено: {WEBHOOK_URL}")

    # Запустити моніторинг
    Thread(target=monitor, daemon=True).start()

    # Запустити Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
