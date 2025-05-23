import os
import asyncio
import logging
from aiohttp import web
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# === Configuration ===
BOT_TOKEN = "7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0"
CHAT_ID = 7559598079
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://your-app.onrender.com

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Globals ===
watchlist = {}

# === Telegram Bot ===
app = ApplicationBuilder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Send a Binance Futures ticker (e.g., BTC, ETH).")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()

    if user_id not in watchlist:
        # First message: assume ticker
        symbol = f"{text}USDT"
        price = await get_binance_price(symbol)
        if price:
            context.user_data["symbol"] = symbol
            await update.message.reply_text(f"✅ {symbol} found. Current price: {price}. Enter target price:")
        else:
            await update.message.reply_text("❌ Ticker not found on Binance Futures.")
        return
    else:
        # Second message: assume price
        symbol = context.user_data.get("symbol")
        try:
            target_price = float(text)
            watchlist[symbol] = target_price
            await update.message.reply_text(f"📡 Alert set for {symbol} at {target_price}.")
        except ValueError:
            await update.message.reply_text("❌ Invalid price. Try again.")

async def get_binance_price(symbol: str):
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5)
            if response.status_code == 200:
                return float(response.json()["price"])
    except Exception as e:
        logger.error(f"Error fetching price: {e}")
    return None

async def price_monitor():
    while True:
        for symbol, target in list(watchlist.items()):
            price = await get_binance_price(symbol)
            if price:
                if (price >= target):
                    await app.bot.send_message(chat_id=CHAT_ID, text=f"🚨 {symbol} hit target price {target} (Current: {price})")
                    del watchlist[symbol]
        await asyncio.sleep(15)

# === Webhook ===
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return web.Response()

async def main():
    # Telegram handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start webhook
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", handle_webhook)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()
    logger.info("🌐 Webhook running")

    # Set Telegram webhook
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": f"{WEBHOOK_URL}/webhook"})

    asyncio.create_task(price_monitor())
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
