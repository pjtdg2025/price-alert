import logging
import os
import asyncio
import json
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Bot Token and Webhook URL ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app-name.onrender.com/webhook

# === Global Application Reference ===
telegram_app = None

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is active. Send a ticker like BTC or ETH.")

async def handle_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    valid_tickers = ["BTC", "ETH", "BNB", "SOL", "DOGE"]  # Extend as needed
    if text in valid_tickers:
        await update.message.reply_text(f"🔔 Alert set for {text}")
    else:
        await update.message.reply_text(f"❌ No matching tickers found for {text}")

# === Webhook Handler ===
async def telegram_webhook_handler(request):
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}")
        return web.Response(status=500)
    return web.Response(status=200)

# === Web Server Setup ===
async def start_webhook():
    app = web.Application()
    app.router.add_post("/webhook", telegram_webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()
    logger.info("🌐 Webhook server running at /webhook")

# === Main Function ===
async def main():
    global telegram_app

    telegram_app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # Add handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker))

    # Start webhook server
    await start_webhook()

    # Remove old webhook (clean start)
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
        await client.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            json={"url": f"{WEBHOOK_URL}/webhook"}
        )

    logger.info("✅ Webhook was successfully set.")
    logger.info("🚀 Bot is live and webhook server is running.")

    # Keep running
    while True:
        await asyncio.sleep(3600)

# === Entry Point ===
if __name__ == "__main__":
    asyncio.run(main())
