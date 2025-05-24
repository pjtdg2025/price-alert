import logging
import httpx
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    Defaults,
)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
WEBHOOK_URL = "https://your-deployment-url.com/webhook"  # your public HTTPS webhook url

app = FastAPI()
user_states = {}
user_alerts = {}
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Replace with your preferred Binance Futures tickers or fetch dynamically
VALID_TICKERS = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOGEUSDT", "MATICUSDT", "DOTUSDT", "LTCUSDT"
}

# Create Telegram bot Application globally
defaults = Defaults(parse_mode="HTML")
telegram_app = Application.builder().token(BOT_TOKEN).defaults(defaults).build()
telegram_app.bot_data["valid_tickers"] = VALID_TICKERS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Send me a Binance Futures ticker (e.g., BTCUSDT) to set a price alert."
    )


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
            await update.message.reply_text("❌ Invalid price. Please enter a number.")
    else:
        if text in VALID_TICKERS:
            user_states[user_id]["awaiting_price_for"] = text
            await update.message.reply_text(
                f"Enter the price you want to be alerted for {text}:"
            )
        else:
            await update.message.reply_text(
                "❌ Not a valid Binance Futures ticker. Please try again."
            )


telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    if not user_alerts:
        return
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://fapi.binance.com/fapi/v1/ticker/price")
            r.raise_for_status()
            prices = {item["symbol"]: float(item["price"]) for item in r.json()}

        for user_id, alerts in list(user_alerts.items()):
            to_remove = []
            for ticker, target_price in alerts.items():
                current_price = prices.get(ticker)
                if current_price is not None and current_price >= target_price:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🚨 {ticker} price alert!\nCurrent price: {current_price} (Target: {target_price})"
                    )
                    to_remove.append(ticker)
            for ticker in to_remove:
                del user_alerts[user_id][ticker]
            if not user_alerts[user_id]:
                del user_alerts[user_id]
    except Exception as e:
        logger.error(f"Error in check_alerts: {e}")


telegram_app.job_queue.run_repeating(check_alerts, interval=60, first=10)


@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.update_queue.put(update)
    return {"ok": True}


@app.get("/")
async def root():
    return {"message": "Bot is running"}


@app.on_event("startup")
async def startup_event():
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.delete_webhook()
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    logger.info("Webhook set")


@app.on_event("shutdown")
async def shutdown_event():
    await telegram_app.stop()
    await telegram_app.shutdown()
