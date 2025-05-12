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

# === YOUR BOT TOKEN AND WEBHOOK URL FROM ENVIRONMENT VARIABLES ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g. https://your-service.onrender.com

# === ENABLE LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === LOAD ALL USDT PERPETUAL FUTURES FROM BINANCE ===
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
    await update.message.reply_text("Bot is active and ready. Send a ticker like BTC or ETH.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.upper()
    matches = [symbol for symbol in coins if text in symbol]

    if not matches:
        await update.message.reply_text("No matching tickers found.")
        return

    keyboard = [[InlineKeyboardButton(symbol, callback_data=f"select|{symbol}")] for symbol in matches]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a symbol:", reply_markup=reply_markup)

async def select_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    symbol = query.data.split("|")[1]

    coins[symbol]['chat_id'] = query.message.chat.id
    context.user_data['symbol'] = symbol

    keyboard = [
        [InlineKeyboardButton("Set Min Price", callback_data=f"min|{symbol}")],
        [InlineKeyboardButton("Set Max Price", callback_data=f"max|{symbol}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=f"{symbol} selected. Choose what to set:", reply_markup=reply_markup)

async def price_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    price_type, symbol = query.data.split("|")
    context.user_data['price_type'] = price_type
    await query.edit_message_text(f"Send the {price_type} price for {symbol}.")

async def toggle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    symbol = query.data.split("|")[1]
    coins[symbol]['active'] = not coins[symbol]['active']
    state = "activated" if coins[symbol]['active'] else "deactivated"
    await query.edit_message_text(f"Alerts for {symbol} are now {state}.")

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active_alerts = [s for s in coins if coins[s]['active']]
    if not active_alerts:
        await update.message.reply_text("No active alerts.")
        return
    msg = "Active alerts:\n" + "\n".join(active_alerts)
    await update.message.reply_text(msg)

async def get_current_price(symbol):
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
    response = requests.get(url)
    return float(response.json()["price"]) if response.status_code == 200 else None

async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    for symbol, data in coins.items():
        if not data['active'] or not data['chat_id']:
            continue

        price = await get_current_price(symbol)
        if price is None:
            continue

        alert_msg = None
        if data['min_price'] and price < float(data['min_price']):
            alert_msg = f"🔻 {symbol} dropped below {data['min_price']}: now {price}"
        elif data['max_price'] and price > float(data['max_price']):
            alert_msg = f"🚀 {symbol} rose above {data['max_price']}: now {price}"

        if alert_msg:
            await context.bot.send_message(chat_id=data['chat_id'], text=alert_msg)
            coins[symbol]['active'] = False  # Disable alert after trigger

# === WEBHOOK INIT ===
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

    await app.initialize()  # ✅ FIXED: Needed for webhook processing
    Application.current = app
    start_web_server(app)

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
