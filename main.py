import logging
import requests
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
import asyncio
import nest_asyncio

# === YOUR BOT TOKEN ===
TELEGRAM_TOKEN = '7602575751:AAFLeulkFLCz5uhh6oSk39Er6Frj9yyjts0'

# === ENABLE LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === LOAD ALL USDT PERPETUAL FUTURES FROM BINANCE ===
def get_usdt_futures_symbols():
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
    response = requests.get(url)
    futures = {}
    if response.status_code == 200:
        data = response.json()
        for s in data['symbols']:
            if s['contractType'] == 'PERPETUAL' and s['quoteAsset'] == 'USDT':
                futures[s['symbol']] = {
                    'min_price': None,
                    'max_price': None,
                    'active': False,
                    'chat_id': None,
                    'last_price': None
                }
    return futures

coins = get_usdt_futures_symbols()

def get_symbol_message(symbol):
    data = coins[symbol]
    min_set = data['min_price'] is not None
    max_set = data['max_price'] is not None

    min_button = InlineKeyboardButton(
        "✅ Min" if min_set else "Min",
        callback_data=f"min|{symbol}"
    )
    max_button = InlineKeyboardButton(
        "✅ Max" if max_set else "Max",
        callback_data=f"max|{symbol}"
    )

    keyboard = [
        [min_button, max_button],
        [InlineKeyboardButton("🔕 OFF" if data['active'] else "🔔 ON", callback_data=f"toggle|{symbol}")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    min_display = data['min_price'] if data['min_price'] is not None else "Not set"
    max_display = data['max_price'] if data['max_price'] is not None else "Not set"
    text = f"{symbol}\nMin Price: {min_display}\nMax Price: {max_display}\nStatus: {'ON' if data['active'] else 'OFF'}"
    return text, markup

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is ready. Type part of a ticker (e.g. BTC)")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip().upper()
    chat_id = update.effective_chat.id

    if context.chat_data.get('expecting_price') and all(k in context.chat_data for k in ('set_symbol', 'price_type')):
        symbol = context.chat_data['set_symbol']
        price_type = context.chat_data['price_type']
        try:
            price = float(user_input)
            if price_type == 'min':
                coins[symbol]['min_price'] = price
            elif price_type == 'max':
                coins[symbol]['max_price'] = price
            coins[symbol]['chat_id'] = chat_id
            coins[symbol]['active'] = True
            await update.message.reply_text(f"✅ {price_type.upper()} price for {symbol} set at {price}.")
            text, markup = get_symbol_message(symbol)
            await update.message.reply_text(text=text, reply_markup=markup)
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please enter a valid price:")
            return

        context.chat_data.clear()
        return

    if context.chat_data.get('expecting_price') and ('set_symbol' not in context.chat_data or 'price_type' not in context.chat_data):
        await update.message.reply_text("⚠️ Something went wrong. Please select Min or Max again.")
        context.chat_data.clear()
        return

    matches = sorted([s for s in coins if user_input in s])
    if len(matches) == 1:
        symbol = matches[0]
        context.chat_data['set_symbol'] = symbol
        text, markup = get_symbol_message(symbol)
        await update.message.reply_text(f"🔍 Select Min or Max price for {symbol}:", reply_markup=markup)
    elif len(matches) > 1:
        keyboard = [
            [InlineKeyboardButton(symbol, callback_data=f"select|{symbol}")] for symbol in matches[:10]
        ]
        await update.message.reply_text("🔍 Select a symbol:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("❌ No matching tickers found. Try again.")

async def select_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, symbol = query.data.split('|')
    context.chat_data['set_symbol'] = symbol
    text, markup = get_symbol_message(symbol)
    await query.message.reply_text(f"🔍 Select Min or Max price for {symbol}:", reply_markup=markup)

async def price_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    price_type, symbol = query.data.split('|')
    context.chat_data['set_symbol'] = symbol
    context.chat_data['price_type'] = price_type
    context.chat_data['expecting_price'] = True
    await query.message.reply_text(f"✏️ Enter {price_type.upper()} price for {symbol}:")

async def toggle_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, symbol = query.data.split('|')
    if coins[symbol]['min_price'] is None and coins[symbol]['max_price'] is None:
        await query.message.reply_text("⚠️ Please set a price first.")
        return
    coins[symbol]['active'] = not coins[symbol]['active']
    text, markup = get_symbol_message(symbol)
    await query.edit_message_text(text=text, reply_markup=markup)

def get_current_price(symbol):
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return float(response.json()['price'])
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
    return None

async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    for symbol, data in coins.items():
        if not data['active'] or (data['min_price'] is None and data['max_price'] is None):
            continue
        current_price = get_current_price(symbol)
        if current_price is None:
            continue
        last_price = data.get('last_price')
        min_target = data['min_price']
        max_target = data['max_price']
        if last_price is not None:
            crossed_min = min_target is not None and last_price > min_target >= current_price
            crossed_max = max_target is not None and last_price < max_target <= current_price
            if crossed_min or crossed_max:
                now_utc = datetime.utcnow().strftime('%H:%M UTC')
                await context.bot.send_message(
                    chat_id=data['chat_id'],
                    text=f"{symbol} hit {current_price} at {now_utc}"
                )
                if crossed_min:
                    coins[symbol]['min_price'] = None
                if crossed_max:
                    coins[symbol]['max_price'] = None
                if coins[symbol]['min_price'] is None and coins[symbol]['max_price'] is None:
                    data['active'] = False
        data['last_price'] = current_price

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alerts = []
    for symbol, data in coins.items():
        if data['active'] and (data['min_price'] is not None or data['max_price'] is not None):
            min_display = data['min_price'] if data['min_price'] is not None else "-"
            max_display = data['max_price'] if data['max_price'] is not None else "-"
            alerts.append(f"{symbol}: Min={min_display}, Max={max_display}")
    if alerts:
        await update.message.reply_text("📋 Active Alerts:\n" + "\n".join(alerts))
    else:
        await update.message.reply_text("ℹ️ No active alerts.")

async def post_init(application: Application):
    application.job_queue.run_repeating(check_prices, interval=10, first=5)

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("alerts", list_alerts))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(toggle_alert, pattern="^toggle\\|"))
    app.add_handler(CallbackQueryHandler(select_symbol, pattern="^select\\|"))
    app.add_handler(CallbackQueryHandler(price_type_selection, pattern="^(min|max)\\|"))
    
    # Error handler
    def error_handler(update, context):
        logger.error(f"Error occurred: {context.error}")

    app.add_error_handler(error_handler)

    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
