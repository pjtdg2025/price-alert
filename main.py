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

# === CONFIGURATION ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Example: https://your-service-name.onrender.com

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === GLOBAL VARIABLES ===
bot_app = None  # Will hold the Application instance
user_states = {}  # Tracks chat_id -> {'step': str, 'symbol': str}
coins = {}  # Will be filled with Binance futures info

# === LOAD USDT PERPETUAL FUTURES SYMBOLS ===
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

# === COMMAND HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is active and ready. Send a symbol like 'BTC' to get started.")

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = [s for s, data in coins.items() if data['active'] and data['chat_id'] == update.effective_chat.id]
    if active:
        msg = "Active alerts:\n" + "\n".join(active)
    else:
        msg = "No active alerts."
    await update.message.reply_text(msg)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip().upper()

    # Handle stateful flow
    state = user_states.get(chat_id)
    if state:
        symbol = state['symbol']
        if state['step'] in ('min', 'max'):
            try:
                price = float(text)
                coins[symbol][f"{state['step']}_price"] = price
                await update.message.reply_text(f"{state['step']} price for {symbol} set to {price}. Alert activated.")
                coins[symbol]['chat_id'] = chat_id
                coins[symbol]['active'] = True
                del user_states[chat_id]
            except ValueError:
                await update.message.reply_text("Invalid price. Please enter a number.")
        return

    # Match symbol
    matches = [s for s in coins if text in s]
    if not matches:
        await update.message.reply_text("No matching symbol.")
    elif len(matches) == 1:
        await show_price_type_buttons(update, matches[0])
    else:
        buttons = [[InlineKeyboardButton(s, callback_data=f"select|{s}")] for s in matches[:10]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("Multiple matches found:", reply_markup=reply_markup)

async def select_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    symbol = query.data.split("|")[1]
    await show_price_type_buttons(query, symbol)

async def show_price_type_buttons(target, symbol):
    buttons = [
        [InlineKeyboardButton("Set Min Price", callback_data=f"min|{symbol}")],
        [InlineKeyboardButton("Set Max Price", callback_data=f"max|{symbol}")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await target.message.reply_text(f"{symbol} selected. Choose alert type:", reply_markup=reply_markup)

async def price_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    step, symbol = query.data.split("|")
    user_states[query.message.chat.id] = {'step': step, 'symbol': symbol}
    await query.message.reply_text(f"Send the price to set for {symbol} ({step.upper()})")

async def toggle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    symbol = query.data.split("|")[1]
    coins[symbol]['active'] = not coins[symbol]['active']
    state = "ON" if coins[symbol]['active'] else "OFF"
    await query.message.reply_text(f"Alert for {symbol} is now {state}.")

async def get_current_price(symbol):
    url = f'https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}'
    response = requests.get(url)
    if response.status_code == 200:
        return float(response.json()['price'])
    return None

async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    for symbol, data in coins.items():
        if not data['active'] or not data['chat_id']:
            continue
        price = await get_current_price(symbol)
        if price is None:
            continue

        send_alert = False
        if data['min_price'] and price <= data['min_price']:
            send_alert = True
        if data['max_price'] and price >= data['max_price']:
            send_alert = True

        if send_alert and price != data['last_price']:
            msg = f"{symbol} has hit your alert level. Current price: {price}"
            await context.bot.send_message(chat_id=data['chat_id'], text=msg)
            data['last_price'] = price

# === WEBHOOK SETUP ===
async def post_init(application: Application):
    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    application.job_queue.run_repeating(check_prices, interval=10, first=5)

async def telegram_webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)
    return web.Response(text="ok")

async def handle(request):
    return web.Response(text="Bot is running.")

def start_web_server(app: Application):
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", telegram_webhook_handler)
    aio_app.router.add_get("/", handle)
    port = int(os.environ.get("PORT", 10000))
    web.run_app(aio_app, port=port)

# === MAIN FUNCTION ===
async def main():
    global bot_app
    bot_app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("alerts", list_alerts))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    bot_app.add_handler(CallbackQueryHandler(toggle_alert, pattern="^toggle\\|"))
    bot_app.add_handler(CallbackQueryHandler(select_symbol, pattern="^select\\|"))
    bot_app.add_handler(CallbackQueryHandler(price_type_selection, pattern="^(min|max)\\|"))

    start_web_server(bot_app)

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
