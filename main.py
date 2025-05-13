import os
import logging
import asyncio
import httpx
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, CallbackQueryHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is active and ready. Send a ticker like BTC or ETH.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.upper()
    possible_tickers = [f"{user_input}USDT", f"{user_input}BUSD"]

    # Simulate matching tickers (this can be replaced with real Binance API check)
    matched = [t for t in possible_tickers if t.endswith("USDT")]

    if matched:
        buttons = [[InlineKeyboardButton(t, callback_data=t)] for t in matched]
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("Select the ticker:", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"No matching tickers found for {user_input}.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"You selected {query.data}")

async def set_webhook(application):
    async with httpx.AsyncClient() as client:
        url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
        webhook_url = f"{WEBHOOK_URL}/webhook"
        response = await client.post(url, json={"url": webhook_url})
        if response.status_code == 200:
            logger.info("Webhook was successfully set.")
        else:
            logger.error(f"Failed to set webhook: {response.text}")

async def telegram_webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, Application.current.bot)
    await Application.current.process_update(update)
    return web.Response()

async def main():
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Set application for webhook processing
    Application.current = application

    await set_webhook(application)

    app = web.Application()
    app.add_routes([web.post("/webhook", telegram_webhook_handler)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info("Bot is live and webhook is set.")

    # Keep the process alive forever
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
