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

# === HANDLERS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received /start command")
    await update.message.reply_text("✅ Bot is active and ready.")

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 List of alerts will go here.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💬 You said: " + update.message.text)

async def toggle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Toggled alert")

async def select_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Symbol selected")

async def price_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Price type selected")

async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    pass  # Placeholder for checking prices

async def post_init(application: Application):
    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    application.job_queue.run_repeating(check_prices, interval=10, first=5)

async def telegram_webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, Application.current.bot)
    await Application.current.initialize()
    await Application.current.process_update(update)
    return web.Response(text="ok")

async def handle(request):
    return web.Response(text="Bot is running.")

def start_web_server():
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", telegram_webhook_handler)
    aio_app.router.add_get("/", handle)
    port = int(os.environ.get("PORT", 10000))
    web.run_app(aio_app, port=port)

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alerts", list_alerts))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(toggle_alert, pattern="^toggle\\|"))
    app.add_handler(CallbackQueryHandler(select_symbol, pattern="^select\\|"))
    app.add_handler(CallbackQueryHandler(price_type_selection, pattern="^(min|max)\\|"))

    Application.current = app  # Store globally for webhook handler
    await app.initialize()
    start_web_server()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
