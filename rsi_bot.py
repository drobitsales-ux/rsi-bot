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
SYMBOLS = ['SOL-USDT', 'XRP-USDT', 'DOGE-USDT']

def get_data(symbol):
    try:
        url = "https://open-api.bingx.com/openApi/swap/v2/quote/klines"
        r = requests.get(url, params={'symbol': symbol, 'interval': '15m', 'limit': 100}, timeout=10)
        time.sleep(0.7)
        if r.status_code == 200:
            d = r.json().get('data', [])
            if d:
                return [float(x[4]) for x in d]  # close
        return None
    except: return None

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
    while True:
        try:
            bot.send_message(CHAT_ID, generate_signal())
        except: pass
        time.sleep(900)

@bot.message_handler(commands=['signal'])
def signal(m):
    bot.reply_to(m, generate_signal())

if __name__ == '__main__':
    Thread(target=monitor, daemon=True).start()
    print("БОТ ЗАПУЩЕНО НА RENDER!")
    bot.polling(none_stop=True)
