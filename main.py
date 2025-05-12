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

# === YOUR BOT TOKEN ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Full HTTPS URL to your webhook endpoint

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

# === Start Command Handler ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply("Welcome to the Binance Futures Price Alert Bot! Use /alerts to manage your alerts.")

# === Handle Text Messages ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles regular text messages."""
    await update.message.reply("Send me a command or type /alerts to set up price alerts.")

# === Select Symbol ===
async def select_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles symbol selection."""
    query = update.callback_query
    selected_symbol = query.data.split('|')[1]
    await query.answer()
    await query.edit_message_text(f"Selected symbol: {selected_symbol}")

# === Price Type Selection ===
async def price_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles price type selection (min/max)."""
    query = update.callback_query
    price_type = query.data.split('|')[0]
    await query.answer()
    await query.edit_message_text(f"Price type selected: {price_type}")

# === Toggle Alert ===
async def toggle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggles the alert status."""
    query = update.callback_query
    symbol = query.data.split('|')[1]
    current_status = coins[symbol]['active']
    coins[symbol]['active'] = not current_status
    status_text = "activated" if coins[symbol]['active'] else "deactivated"
    await query.answer()
    await query.edit_message_text(f"Alert for {symbol} {status_text}")

# === List Alerts ===
async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all current price alerts."""
    active_alerts = [f"{symbol}: {coins[symbol]['active']}" for symbol in coins if coins[symbol]['active']]
    await update.message.reply("\n".join(active_alerts) if active_alerts else "No active alerts.")

# === Check Prices ===
async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    """Checks the prices and triggers alerts."""
    for symbol, coin in coins.items():
        # Check if the price is above or below the set price and trigger alerts
        pass  # Logic for checking prices will be here

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

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))  # Start command handler
    app.add_handler(CommandHandler("alerts", list_alerts))  # Alerts command handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))  # Text message handler
    app.add_handler(CallbackQueryHandler(toggle_alert, pattern="^toggle\\|"))  # Toggle alert handler
    app.add_handler(CallbackQueryHandler(select_symbol, pattern="^select\\|"))  # Select symbol handler
    app.add_handler(CallbackQueryHandler(price_type_selection, pattern="^(min|max)\\|"))  # Price type selection handler

    # Do not call app.run_polling() here
    Application.current = app  # Store globally for webhook handler
    start_web_server(app)

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())  # Ensure that 'main()' is awaited properly
