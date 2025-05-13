import os
import logging
import asyncio
import httpx
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, Application
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

telegram_app: Application = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is active and ready. Send a ticker like BTC or ETH.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.upper()
    possible_tickers = [f"{user_input}USDT", f"{user_input}BUSD"]

    matched = [t for t in possible_tickers if "USDT" in t]

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

async def set_webhook():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            json={"url": f"{WEBHOOK_URL}/webhook"}
        )
        if response.status_code == 200:
            logger.info("✅ Webhook was successfully set.")
        else:
            logger.error(f"❌ Failed to set webhook: {response.text}")

async def telegram_webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return web.Response()

async def main():
    global telegram_app

    telegram_app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))

    # 🟢 FIRST: Initialize bot (must happen before webhook receives updates)
    await telegram_app.initialize()

    # 🟢 THEN: Start aiohttp webhook server
    app = web.Application()
    app.add_routes([web.post("/webhook", telegram_webhook_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    # 🟢 AFTER webhook server is live, start application and set webhook
    await telegram_app.start()
    await set_webhook()

    logger.info("🚀 Bot is live and webhook server is running.")

    # Keeps the app alive
    await telegram_app.updater.start_polling()  # not used, but needed to keep alive
    await telegram_app.updater.idle()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
