import os
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters
)

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-service.onrender.com

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = ApplicationBuilder().token(TOKEN).build()

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is live. Send a ticker.")

async def handle_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.strip().upper()
    await update.message.reply_text(f"🔔 Alert set for {ticker}")

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker))

# Aiohttp webhook server
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response()

async def main():
    await app.initialize()
    app.bot.delete_webhook()
    app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

    # Start webhook server
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", handle_webhook)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()

    logger.info("🌐 Webhook is live.")
    await app.start()
    await app.updater.start_polling()  # Optional
    await app.updater.idle()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
