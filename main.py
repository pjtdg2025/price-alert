import asyncio
import logging
import os
import json
import httpx
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# --- Configuration ---
BOT_TOKEN = "7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0"
CHAT_ID = "7559598079"
WEBHOOK_URL = "https://price-alert-roro.onrender.com"

# --- Globals ---
user_state = {}  # Tracks user input states
alerts = {}      # Format: {'BTCUSDT': [price1, price2], ...}

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Telegram Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Send me a Binance Futures ticker (e.g. BTCUSDT).")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()

    # User is setting price
    if user_state.get(user_id) == "awaiting_price":
        ticker = context.user_data["ticker"]
        try:
            price = float(text)
            alerts.setdefault(ticker, []).append(price)
            await update.message.reply_text(f"✅ Alert set for {ticker} at {price}.")
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number.")
        user_state[user_id] = None
        return

    # User sent a ticker
    symbol_info = await fetch_binance_symbol_info(text)
    if symbol_info:
        context.user_data["ticker"] = text
        user_state[user_id] = "awaiting_price"
        await update.message.reply_text(f"📈 {text} is a valid Binance Futures symbol. Send target price:")
    else:
        await update.message.reply_text("❌ Not a valid Binance Futures ticker. Try again.")

# --- Price Checker ---

async def fetch_binance_symbol_info(symbol):
    async with httpx.AsyncClient() as client:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        try:
            resp = await client.get(url, timeout=10)
            data = resp.json()
            symbols = [s["symbol"] for s in data["symbols"]]
            return symbol if symbol in symbols else None
        except Exception as e:
            logger.error(f"Exchange info fetch failed: {e}")
            return None

async def fetch_price(symbol):
    async with httpx.AsyncClient() as client:
        url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
        try:
            resp = await client.get(url, timeout=10)
            data = resp.json()
            return float(data["price"])
        except Exception as e:
            logger.error(f"Price fetch failed for {symbol}: {e}")
            return None

async def monitor_prices(application):
    while True:
        try:
            for symbol, targets in alerts.items():
                current_price = await fetch_price(symbol)
                if current_price is None:
                    continue
                triggered = [p for p in targets if abs(current_price - p) / p < 0.001]
                for price in triggered:
                    await application.bot.send_message(
                        chat_id=CHAT_ID,
                        text=f"🚨 {symbol} has reached target price: {price} (Current: {current_price})"
                    )
                    alerts[symbol].remove(price)
        except Exception as e:
            logger.error(f"Error in monitor_prices: {e}")
        await asyncio.sleep(15)

# --- Webhook Setup ---

async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response(text="OK")

async def main():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.bot.delete_webhook()
    await app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    await app.start()

    # Webhook server
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", handle_webhook)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()

    logger.info("🌐 Webhook running")

    # Start price monitor
    asyncio.create_task(monitor_prices(app))
    await app.updater.start_polling()  # optional fallback
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
