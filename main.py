import os
import asyncio
import json
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
import httpx

# === Configuration ===
TOKEN = "7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0"
CHAT_ID = "7559598079"
WEBHOOK_URL = "https://price-alert-roro.onrender.com/webhook"
BINANCE_FUTURES_API = "https://fapi.binance.com/fapi/v1/ticker/price"

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === In-memory storage ===
alerts = {}  # Format: {symbol: target_price}

# === Telegram Bot Setup ===
app = ApplicationBuilder().token(TOKEN).build()

# === Handlers ===
user_states = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Send me a Binance perpetual ticker like `BTCUSDT`.")
    user_states[update.effective_chat.id] = {"stage": "awaiting_ticker"}

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    message = update.message.text.strip().upper()

    if user_id not in user_states:
        await update.message.reply_text("Please send /start to begin.")
        return

    state = user_states[user_id]

    if state["stage"] == "awaiting_ticker":
        # Check if it's a valid Binance Futures ticker
        async with httpx.AsyncClient() as client:
            response = await client.get(BINANCE_FUTURES_API)
            symbols = [item["symbol"] for item in response.json()]
        
        if message in symbols:
            state["ticker"] = message
            state["stage"] = "awaiting_price"
            await update.message.reply_text(f"✅ Got {message}. Now send me the target price.")
        else:
            await update.message.reply_text("❌ Invalid ticker. Try again (e.g., BTCUSDT).")

    elif state["stage"] == "awaiting_price":
        try:
            price = float(message)
            ticker = state["ticker"]
            alerts[ticker] = price
            await update.message.reply_text(f"🔔 Alert set for {ticker} at price {price}")
            del user_states[user_id]
        except ValueError:
            await update.message.reply_text("❌ Invalid price. Please send a number.")

# === Background Price Monitor ===
async def monitor_prices():
    while True:
        if alerts:
            async with httpx.AsyncClient() as client:
                response = await client.get(BINANCE_FUTURES_API)
                prices = {item["symbol"]: float(item["price"]) for item in response.json()}

            for symbol, target in list(alerts.items()):
                if symbol in prices:
                    current_price = prices[symbol]
                    if current_price >= target:
                        await app.bot.send_message(
                            chat_id=CHAT_ID,
                            text=f"🚨 {symbol} has reached the target price of {target} (Current: {current_price})"
                        )
                        del alerts[symbol]
        await asyncio.sleep(15)

# === Webhook Receiver ===
async def telegram_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response()

# === Web Server and Bot Startup ===
async def main():
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Initialize
    await app.initialize()
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
        await client.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            json={"url": WEBHOOK_URL}
        )

    # Start webhook server
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", telegram_webhook)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()
    logger.info("🌐 Webhook running")

    # Start price monitoring
    asyncio.create_task(monitor_prices())

    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
