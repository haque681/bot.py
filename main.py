import os
import re
import time
import logging
import aiosqlite
from datetime import datetime, timedelta, timezone
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, TypeHandler, ContextTypes, ApplicationHandlerStop,
    filters
)
from telegram.error import BadRequest

BOT_TOKEN = os.environ.get("8965583554:AAHyYwUxmOx1wGFoQ8DFob6RSGEv8rLHny0")
try:
    ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "8373846582").split(",") if x.strip()]
except:
    ADMIN_IDS = [8373846582]
DB_NAME = "bot_database.db"

# Settings keys
SETTING_GMAIL_PRICE = "gmail_price"
SETTING_REF_BONUS = "referral_bonus"
SETTING_MIN_WITHDRAW = "min_withdraw"
SETTING_MAX_WITHDRAW = "max_withdraw"
SETTING_DAILY_LIMIT = "daily_limit"
SETTING_START_MSG = "start_message"
SETTING_HELP_MSG = "help_message"
SETTING_BOT_NAME = "bot_name"
SETTING_CURRENCY_SYMBOL = "currency_symbol"
SETTING_MAINTENANCE_MODE = "maintenance_mode"
SETTING_ANTI_SPAM = "anti_spam"
SETTING_BONUS_AMOUNT = "bonus_amount"
SETTING_BONUS_COOLDOWN = "bonus_cooldown"
SETTING_RANK_ENABLED = "rank_enabled"
SETTING_FORCE_JOIN = "force_join"

DEFAULT_SETTINGS = {
    SETTING_GMAIL_PRICE: "5",
    SETTING_REF_BONUS: "2",
    SETTING_MIN_WITHDRAW: "200",
    SETTING_MAX_WITHDRAW: "0",
    SETTING_DAILY_LIMIT: "20",
    SETTING_START_MSG: "Welcome to Gmail Submit Bot!",
    SETTING_HELP_MSG: (
        "❓ Help Center\n\n"
        "📧 Send Gmail to earn balance\n"
        "💰 Withdraw when you reach minimum\n"
        "👥 Refer friends and earn bonus\n"
        "📊 Check your rank and leaderboard\n\n"
        "Admin commands:\n"
        "/admin - Open admin panel\n"
        "/set key value - Change any setting\n"
        "/user <id> - Manage user\n\n"
        "Support: @admin"
    ),
    SETTING_BOT_NAME: "Gmail Submit Bot",
    SETTING_CURRENCY_SYMBOL: "৳",
    SETTING_MAINTENANCE_MODE: "0",
    SETTING_ANTI_SPAM: "1",
    SETTING_BONUS_AMOUNT: "10",
    SETTING_BONUS_COOLDOWN: "24",
    SETTING_RANK_ENABLED: "1",
    SETTING_FORCE_JOIN: "0",
}

# Conversation states
GMAIL_INPUT = 1
GMAIL_PASSWORD = 2
WITHDRAW_AMOUNT = 3
WITHDRAW_METHOD_SELECT = 4   # new state for selecting method
WITHDRAW_ACCOUNT_DETAILS = 5 # new state for entering account details
PAYMENT_METHOD_INPUT = 6
ADMIN_TASK_DESC = 7
ADMIN_TASK_REQ = 8
ADMIN_TASK_REWARD = 9
ADMIN_BROADCAST_MSG = 10
ADMIN_CHANNEL_ID = 11
ADMIN_CHANNEL_URL = 12
ADMIN_EDIT_TASK_SELECT = 13
ADMIN_EDIT_TASK_DESC = 14
ADMIN_EDIT_TASK_REQ = 15
ADMIN_EDIT_TASK_REWARD = 16
ADMIN_EDIT_TASK_ACTIVE = 17
ADMIN_EDIT_SETTING = 18
ADMIN_ADD_PAYMENT_METHOD = 19   # for adding payment method name

