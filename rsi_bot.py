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

WEBHOOK_URL = "https://rsi-bot-4vaj.onrender.com/bot"  # ← Зміни на свій URL!

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === СПИСОК ПАР (Binance: без дефісу) ===
SYMBOLS = [
    'FARTCOINUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'TONUSDT', 'ADAUSDT',
    'ORDIUSDT', 'AVAXUSDT', 'SHIBUSDT', 'LINKUSDT', 'DOTUSDT', 'BCHUSDT',
    'NEARUSDT', 'MATICUSDT', 'UNIUSDT', 'KASUSDT', 'FETUSDT', 'ETCUSDT',
    'XLMUSDT', 'APTUSDT', 'HBARUSDT', 'SUIUSDT', 'FILUSDT', 'MKRUSDT',
    'ATOMUSDT', 'INJUSDT', 'GRTUSDT', 'LDOUSDT', 'VETUSDT', 'OPUSDT',
    'ARBUSDT', 'SEIUSDT', 'THETAUSDT', 'GTUSDT', 'RENDERUSDT', 'FLKIUSDT',
    'PYTHUSDT', 'BONKUSDT', 'AAVEUSDT', 'JUPUSDT', 'ONDOUSDT', 'WIFUSDT'
]

INTERVAL = 900  # 15 хвилин
NO_SIGNAL_INTERVAL = 3600  # 1 година
last_no_signal = 0

