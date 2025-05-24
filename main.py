import logging
import asyncio
import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    Defaults,
)
from fastapi import FastAPI, Request
import uvicorn

BOT_TOKEN = "7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0"
CHAT_ID = 7559598079
WEBHOOK_URL = "https://price-alert-roro.onrender.com/webhook"
PORT = 10000

user_states = {}
user_alerts = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Static ticker list to avoid geo-block or API issues
async def fetch_binance_futures_tickers():
    # A fixed sample set of popular Binance Futures tickers (uppercase)
    return {
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT",
        "ADAUSDT", "SOLUSDT", "DOGEUSDT", "MATICUSDT",
        "DOTUSDT", "LTCUSDT", "TRXUSDT", "AVAXUSDT",
        "LINKUSDT", "ATOMUSDT", "BCHUSDT", "ALGOUSDT"
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me the Binance Futures ticker (e.g., BTCUSDT)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    text = update.message.text.strip().upper()

    if user_id not in user_states:
        user_states[user_id] = {}

    if user_states[user_id].get("awaiting_price_for"):
        ticker = user_states[user_id].pop("awaiting_price_for")
        try:
            price = float(text)
            user_alerts.setdefault(user_id, {})[ticker] = price
            await update.message.reply_text(f"✅ Alert set for {ticker} at {price}")
        except ValueError:
            await update.message.reply_text("❌ Invalid price. Please enter a numeric value.")
    else:
        valid_tickers = context.bot_data.get("valid_tickers", set())
        if text in valid_tickers:
            user_states[user_id]["awaiting_price_for"] = text
            await update.message.reply_text(f"Enter the price you want to be alerted for {text}:")
        else:
            await update.message.reply_text("❌ Not a valid Binance Futures ticker. Please try again.")

async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    if not user_alerts:
        return
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://fapi.binance.com/fapi/v1/ticker/price")
            r.raise_for_status()
            prices = {item["symbol"]: float(item["price"]) for item in r.json()}

        for user_id, alerts in user_alerts.items():
            to_remove = []
            for ticker, target_price in alerts.items():
                current_price = prices.get(ticker)
                if current_price is not None and current_price >= target_price:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🚨 {ticker} reached {current_price} (target: {target_price})"
                    )
                    to_remove.append(ticker)
            for ticker in to_remove:
                del user_alerts[user_id][ticker]
    except Exception as e:
        logger.error(f"Error checking alerts: {e}")

app = FastAPI()

# Global Application instance will be assigned in main()
application = None

@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return "ok"

@app.get("/")
async def root():
    return {"message": "Bot is running"}

async def main():
    global application

    valid_tickers = await fetch_binance_futures_tickers()

    defaults = Defaults(parse_mode="HTML")
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .defaults(defaults)
        .build()
    )

    application.bot_data["valid_tickers"] = valid_tickers

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = application.job_queue
    job_queue.run_repeating(check_alerts, interval=60, first=10)

    await application.bot.delete_webhook()
    await application.bot.set_webhook(url=WEBHOOK_URL)

    logger.info("🌐 Webhook running")

    await application.initialize()
    await application.start()

if __name__ == "__main__":
    # For local testing, run uvicorn server directly
    import sys
    if "uvicorn" in sys.argv[0]:
        uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
    else:
        asyncio.run(main())
