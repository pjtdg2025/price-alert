import logging
import requests
import os
import asyncio
import nest_asyncio
from datetime import datetime
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === Setup Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Load Tokens from Environment Variables ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Example: https://your-app.onrender.com

# === Load Futures Tickers from Binance ===
def get_usdt_futures_symbols():
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
    response = requests.get(url)
    futures = {}
    if response.status_code == 200:
        data = response.json()
        for s in data['symbols']:
            if s['contractType'] == 'PERPETUAL' and s['quoteAsset'] == 'USDT':
                futures[s['symbol']] = {}
    return futures

coins = get_usdt_futures_symbols()

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is active and ready. Send a ticker like BTC or ETH.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.upper().strip()
    matched = [symbol for symbol in coins if text in symbol]

    if matched:
        response = "Found matching tickers:\n" + "\n".join(f"- {m}" for m in matched)
    else:
        response = f"No matching tickers found for {text}"

    await update.message.reply_text(response)

# === Webhook Handler ===
async def make_webhook_handler(application: Application):
    async def telegram_webhook_handler(request):
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(text="ok")

    return telegram_webhook_handler

async def handle_root(request):
    return web.Response(text="Bot is running.")

# === Main Application Setup ===
async def main():
    # Build Telegram application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Set webhook
    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")

    # Create aiohttp app
    aio_app = web.Application()
    aio_app.router.add_get("/", handle_root)
    aio_app.router.add_post("/webhook", await make_webhook_handler(application))

    # Start aiohttp server
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("Bot is live and webhook is set.")
    # Run the Telegram polling loop (just to keep it alive)
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
