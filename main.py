import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Your Telegram Bot Token (embedded directly)
TELEGRAM_BOT_TOKEN = "7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0"

# Command handler for /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello! Bot is running with your token.")

# This function will run every 60 seconds as a job
async def periodic_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    print("Periodic task running...")
    # Here you can add your alert checks and send messages, e.g.:
    # await context.bot.send_message(chat_id=YOUR_CHAT_ID, text="Alert!")

async def main():
    # Build the bot application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register the /start handler
    app.add_handler(CommandHandler("start", start))

    # Add a repeating job every 60 seconds, starting 10 seconds after bot start
    app.job_queue.run_repeating(periodic_task, interval=60, first=10)

    print("Bot started. Press Ctrl+C to stop.")
    # Start the bot
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
