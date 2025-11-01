import logging
import sqlite3
import secrets
import time
from datetime import datetime, timedelta
import requests
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from apscheduler.schedulers.background import BackgroundScheduler

# ================== CONFIGURATION ==================
TELEGRAM_BOT_TOKEN = "8341913567:AAHWf8fa9J-dl5IrGYWRvEnPJNNjM2kEwlY"  # Replace with your bot token
USDT_RECEIVE_ADDRESS = "0xc64C9Ab178B4613DB93a2bA708E1442fC4755058"  # Your TRC20 USDT address
USDT_AMOUNT_REQUIRED = 30.0  # USD equivalent (you may adjust based on real-time price if needed)
MIN_CONFIRMATIONS = 1  # Wait for 1 confirmation on Tron

# TronGrid API (public, no key needed for basic usage)
TRONGRID_API = "https://api.trongrid.io"

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
ASKING_LOGIN, WAITING_PAYMENT = range(2)

# ================== DATABASE SETUP ==================
def init_db():
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            mt5_login TEXT,
            license_key TEXT,
            expiry DATETIME,
            payment_tx TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_payments (
            user_id INTEGER PRIMARY KEY,
            mt5_login TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ================== LICENSE & PAYMENT HELPERS ==================
def generate_license_key():
    return secrets.token_hex(16)  # 32-character hex string

def save_license(user_id, mt5_login, license_key, days=30):
    expiry = datetime.utcnow() + timedelta(days=days)
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (user_id, mt5_login, license_key, expiry, payment_tx)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, mt5_login, license_key, expiry.isoformat(), ''))
    conn.commit()
    conn.close()

def get_user_license(user_id):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('SELECT license_key, expiry FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row if row else (None, None)

def save_pending(user_id, mt5_login):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO pending_payments (user_id, mt5_login) VALUES (?, ?)', (user_id, mt5_login))
    conn.commit()
    conn.close()

def get_pending_login(user_id):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('SELECT mt5_login FROM pending_payments WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def clear_pending(user_id):
    conn = sqlite3.connect('licenses.db')
    c = conn.cursor()
    c.execute('DELETE FROM pending_payments WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# ================== TRON PAYMENT MONITOR ==================
def check_usdt_payments():
    """Check for new USDT-TRC20 payments to your address"""
    url = f"{TRONGRID_API}/v1/accounts/{USDT_RECEIVE_ADDRESS}/transactions/trc20"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        transactions = data.get('data', [])
        
        for tx in transactions:
            token_info = tx.get('tokenInfo', {})
            if token_info.get('symbol') != 'USDT':
                continue
            if token_info.get('tokenId') != 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':  # USDT-TRC20 contract
                continue

            value = int(tx['value'])  # USDT has 6 decimals
            usdt_amount = value / 1_000_000
            if usdt_amount < USDT_AMOUNT_REQUIRED:
                continue

            tx_hash = tx['transaction_id']
            sender = tx['from']
            timestamp = tx.get('block_timestamp', 0) / 1000  # ms to sec

            # Skip if already processed (you can add a 'processed_tx' table for robustness)
            conn = sqlite3.connect('licenses.db')
            c = conn.cursor()
            c.execute('SELECT 1 FROM users WHERE payment_tx = ?', (tx_hash,))
            if c.fetchone():
                conn.close()
                continue
            conn.close()

            logger.info(f"New payment: {usdt_amount} USDT from {sender}, tx: {tx_hash}")

            # Match sender to pending user (simple: assume 1 payment per user)
            # In production: use memo or unique address per user
            conn = sqlite3.connect('licenses.db')
            c = conn.cursor()
            c.execute('SELECT user_id, mt5_login FROM pending_payments LIMIT 1')  # Simplified
            pending = c.fetchone()
            conn.close()

            if pending:
                user_id, mt5_login = pending
                key = generate_license_key()
                save_license(user_id, mt5_login, key, days=30)

                # Update payment tx
                conn = sqlite3.connect('licenses.db')
                c = conn.cursor()
                c.execute('UPDATE users SET payment_tx = ? WHERE user_id = ?', (tx_hash, user_id))
                conn.commit()
                conn.close()

                clear_pending(user_id)

                # Send license key via Telegram
                try:
                    import asyncio
                    from telegram import Bot
                    bot = Bot(token=TELEGRAM_BOT_TOKEN)
                    asyncio.run(bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Payment confirmed!\n\nYour 30-day license key:\n<code>{key}</code>\n\n"
                             f"Enter this key in your MT5 EA to activate.",
                        parse_mode='HTML'
                    ))
                    logger.info(f"Sent license to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send Telegram message: {e}")
            else:
                logger.warning("Payment received but no pending user found!")

    except Exception as e:
        logger.error(f"Error checking payments: {e}")

# ================== TELEGRAM HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    license_key, expiry = get_user_license(user.id)
    if license_key and datetime.fromisoformat(expiry) > datetime.utcnow():
        await update.message.reply_text(
            f"✅ You already have an active license!\nKey: <code>{license_key}</code>\nExpires: {expiry[:10]}",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "Welcome! 🤖\n\n"
            "This bot provides license keys for the Pro Forex EA.\n"
            "✅ 5-day free trial included\n"
            "💰 Full access: $30/month (paid in USDT-TRC20)\n\n"
            "To get started, send /pay"
        )

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Please send exactly {USDT_AMOUNT_REQUIRED} USDT (TRC20) to:\n\n"
        f"<code>{USDT_RECEIVE_ADDRESS}</code>\n\n"
        "⚠️ Use TRC20 network only!\n\n"
        "After sending, reply with your **MT5 Account Login Number** (e.g., 12345678).",
        parse_mode='HTML'
    )
    return ASKING_LOGIN

async def receive_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    login = update.message.text.strip()

    if not login.isdigit() or len(login) < 6:
        await update.message.reply_text("❌ Invalid MT5 login. Please enter a valid number (e.g., 12345678).")
        return ASKING_LOGIN

    save_pending(user.id, login)
    await update.message.reply_text(
        f"✅ Got it! We're waiting for your payment of {USDT_AMOUNT_REQUIRED} USDT.\n\n"
        "We'll notify you here as soon as it's confirmed (usually <2 mins)."
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ================== MAIN ==================
def main():
    init_db()

    # Start payment monitor
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_usdt_payments, 'interval', minutes=2)
    scheduler.start()

    # Telegram bot
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('pay', pay)],
        states={
            ASKING_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_login)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)

    logger.info("Bot started. Listening for messages...")
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Bot stopped.")