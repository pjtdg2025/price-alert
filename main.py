from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import Application, ContextTypes, MessageHandler, filters
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0"

app = FastAPI()

bot = Bot(token=TOKEN)
telegram_app = Application.builder().token(TOKEN).build()

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_received = update.message.text
    reply_text = f"You sent ticker: {text_received}. Bot is working!"
    await update.message.reply_text(reply_text)

telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), echo))

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot)  # <-- fixed here
    await telegram_app.update_queue.put(update)
    await telegram_app.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "Bot is running"}
