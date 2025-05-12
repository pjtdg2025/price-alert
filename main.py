import logging
import requests
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
import asyncio
import nest_asyncio
from aiohttp import web
import os

# === YOUR BOT TOKEN AND WEBHOOK URL ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g. https://your-service-name.onrender.com

# === ENABLE LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === FETCH ALL USDT PERPETUAL FUTURES FROM BINANCE ===
def get_usdt_futures_symbols():
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
    response = requests.get(url)
    futures = {}
    if response.status_code == 200:
        data = response.json()
        for s in data['symbols']:
            if s['contractType'] == 'PERPETUAL' and s['quoteAsset'] == 'USDT':
                futures[s['symbol']] = {
                    'min_price': None,
                    'max_price': None,
                    'active': False,
                    'chat_id': None,
                    'last_price': None
                }
    return futures

coins = get_usdt_futures_symbols()

# === HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is active and ready. Send a ticker like BTC to begin.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip().upper()
    matches = [symbol for symbol in coins if symbol.startswith(query)]

    if not matches:
        await update.message.reply_text("No matching symbols found.")
        return

    keyboard = []
    for match in matches:
        keyboard.append([
            InlineKeyboardButton(match, callback_data=f"select|{match}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a symbol:", reply_markup=reply_markup)

async def select_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    symbol = query.data.split("|")[1]
    chat_id = query.message.chat_id

    coins[symbol]['chat_id'] = chat_id
    keyboard = [
        [InlineKeyboardButton("Set Min Price", callback_data=f"min|{symbol}")],
        [InlineKeyboardButton("Set Max Price", callback_data=f"max|{symbol}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Set alert type for {symbol}:", reply_markup=reply_markup)

async def price_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    price_type, symbol = query.data.split("|")

    context.user_data['setting_price_for'] = (symbol, price_type)
    await query.edit_message_text(f"Send the price for {price_type.upper()} alert on {symbol}.")

async def toggle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    symbol = query.data.split("|")[1]
    coins[symbol]['active'] = not coins[symbol]['active']
    state = "activated" if coins[symbol]['active'] else "deactivated"
    await query.edit_message_text(f"Alerts for {symbol} are now {state}.")

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "Current alerts:\n"
    for symbol, data in coins.items():
        if data['chat_id'] == update.effective_chat.id and (data['min_price'] or data['max_price']):
            msg += f"{symbol} | Min: {data['min_price']} | Max: {data['max_price']} | Active: {data['active']}\n"
    await update.message.reply_text(msg if msg != "Current alerts:\n" else "No alerts set.")

# === CHECK PRICES ===

async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    for symbol, data in coins.items():
        if not data['active'] or not data['chat_id']:
            continue

        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
        try:
            res = requests.get(url)
            current_price = float(res.json()['price'])
            data['last_price'] = current_price
        except:
            continue

        alert_triggered = False
        msg_parts = []

        if data['min_price'] and current_price <= data['min_price']:
            msg_parts.append(f"⬇️ {symbol} dropped below {data['min_price']}! Now: {current_price}")
            alert_triggered = True

        if data['max_price'] and current_price >= data['max_price']:
            msg_parts.append(f"⬆️ {symbol} exceeded {data['max_price']}! Now: {current_price}")
            alert_triggered = True

        if alert_triggered:
            await context.bot.send_message(chat_id=data['chat_id'], text="\n".join(msg_parts))

# === WEBHOOK & SERVER ===

async def post_init(application: Application):
    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    application.job_queue.run_repeating(check_prices, interval=10, first=5)

async def telegram_webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, Application.current.bot)
    await Application.current.process_update(update)
    return web.Response(text="ok")

async def handle(request):
    return web.Response(text="Bot is running.")

def start_web_server(app: Application):
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", telegram_webhook_handler)
    aio_app.router.add_get("/", handle)
    port = int(os.environ.get("PORT", 10000))
    web.run_app(aio_app, port=port)

# === MAIN ===

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alerts", list_alerts))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(toggle_alert, pattern="^toggle\\|"))
    app.add_handler(CallbackQueryHandler(select_symbol, pattern="^select\\|"))
    app.add_handler(CallbackQueryHandler(price_type_selection, pattern="^(min|max)\\|"))

    Application.current = app
    start_web_server(app)

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
