import telebot
import requests
import numpy as np
import time
import logging
from datetime import datetime, timezone

# ТВОЇ ДАНІ (вже в коді)
TELEGRAM_TOKEN = '8317841952:AAH1dtIYJ0oh-dhpAVhudqCVZTRrBL6it1g'
CHAT_ID = 7436397755

# ТВОЇ ПАРИ
SYMBOLS = [
    'SOL-USDT', 'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'ADA-USDT', 'ORDI-USDT',
    'AVAX-USDT', 'SHIB-USDT', 'LINK-USDT', 'DOT-USDT', 'BCH-USDT', 'NEAR-USDT', 'MATIC-USDT',
    'UNI-USDT', 'KAS-USDT', 'FET-USDT', 'ETC-USDT', 'XLM-USDT', 'APT-USDT', 'HBAR-USDT',
    'SUI-USDT', 'FIL-USDT', 'MKR-USDT', 'ATOM-USDT', 'INJ-USDT', 'GRT-USDT', 'LDO-USDT',
    'VET-USDT', 'OP-USDT', 'ARB-USDT', 'SEI-USDT', 'THETA-USDT', 'GT-USDT', 'RENDER-USDT',
    'FLKI-USDT', 'PYTH-USDT', 'BONK-USDT', 'AAVE-USDT', 'FARTCOIN-USDT','JUP-USDT', 'ONDO-USDT', 'WIF-USDT'
]

INTERVAL = 900  # 15 хвилин для сигналів
HOLD_INTERVAL = 3600  # 1 година для "Сигналів немає"
LEVERAGE = 10
signals_per_day = 5
START_HOUR_UTC = 7
END_HOUR_UTC = 20

logging.basicConfig(
    filename='/home/RD68/rsi_bot.log',
    level=logging.INFO,
    format='%(asctime)s | %(message)s'
)

bot = telebot.TeleBot(TELEGRAM_TOKEN)
signals_today = 0
last_reset_date = datetime.now(timezone.utc).date()
last_hold_sent = 0  # Час останнього "hold" повідомлення

def reset_counter():
    global signals_today, last_reset_date
    today = datetime.now(timezone.utc).date()
    if today > last_reset_date:
        signals_today = 0
        last_reset_date = today
        logging.info("Лічильник скинуто")

def get_data(symbol):
    try:
        url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
        params = {'symbol': symbol, 'interval': '15m', 'limit': 100}
        r = requests.get(url, params=params, timeout=10)
        time.sleep(0.7)
        if r.status_code == 200:
            d = r.json().get('data', [])
            if d:
                return [float(x[4]) for x in d], [float(x[2]) for x in d], [float(x[3]) for x in d], [float(x[5]) for x in d]
        logging.warning(f"BingX {r.status_code} для {symbol}")
        return None
    except Exception as e:
        logging.error(f"Помилка {symbol}: {e}")
        return None

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
    return sum(t*v[i] for i,t in enumerate(tp)) / sum(v)

def check(sym):
    data = get_data(sym)
    if not data: return None
    c, h, l, v = data
    price = c[-1]
    r = rsi(c); m, ms = macd(c); _, ub, lb = bb(c)
    sk, _ = stoch(c); vs = vol_spike(v); vw = vwap(h, l, c, v)

    # Полегшені умови
    if (r < 40 and m > ms and price <= lb and sk < 35 and vs > 1.0 and price <= vw):
        sl = price * (1 - 0.10/LEVERAGE)
        tp1 = price * (1 + 0.20/LEVERAGE)
        tp2 = price * (1 + 0.40/LEVERAGE)
        return f"BUY {sym}\nЦіна: {price:.4f}\nSL: {sl:.4f}\nTP1: {tp1:.4f}\nTP2: {tp2:.4f}\nRSI: {r:.1f}"

    if (r > 60 and m < ms and price >= ub and sk > 65 and vs > 1.0 and price >= vw):
        sl = price * (1 + 0.10/LEVERAGE)
        tp1 = price * (1 - 0.20/LEVERAGE)
        tp2 = price * (1 - 0.40/LEVERAGE)
        return f"SELL {sym}\nЦіна: {price:.4f}\nSL: {sl:.4f}\nTP1: {tp1:.4f}\nTP2: {tp2:.4f}\nRSI: {r:.1f}"

    return None

def generate_signal():
    global signals_today, last_hold_sent
    reset_counter()
    if signals_today >= signals_per_day: 
        return "Ліміт вичерпано"
    if not (START_HOUR_UTC <= datetime.now(timezone.utc).hour < END_HOUR_UTC):
        return "Поза робочим часом"

    for sym in SYMBOLS:
        sig = check(sym)
        if sig:
            signals_today += 1
            logging.info(f"Сигнал: {sig}")
            return sig

    # "Сигналів немає" 1 раз на годину
    now = time.time()
    if now - last_hold_sent >= 3600:
        last_hold_sent = now
        return "Сигналів немає"
    return ""

# === МОНИТОРИНГ ===
def monitor():
    global last_hold_sent
    last_hold_sent = time.time()
    logging.info("БОТ ЗАПУЩЕНО")
    print("БОТ ЗАПУЩЕНО — BingX API")
    while True:
        try:
            now = datetime.now(timezone.utc).strftime("%H:%M")
            print(f"[{now}] Сканування...")
            sig = generate_signal()
            if sig:
                bot.send_message(CHAT_ID, sig)
                logging.info(f"Відправлено: {sig}")
        except Exception as e:
            logging.error(f"Помилка: {e}")
            print(f"Помилка: {e}")
        time.sleep(INTERVAL)

# === КОМАНДИ ===
@bot.message_handler(commands=['start', 'help'])
def start(m):
    bot.reply_to(m, "Бот активний! BingX API. /signal")

@bot.message_handler(commands=['signal'])
def sig(m):
    bot.reply_to(m, generate_signal())

# === ЗАПУСК ===
if __name__ == '__main__':
    print("Запускаю polling...")
    logging.info("Polling запущено")
    Thread(target=monitor, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logging.error(f"Polling впав: {e}")
            print(f"Polling впав: {e}. Перезапуск через 10с...")
            time.sleep(10)
