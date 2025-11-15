import telebot
import requests
import numpy as np
import time
import os
import logging
from datetime import datetime, timezone, timedelta
from flask import Flask, request
from threading import Thread
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === ЛОГУВАННЯ (все видно в Render Logs) ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
log = logging.getLogger(__name__)

# === НАЛАШТУВАННЯ ===
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = int(os.getenv('CHAT_ID'))

WEBHOOK_URL = "https://rsi-bot-4vaj.onrender.com/bot"  # ← Зміни на свій URL!

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === ЧАС КИЄВА (UTC+2) ===
KYIV_TZ = timezone(timedelta(hours=2))

# === СПИСОК ПАР ===
SYMBOLS = [
    'FARTCOIN-USDT', 'SOL-USDT', 'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'ADA-USDT',
    'ORDI-USDT', 'AVAX-USDT', 'SHIB-USDT', 'LINK-USDT', 'DOT-USDT', 'BCH-USDT',
    'NEAR-USDT', 'UNI-USDT', 'KAS-USDT', 'FET-USDT', 'ETC-USDT',
    'XLM-USDT', 'APT-USDT', 'HBAR-USDT', 'SUI-USDT', 'FIL-USDT',
    'ATOM-USDT', 'INJ-USDT', 'GRT-USDT', 'LDO-USDT', 'VET-USDT', 'OP-USDT',
    'ARB-USDT', 'SEI-USDT', 'THETA-USDT', 'RENDER-USDT','PYTH-USDT', 'BONK-USDT', 
    'AAVE-USDT', 'JUP-USDT', 'ONDO-USDT', 'WIF-USDT'
]

INTERVAL = 900  # 15 хвилин
NO_SIGNAL_INTERVAL = 3600  # 1 година
last_no_signal = 0

# === СЕСІЯ З РЕТРАЄМ ===
session = requests.Session()
retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

# === ОТРИМАННЯ ДАНИХ З KUCOIN ===
def get_data(symbol):
    url = "https://api.kucoin.com/api/v1/market/candles"
    params = {
        'symbol': symbol,
        'type': '15min',
        'startAt': int(time.time() - 100 * 900),
        'endAt': int(time.time())
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (RSI-Bot/1.0)'
    }
    
    try:
        log.info(f"[REQUEST] → {symbol}")
        r = session.get(url, params=params, headers=headers, timeout=10)
        log.info(f"[RESPONSE] {symbol} → {r.status_code}")
        
        if r.status_code == 200:
            json_data = r.json()
            if json_data.get('code') == '200000':
                data = json_data.get('data', [])
                if data:
                    data = data[::-1]
                    closes = [float(x[2]) for x in data]
                    highs = [float(x[3]) for x in data]
                    lows = [float(x[4]) for x in data]
                    volumes = [float(x[5]) for x in data]
                    log.info(f"[DATA OK] {symbol} → {len(closes)} свічок | Ціна: {closes[-1]:.6f}")
                    return closes, highs, lows, volumes
                else:
                    log.info(f"[EMPTY DATA] {symbol}")
            else:
                log.info(f"[KUCOIN ERROR] {symbol} → {json_data}")
        else:
            log.info(f"[HTTP ERROR] {symbol} → {r.status_code}: {r.text[:200]}")
        
        time.sleep(0.1)
        return None
    except Exception as e:
        log.info(f"[EXCEPTION] {symbol} → {e}")
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
    e12 = sum(c[-12:])/12
    e26 = sum(c[-26:])/26
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

