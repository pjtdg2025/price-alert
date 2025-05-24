import logging
import asyncio
import httpx
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

import os
from aiohttp import web

# Telegram credentials
BOT_TOKEN = "7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0"
CHAT_ID = "7559598079"
WEBHOOK_URL = "https://price-alert-roro.onrender.com/webhook"

# Globals
user_states = {}
alerts = {}
valid_tickers = set()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get list of Binance Perpetual Futures tickers
async def fetch_binance_futures_tickers():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        symbols = r.json()["symbols"]
        return {s["symbol"] for s in symbols if s["contractType"] == "PERPETUAL"}

# Handle /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hi! Send me a Binance Futures ticker like BTCUSDT.")

# Handle text messages (tickers and prices)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.upper().strip()

    # If waiting for price
    if user_id in user_states:
        ticker = user_states[user_id]
        try:
            price = float(text)
            alerts[(user_id, ticker)] = price
            await context.bot.send_message(chat_id=user_id, text=f"✅ Alert set for {ticker} at {price}")
            del user_states[user_id]
        except ValueError:
            await context.bot.send_message(chat_id=user_id, text="Please enter a valid number as price.")
        return

    # If expecting ticker
    if text in valid_tickers:
        user_states[user_id] = text
        await context.bot.send_message(chat_id=user_id, text=f"🪙 {text} found. Now send me the price to alert at.")
    else:
        await context.bot.send_message(chat_id=user_id, text="❌ Not a valid Binance PERPETUAL Futures symbol. Please try again.")

# Price monitor
async def monitor_prices(application):
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                prices = {x["symbol"]: float(x["price"]) for x in response.json()}

                to_remove = []
                for (user_id, ticker), alert_price in alerts.items():
                    current_price = prices.get(ticker)
                    if current_price and current_price >= alert_price:
                        await application.bot.send_message(chat_id=user_id, text=f"🚨 {ticker} hit your alert price: {alert_price}")
                        to_remove.append((user_id, ticker))

                for key in to_remove:
                    del alerts[key]

        except Exception as e:
            logger.error(f"Price monitor error: {e}")
        await asyncio.sleep(10)

# Webhook handler
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.update_queue.put(update)
    return web.Response()

# Main setup
async def main():
    global valid_tickers
    valid_tickers = await fetch_binance_futures_tickers()

    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    asyncio.create_task(monitor_prices(app))

    # Webhook setup
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}")

    # Webhook app server
    webhook_app = web.Application()
    webhook_app.router.add_post("/webhook", handle_webhook)
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000)))
    logger.info("🌐 Webhook running")
    await site.start()

    await app.run_polling()  # fallback for local testing

if __name__ == "__main__":
    asyncio.run(main())
