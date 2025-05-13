import os
import json
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import httpx

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Load from environment ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://yourapp.onrender.com

# === Create Application globally ===
telegram_app = (
    ApplicationBuilder()
    .token(TOKEN)
    .concurrent_updates(True)
    .build()
)

# === Telegram Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is live. Send a ticker like BTC or ETH.")

async def handle_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()
    if text in ["BTC", "ETH", "BNB", "SOL"]:
        await update.message.reply_text(f"🔔 Alert set for {text}")
    else:
        await update.message.reply_text("❌ Ticker not recognized.")

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

# === Setup aiohttp server ===
async def run_webhook_server():
    app = web.Application()
    app.router.add_post("/webhook", telegram_webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()
    logger.info("🌐 Webhook server running at /webhook")

# === Main ===
async def main():
    # Add handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker))

    # Initialize bot
    await telegram_app.initialize()

    # Start aiohttp webhook server
    await run_webhook_server()

    # Set webhook URL
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
        await client.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            json={"url": f"{WEBHOOK_URL}/webhook"}
        )

    logger.info("✅ Webhook set. Bot is ready.")
    await telegram_app.start()
    await telegram_app.updater.start_polling()  # Optional: for scheduling or internal polling
    await telegram_app.updater.stop()
    await telegram_app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