# === ДАНІ З BINANCE ===
def get_data(symbol):
    binance_symbol = symbol  # Вже без дефісу
    url = "https://api.binance.com/api/v3/klines"
    params = {
        'symbol': binance_symbol,
        'interval': '15m',
        'limit': 100
    }
    
    try:
        print(f"[REQUEST] → {symbol}")
        r = requests.get(url, params=params, timeout=10)
        print(f"[RESPONSE] {symbol} → {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                closes = [float(x[4]) for x in data]
                highs = [float(x[2]) for x in data]
                lows = [float(x[3]) for x in data]
                volumes = [float(x[5]) for x in data]
                print(f"[DATA OK] {symbol} → {len(closes)} свічок | Ціна: {closes[-1]:.6f}")
                time.sleep(0.1)  # Binance: 1200 запитів/хв
                return closes, highs, lows, volumes
            else:
                print(f"[EMPTY DATA] {symbol}")
        else:
            print(f"[HTTP ERROR] {symbol} → {r.status_code}: {r.text[:200]}")
        
        time.sleep(0.1)
        return None
    except Exception as e:
        print(f"[EXCEPTION] {symbol} → {e}")
        time.sleep(0.1)
        return None

# === ІНДИКАТОРИ ===
def rsi(c):
    if len(c) < 15: return 50
    d = np.diff(c)[-14:]
    g = np.mean(d[d > 0]) if len(d[d > 0]) else 0
    l = np.mean(-d[d < 0]) if len(d[d < 0]) else 1
    return 100 - 100/(1 + g/l)

def macd(c):
    if len(c) < 26: return 0, 0
    e12 = sum(c[-12:])/12; e26 = sum(c[-26:])/26
    return e12 - e26, 0

def bb(c):
    if len(c) < 20: return 0, 0, 0
    s = sum(c[-20:])/20
    dev = (sum((x-s)**2 for x in c[-20:])/19)**0.5
    return s, s + 2*dev, s - 2*dev

def stoch(c):
    if len(c) < 14: return 50, 50
    low, high = min(c[-14:]), max(c[-14:])
    k = 100 * (c[-1] - low)/(high - low) if high != low else 50
    return k, k

def vol_spike(v):
    if len(v) < 20: return 1.0
    return v[-1] / (sum(v[-20:])/20)

def vwap(h, l, c, v):
    tp = [(h[i]+l[i]+c[i])/3 for i in range(len(c))]
    return sum(t*v[i] for i,t in enumerate(tp)) / sum(v) if sum(v) > 0 else c[-1]

# === ГЕНЕРАЦІЯ СИГНАЛУ ===
def generate_signal():
    global last_no_signal
    for sym in SYMBOLS:
        data = get_data(sym)
        if not data: continue
        c, h, l, v = data
        price = c[-1]
        r = rsi(c)
        m, ms = macd(c)
        _, ub, lb = bb(c)
        sk, _ = stoch(c)
        vs = vol_spike(v)
        vw = vwap(h, l, c, v)

        confirmations = 0
        if m > ms: confirmations += 1
        if m < ms: confirmations += 1
        if price <= lb or price >= ub: confirmations += 1
        if sk < 35 or sk > 65: confirmations += 1
        if vs > 1.0: confirmations += 1
        if price <= vw or price >= vw: confirmations += 1

        probability = max(0, (confirmations / 5) * 100)

        # ВИДАЛЯЄМО "USDT"
        coin = sym[:-4]

        if probability >= 60 and m > ms:
            tp = ub
            sl = lb * 0.98
            return f"{coin} Long, {probability}%, RSI {r:.1f}\nТВХ {price:.4f}\nTP {tp:.4f}\nSL {sl:.4f}"
        
        if probability >= 60 and m < ms:
            tp = lb
            sl = ub * 1.02
            return f"{coin} Short, {probability}%, RSI {r:.1f}\nТВХ {price:.4f}\nTP {tp:.4f}\nSL {sl:.4f}"
    
    return None

# === МОНІТОРИНГ ===
def monitor():
    global last_no_signal
    last_no_signal = time.time()
    print(f"[{datetime.now().strftime('%H:%M')}] МОНІТОРИНГ ЗАПУЩЕНО")
    
    # ТЕСТ API BINANCE
    print(f"[{datetime.now().strftime('%H:%M')}] ТЕСТ API BINANCE...")
    test_data = get_data('FARTCOINUSDT')
    if test_data:
        print(f"[TEST OK] Отримано {len(test_data[0])} свічок | Ціна: {test_data[0][-1]:.6f}")
    else:
        print("[TEST FAILED] Немає даних з Binance")

    # ПЕРШИЙ СКАН
    print(f"[{datetime.now().strftime('%H:%M')}] ПЕРШИЙ СКАН...")
    sig = generate_signal()
    if sig:
        bot.send_message(CHAT_ID, sig)
        print(f"Відправлено: {sig}")
    else:
        print("Сигналів немає на старті")

    # ОСНОВНИЙ ЦИКЛ
    while True:
        try:
            now = time.time()
            sig = generate_signal()
            if sig:
                bot.send_message(CHAT_ID, sig)
                print(f"Відправлено: {sig}")
                last_no_signal = now
            else:
                if now - last_no_signal >= NO_SIGNAL_INTERVAL:
                    bot.send_message(CHAT_ID, "Сигналів немає")
                    print("Відправлено: Сигналів немає")
                    last_no_signal = now
        except Exception as e:
            print(f"[MONITOR ERROR] {e}")
        time.sleep(INTERVAL)

# === WEBHOOK ===
@app.route('/bot', methods=['POST'])
def webhook():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        print(f"[WEBHOOK] Отримано update")
        return '', 200
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
        return 'Error', 500

@app.route('/')
def index():
    return "RSI Bot живий! Webhook: /bot"

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
    except Exception as e:
        print(f"Помилка видалення webhook: {e}")

    try:
        success = bot.set_webhook(url=WEBHOOK_URL)
        if success:
            print(f"Webhook встановлено: {WEBHOOK_URL}")
        else:
            print("ПОМИЛКА: set_webhook повернув False")
    except Exception as e:
        print(f"ПОМИЛКА webhook: {e}")

    Thread(target=monitor, daemon=True).start()
    print("Моніторинг запущено")

    print("Flask сервер запущено")
    app.run(host='0.0.0.0', port=10000, debug=False)