user_last_message = {}
COOLDOWN_SECONDS = 1.0

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------- Database Setup --------------------
async def setup_database():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        # Create tables
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                balance REAL DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                total_gmail INTEGER DEFAULT 0,
                total_earn REAL DEFAULT 0,
                referrer_id INTEGER DEFAULT NULL,
                payment_method TEXT DEFAULT NULL,
                notification_on INTEGER DEFAULT 1,
                language TEXT DEFAULT 'en',
                is_banned INTEGER DEFAULT 0,
                last_bonus TIMESTAMP DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS gmail_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                email TEXT UNIQUE,
                password TEXT,
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS withdraw_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                method TEXT,                -- selected method (e.g., "Bkash")
                account_details TEXT,       -- user's account number/details
                status TEXT DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT,
                required_gmails INTEGER,
                reward REAL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bonus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS daily_tasks (
                user_id INTEGER,
                date TEXT,
                submitted_today INTEGER DEFAULT 0,
                claimed INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        # New table for payment methods
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Schema migration: add missing columns
        cursor = await db.execute("PRAGMA table_info(gmail_accounts)")
        columns = [row[1] for row in await cursor.fetchall()]
        if 'password' not in columns:
            await db.execute("ALTER TABLE gmail_accounts ADD COLUMN password TEXT")
            logger.info("Added missing 'password' column to gmail_accounts")

        cursor = await db.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in await cursor.fetchall()]
        required_user_cols = ['payment_method', 'notification_on', 'language', 'is_banned', 'last_bonus']
        for col in required_user_cols:
            if col not in columns:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT NULL")
                logger.info(f"Added missing column '{col}' to users")

        cursor = await db.execute("PRAGMA table_info(daily_tasks)")
        columns = [row[1] for row in await cursor.fetchall()]
        if 'claimed' not in columns:
            await db.execute("ALTER TABLE daily_tasks ADD COLUMN claimed INTEGER DEFAULT 0")
            logger.info("Added missing 'claimed' column to daily_tasks")

        # Add account_details column to withdraw_requests if missing
        cursor = await db.execute("PRAGMA table_info(withdraw_requests)")
        columns = [row[1] for row in await cursor.fetchall()]
        if 'account_details' not in columns:
            await db.execute("ALTER TABLE withdraw_requests ADD COLUMN account_details TEXT")
            logger.info("Added missing 'account_details' column to withdraw_requests")

        # Insert default settings
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))

        # Insert default task
        await db.execute('''
            INSERT OR IGNORE INTO tasks (id, description, required_gmails, reward, is_active)
            VALUES (1, 'Submit 5 Gmail', 5, 20, 1)
        ''')

        # Insert default payment methods if none exist
        async with db.execute("SELECT COUNT(*) FROM payment_methods") as cursor:
            count = (await cursor.fetchone())[0]
            if count == 0:
                for method in ["Bkash", "Nagad", "Rocket"]:
                    await db.execute("INSERT OR IGNORE INTO payment_methods (name) VALUES (?)", (method,))
                logger.info("Inserted default payment methods")

        await db.commit()
    logger.info("Database setup completed.")