# === ГЕНЕРАЦІЯ НАЙКРАЩОГО СИГНАЛУ (RSI ≤32 / ≥68) ===
def generate_signal():
    global last_no_signal
    best_signal = None
    best_probability = 0

    for sym in SYMBOLS:
        data = get_data(sym)
        if not data: 
            continue
            
        c, h, l, v = data
        price = c[-1]
        r = rsi(c)
        m, ms = macd(c)
        _, ub, lb = bb(c)
        sk, _ = stoch(c)
        vs = vol_spike(v)
        vw = vwap(h, l, c, v)

        # Базові підтвердження
        confirmations = 0
        direction = None

        # RSI — СУВОРИЙ ФІЛЬТР
        if r <= 32:  # Перепроданність
            confirmations += 2
            direction = "Long"
        elif r >= 68:  # Перекупленість
            confirmations += 2
            direction = "Short"
        else:
            continue  # RSI не в зоні — пропускаємо пару

        # Додаткові підтвердження
        if direction == "Long":
            if m > ms: confirmations += 1
            if price <= lb: confirmations += 1
            if sk < 35: confirmations += 1
            if vs > 1.5: confirmations += 1
            if abs(price - vw) / price < 0.003: confirmations += 1
        else:  # Short
            if m < ms: confirmations += 1
            if price >= ub: confirmations += 1
            if sk > 65: confirmations += 1
            if vs > 1.5: confirmations += 1
            if abs(price - vw) / price < 0.003: confirmations += 1

        probability = min(100, (confirmations / 8) * 100)  # 8 критеріїв
        coin = sym.split('-')[0]

        if probability > best_probability:
            tp = ub if direction == "Long" else lb
            sl = lb * 0.98 if direction == "Long" else ub * 1.02
            best_signal = (
                f"**{coin} {direction}** | `{probability:.0f}%`\n"
                f"RSI: `{r:.1f}` | Stoch: `{sk:.1f}`\n"
                f"ТВХ: `{price:.6f}`\n"
                f"TP: `{tp:.6f}` | SL: `{sl:.6f}`\n"
                f"Час: `{datetime.now(KYIV_TZ).strftime('%H:%M')}`"
            )
            best_probability = probability

    if best_signal and best_probability >= 65:
        return best_signal

    return None

# === МОНІТОРИНГ (9:00–22:00 Київ) ===
def monitor():
    global last_no_signal
    last_no_signal = time.time()
    log.info("МОНІТОРИНГ ЗАПУЩЕНО")
    
    while True:
        try:
            now_kyiv = datetime.now(KYIV_TZ)
            hour = now_kyiv.hour

            # Робота тільки з 9:00 до 22:00 по Києву
            if not (9 <= hour < 22):
                log.info(f"[{now_kyiv.strftime('%H:%M')}] Поза робочим часом (9-22 Київ)")
                time.sleep(300)
                continue

            now = time.time()
            sig = generate_signal()
            if sig:
                bot.send_message(CHAT_ID, sig, parse_mode='Markdown')
                log.info(f"Відправлено: {sig}")
                last_no_signal = now
            else:
                if now - last_no_signal >= NO_SIGNAL_INTERVAL:
                    bot.send_message(CHAT_ID, "Сигналів немає")
                    log.info("Відправлено: Сигналів немає")
                    last_no_signal = now
        except Exception as e:
            log.error(f"[MONITOR ERROR] {e}")
        time.sleep(INTERVAL)

# === WEBHOOK ===
@app.route('/bot', methods=['POST'])
def webhook():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    except Exception as e:
        log.error(f"[WEBHOOK ERROR] {e}")
        return 'Error', 500

@app.route('/')
def index():
    return "RSI Bot живий! Webhook: /bot"

# === КОМАНДИ ===
@bot.message_handler(commands=['signal'])
def cmd_signal(m):
    sig = generate_signal()
    bot.reply_to(m, sig or "Сигналів немає", parse_mode='Markdown')

# === ЗАПУСК ===
if __name__ == '__main__':
    try:
        bot.remove_webhook()
        time.sleep(2)
        log.info("Старий webhook видалено")
    except Exception as e:
        log.error(f"Помилка видалення webhook: {e}")

    try:
        success = bot.set_webhook(url=WEBHOOK_URL)
        if success:
            log.info(f"Webhook встановлено: {WEBHOOK_URL}")
        else:
            log.error("ПОМИЛКА: set_webhook повернув False")
    except Exception as e:
        log.error(f"ПОМИЛКА webhook: {e}")

    Thread(target=monitor, daemon=True).start()
    log.info("Моніторинг запущено")

    log.info("Flask сервер запущено")
    app.run(host='0.0.0.0', port=10000, debug=False)
