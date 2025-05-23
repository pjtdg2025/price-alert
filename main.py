import os
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters
)

TOKEN = "7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0"
WEBHOOK_URL = "https://price-alert-roro.onrender.com"  # Your Render service URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = ApplicationBuilder().token(TOKEN).build()

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is live. Send me a ticker symbol.")

async def handle_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.strip().upper()
    await update.message.reply_text(f"🔔 Alert set for {ticker}. Now please send me the target price.")

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticker))

# aiohttp webhook handler
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(text="ok")

async def main():
    await app.initialize()

    # Properly delete previous webhook and set new webhook
    await app.bot.delete_webhook()
    await app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

    # Start aiohttp server on Render-assigned port
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", handle_webhook)

    runner = web.AppRunner(aio_app)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))  # Use Render's port or fallback 10000
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("🌐 Webhook running at %s on port %d", WEBHOOK_URL, port)

    # Start the bot
    await app.start()
    await app.updater.start_polling()  # Optional fallback, can remove if you want webhook-only
    await app.updater.idle()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