# -------------------- Database Helpers --------------------
async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def create_user(user_id, name, referrer_id=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        await db.execute('INSERT OR IGNORE INTO users (user_id, name, referrer_id) VALUES (?, ?, ?)', (user_id, name, referrer_id))
        await db.commit()

async def update_user_balance(user_id, amount, is_earn=True):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        if is_earn:
            await db.execute('UPDATE users SET balance = balance + ?, total_earn = total_earn + ? WHERE user_id = ?', (amount, amount, user_id))
        else:
            await db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        await db.commit()

async def get_user_rank(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        async with db.execute('SELECT COUNT(*) + 1 as rank FROM users WHERE total_earn > (SELECT total_earn FROM users WHERE user_id = ?)', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 1

async def get_next_rank_info(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        async with db.execute('SELECT total_earn FROM users WHERE user_id = ?', (user_id,)) as cursor:
            user_row = await cursor.fetchone()
            if not user_row:
                return None, None
            current = user_row[0]
        async with db.execute('SELECT total_earn FROM users WHERE total_earn > ? ORDER BY total_earn ASC LIMIT 1', (current,)) as cursor:
            next_row = await cursor.fetchone()
            if not next_row:
                return None, None
            next_amount = next_row[0]
            async with db.execute('SELECT COUNT(*) + 1 FROM users WHERE total_earn > ?', (next_amount,)) as cursor:
                rank_row = await cursor.fetchone()
                next_rank = rank_row[0]
            return next_rank, next_amount - current

async def add_gmail(user_id, email, password):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        await db.execute('INSERT INTO gmail_accounts (user_id, email, password) VALUES (?, ?, ?)', (user_id, email, password))
        await db.commit()

async def get_user_gmails(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM gmail_accounts WHERE user_id = ? ORDER BY id DESC LIMIT 50', (user_id,)) as cursor:
            return await cursor.fetchall()

async def check_gmail_exists(email):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        async with db.execute('SELECT 1 FROM gmail_accounts WHERE email = ?', (email,)) as cursor:
            return await cursor.fetchone() is not None

async def get_pending_gmails():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM gmail_accounts WHERE status = "Pending" ORDER BY id') as cursor:
            return await cursor.fetchall()

async def get_gmail_by_id(gmail_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM gmail_accounts WHERE id = ?', (gmail_id,)) as cursor:
            return await cursor.fetchone()

async def update_gmail_status(gmail_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        await db.execute('UPDATE gmail_accounts SET status = ? WHERE id = ?', (status, gmail_id))
        await db.commit()

async def delete_gmail(gmail_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        await db.execute('DELETE FROM gmail_accounts WHERE id = ?', (gmail_id,))
        await db.commit()

async def get_pending_withdraws():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM withdraw_requests WHERE status = "Pending" ORDER BY id') as cursor:
            return await cursor.fetchall()

async def get_withdraw_by_id(wid):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM withdraw_requests WHERE id = ?', (wid,)) as cursor:
            return await cursor.fetchone()

async def update_withdraw_status(wid, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        await db.execute('UPDATE withdraw_requests SET status = ? WHERE id = ?', (status, wid))
        await db.commit()

async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        await db.commit()

async def add_history(user_id, action, details=""):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        await db.execute('INSERT INTO history (user_id, action, details) VALUES (?, ?, ?)', (user_id, action, details))
        await db.commit()

async def get_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT COUNT(*) as total_users FROM users') as c:
            total_users = (await c.fetchone())['total_users']
        async with db.execute('SELECT COUNT(*) as total_gmails FROM gmail_accounts') as c:
            total_gmails = (await c.fetchone())['total_gmails']
        async with db.execute("SELECT SUM(amount) as total_withdraw FROM withdraw_requests WHERE status='Approved'") as c:
            total_withdraw = (await c.fetchone())['total_withdraw'] or 0
        async with db.execute('SELECT SUM(total_earn) as total_earn FROM users') as c:
            total_earn = (await c.fetchone())['total_earn'] or 0
        today = datetime.now(timezone.utc).date().isoformat()
        async with db.execute('SELECT COUNT(*) as today_users FROM users WHERE DATE(created_at) = ?', (today,)) as c:
            today_users = (await c.fetchone())['today_users']
        async with db.execute('SELECT COUNT(*) as today_gmails FROM gmail_accounts WHERE DATE(created_at) = ?', (today,)) as c:
            today_gmails = (await c.fetchone())['today_gmails']
        return {"total_users": total_users, "today_users": today_users, "total_gmails": total_gmails, "today_gmails": today_gmails, "total_withdraw": total_withdraw, "total_earn": total_earn}

async def get_daily_task_status(user_id):
    today = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT submitted_today, claimed FROM daily_tasks WHERE user_id = ? AND date = ?', (user_id, today)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {"submitted_today": 0, "claimed": 0}

async def increment_daily_submission(user_id):
    today = datetime.now(timezone.utc).date().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        await db.execute('INSERT INTO daily_tasks (user_id, date, submitted_today, claimed) VALUES (?, ?, 1, 0) ON CONFLICT(user_id, date) DO UPDATE SET submitted_today = submitted_today + 1', (user_id, today))
        await db.commit()

async def claim_daily_reward(user_id):
    today = datetime.now(timezone.utc).date().isoformat()
    tasks = await get_all_tasks()
    active_task = next((t for t in tasks if t['is_active']), None)
    if not active_task:
        return False
    required = active_task['required_gmails']
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        async with db.execute('SELECT submitted_today, claimed FROM daily_tasks WHERE user_id = ? AND date = ?', (user_id, today)) as cursor:
            row = await cursor.fetchone()
            if not row or row[1] == 1 or row[0] < required:
                return False
        await db.execute('UPDATE daily_tasks SET claimed = 1 WHERE user_id = ? AND date = ?', (user_id, today))
        await db.commit()
    return True

async def get_all_tasks():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM tasks ORDER BY id') as cursor:
            return await cursor.fetchall()

async def get_task_by_id(task_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('PRAGMA journal_mode=WAL;')
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)) as cursor:
            return await cursor.fetchone()

async def add_task(description, required, reward):
    async with aiosqlite.connect(DB_NAME) as db:
        await 
