import telebot
import requests
import numpy as np
import time
import os
from datetime import datetime
from threading import Thread

# Змінні з Render
TOKEN = '8317841952:AAH1dtIYJ0oh-dhpAVhudqCVZTRrBL6it1g'
CHAT_ID = 7436397755

bot = telebot.TeleBot(TOKEN)

# ВИДАЛЯЄМО СТАРИЙ WEBHOOK (на всяк випадок)
bot.remove_webhook()
time.sleep(1)

SYMBOLS = ['SOL-USDT', 'XRP-USDT', 'DOGE-USDT', 'TON-USDT', 'ADA-USDT']

def get_data(symbol):
    try:
        url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
        r = requests.get(url, params={'symbol': symbol, 'interval': '15m', 'limit': 100}, timeout=10)
        time.sleep(0.7)
        if r.status_code == 200:
            d = r.json().get('data', [])
            if d:
                return [float(x[4]) for x in d]  # close
        print(f"BingX error {r.status_code} for {symbol}")
        return None
    except Exception as e:
        print(f"Request error: {e}")
        return None

def rsi(c):
    if len(c) < 15: return 50
    d = np.diff(c)[-14:]
    g = np.mean(d[d > 0]) if len(d[d > 0]) else 0
    l = np.mean(-d[d < 0]) if len(d[d < 0]) else 1
    return 100 - 100/(1 + g/l)

def generate_signal():
    for sym in SYMBOLS:
        c = get_data(sym)
        if c and len(c) > 14:
            r = rsi(c)
            price = c[-1]
            if r < 35:
                return f"BUY {sym}\nЦіна: {price:.4f}\nRSI: {r:.1f}"
            if r > 65:
                return f"SELL {sym}\nЦіна: {price:.4f}\nRSI: {r:.1f}"
    return "Сигналів немає"

def monitor():
    print("Моніторинг запущено — сигнали кожні 15 хв")
    while True:
        try:
            sig = generate_signal()
            bot.send_message(CHAT_ID, sig)
            print(f"Відправлено: {sig}")
        except Exception as e:
            print(f"Помилка відправки: {e}")
        time.sleep(900)

@bot.message_handler(commands=['signal'])
def signal(m):
    bot.reply_to(m, generate_signal())

if __name__ == '__main__':
    # Запускаємо моніторинг у фоні
    Thread(target=monitor, daemon=True).start()
    
    print("БОТ ЗАПУЩЕНО НА RENDER! Чекаю команди /signal...")
    
    # Polling з захистом від 409
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            if "409" in str(e):
                print("409 Conflict — чекаю 10 сек...")
                time.sleep(10)
            else:
                print(f"Polling error: {e}")
                time.sleep(5)
