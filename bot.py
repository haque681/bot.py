import telebot
import sqlite3
import os

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 123456789  # এখানে তোর Telegram ID দে

bot = telebot.TeleBot(TOKEN)

# ===== DATABASE =====
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    ref_by INTEGER,
    points INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS withdraw (
    user_id INTEGER,
    amount INTEGER,
    status TEXT
)
""")
conn.commit()

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    args = message.text.split()

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()

    if not user:
        ref_by = None

        if len(args) > 1:
            ref_by = int(args[1])

        cursor.execute("INSERT INTO users (user_id, ref_by) VALUES (?,?)", (user_id, ref_by))
        conn.commit()

        # referral bonus
        if ref_by:
            cursor.execute("UPDATE users SET points = points + 10 WHERE user_id=?", (ref_by,))
            conn.commit()

    bot.send_message(user_id, f"""
👋 Welcome!

💰 Earn points by referring friends
🔗 Your link:
https://t.me/YourBot?start={user_id}

Commands:
/balance
/withdraw
""")

# ===== BALANCE =====
@bot.message_handler(commands=['balance'])
def balance(message):
    user_id = message.chat.id

    cursor.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    points = cursor.fetchone()[0]

    bot.send_message(user_id, f"💰 Your Points: {points}")

# ===== WITHDRAW =====
@bot.message_handler(commands=['withdraw'])
def withdraw(message):
    user_id = message.chat.id

    cursor.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    points = cursor.fetchone()[0]

    if points < 50:
        bot.send_message(user_id, "❌ Minimum 50 points needed")
        return

    cursor.execute("INSERT INTO withdraw (user_id, amount, status) VALUES (?,?,?)",
                   (user_id, points, "pending"))
    cursor.execute("UPDATE users SET points=0 WHERE user_id=?", (user_id,))
    conn.commit()

    bot.send_message(user_id, "✅ Withdraw request sent")

    bot.send_message(ADMIN_ID, f"""
📥 New Withdraw Request

User: {user_id}
Amount: {points}

Approve: /approve {user_id}
Reject: /reject {user_id}
""")

# ===== ADMIN APPROVE =====
@bot.message_handler(commands=['approve'])
def approve(message):
    if message.chat.id != ADMIN_ID:
        return

    user_id = int(message.text.split()[1])

    cursor.execute("UPDATE withdraw SET status='approved' WHERE user_id=?", (user_id,))
    conn.commit()

    bot.send_message(user_id, "✅ Withdraw Approved")

# ===== ADMIN REJECT =====
@bot.message_handler(commands=['reject'])
def reject(message):
    if message.chat.id != ADMIN_ID:
        return

    user_id = int(message.text.split()[1])

    cursor.execute("UPDATE withdraw SET status='rejected' WHERE user_id=?", (user_id,))
    conn.commit()

    bot.send_message(user_id, "❌ Withdraw Rejected")

# ===== RUN =====
bot.infinity_polling()
