import telebot
import requests
import numpy as np
import time
import os
from datetime import datetime
from threading import Thread

# === ЗМІННІ З RENDER ===
TOKEN = '8317841952:AAH1dtIYJ0oh-dhpAVhudqCVZTRrBL6it1g'
CHAT_ID = 7436397755

bot = telebot.TeleBot(TOKEN)

# === ОЧИЩЕННЯ WEBHOOK + ЗАХИСТ ===
try:
    bot.remove_webhook()
    time.sleep(3)
except:
    pass

# === СПИСОК ПАР (42 + FARTCOIN) ===
SYMBOLS = [
    'FARTCOIN-USDT', 'SOL-USDT', 'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'ADA-USDT', 'ORDI-USDT',
    'AVAX-USDT', 'SHIB-USDT', 'LINK-USDT', 'DOT-USDT', 'BCH-USDT', 'NEAR-USDT', 'MATIC-USDT',
    'UNI-USDT', 'KAS-USDT', 'FET-USDT', 'ETC-USDT', 'XLM-USDT', 'APT-USDT', 'HBAR-USDT',
    'SUI-USDT', 'FIL-USDT', 'MKR-USDT', 'ATOM-USDT', 'INJ-USDT', 'GRT-USDT', 'LDO-USDT',
    'VET-USDT', 'OP-USDT', 'ARB-USDT', 'SEI-USDT', 'THETA-USDT', 'GT-USDT', 'RENDER-USDT',
    'FLKI-USDT', 'PYTH-USDT', 'BONK-USDT', 'AAVE-USDT', 'JUP-USDT', 'ONDO-USDT', 'WIF-USDT'
]

INTERVAL = 900  # 15 хвилин
last_no_signal = 0
NO_SIGNAL_INTERVAL = 3600  # 1 година

# === ОТРИМАННЯ ДАНИХ ===
def get_data(symbol):
    try:
        url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
        r = requests.get(url, params={'symbol': symbol, 'interval': '15m', 'limit': 100}, timeout=10)
        time.sleep(0.7)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                return [float(x[4]) for x in data]  # close prices
        print(f"[BingX] {r.status_code} | {symbol}")
        return None
    except Exception as e:
        print(f"[ERROR] {symbol}: {e}")
        return None

# === RSI ===
def calculate_rsi(prices):
    if len(prices) < 15: return 50
    deltas = np.diff(prices)[-14:]
    gain = np.mean(deltas[deltas > 0]) if len(deltas[deltas > 0]) > 0 else 0
    loss = np.mean(-deltas[deltas < 0]) if len(deltas[deltas < 0]) > 0 else 1
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# === ГЕНЕРАЦІЯ СИГНАЛУ ===
def generate_signal():
    global last_no_signal
    for sym in SYMBOLS:
        prices = get_data(sym)
        if prices and len(prices) > 14:
            rsi = calculate_rsi(prices)
            price = prices[-1]
            if rsi < 35:
                return f"BUY {sym}\nЦіна: {price:.4f}\nRSI: {rsi:.1f}"
            if rsi > 65:
                return f"SELL {sym}\nЦіна: {price:.4f}\nRSI: {rsi:.1f}"

    # "Сигналів немає" — 1 раз на годину
    now = time.time()
    if now - last_no_signal >= NO_SIGNAL_INTERVAL:
        last_no_signal = now
        return "Сигналів немає"
    return None

# === МОНИТОРИНГ ===
def monitor():
    print(f"[{datetime.now().strftime('%H:%M')}] БОТ ЗАПУЩЕНО — СКАНУВАННЯ КОЖНІ 15 ХВ")
    while True:
        try:
            signal = generate_signal()
            if signal:
                bot.send_message(CHAT_ID, signal)
                print(f"Відправлено: {signal}")
        except Exception as e:
            print(f"Помилка моніторингу: {e}")
        time.sleep(INTERVAL)

# === КОМАНДИ ===
@bot.message_handler(commands=['signal'])
def handle_signal(message):
    signal = generate_signal()
    if signal:
        bot.reply_to(message, signal)
    else:
        bot.reply_to(message, "Сигналів немає")

# === ЗАПУСК ===
if __name__ == '__main__':
    print("ПОЧИНАЮ POLLING...")
    Thread(target=monitor, daemon=True).start()
    
    # Захист від 409: перезапускаємо при помилці
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Polling впав: {e}. Перезапуск через 10 сек...")
            time.sleep(10)
