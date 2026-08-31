import sqlite3
from datetime import datetime, timedelta

DB_PATH = "umbrella_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            tier TEXT DEFAULT 'free',
            expire_date TEXT,
            daily_usage INTEGER DEFAULT 0,
            last_usage_date TEXT
        )
    ''')
    # Avvalgi mavjud jadvalga yangi ustunlarni avtomatik qo'shish (Auto migration)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN daily_usage INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_usage_date TEXT")
    except Exception:
        pass

    conn.commit()
    conn.close()

def get_user(user_id: int, username: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, tier, expire_date, daily_usage, last_usage_date FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    today_str = datetime.now().strftime("%Y-%m-%d")

    if not row:
        cursor.execute("INSERT INTO users (user_id, username, tier, expire_date, daily_usage, last_usage_date) VALUES (?, ?, 'free', NULL, 0, ?)", (user_id, username, today_str))
        conn.commit()
        tier = 'free'
        expire_date = None
        daily_usage = 0
    else:
        tier = row[2]
        expire_date = row[3]
        daily_usage = row[4] or 0
        last_date = row[5]

        # Obuna muddati tugagan bo'lsa
        if expire_date:
            try:
                exp_dt = datetime.strptime(expire_date, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > exp_dt:
                    cursor.execute("UPDATE users SET tier = 'free', expire_date = NULL WHERE user_id = ?", (user_id,))
                    conn.commit()
                    tier = 'free'
                    expire_date = None
            except Exception:
                pass

        # Kun o'zgargan bo me'nosida kunlik ishlatish sonini 0 ga tushirish (Reset daily limit)
        if last_date != today_str:
            cursor.execute("UPDATE users SET daily_usage = 0, last_usage_date = ? WHERE user_id = ?", (today_str, user_id))
            conn.commit()
            daily_usage = 0

    conn.close()
    return {
        "user_id": user_id, 
        "tier": tier, 
        "expire_date": expire_date,
        "daily_usage": daily_usage
    }

def increment_daily_usage(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET daily_usage = daily_usage + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def set_user_tier(user_id: int, tier: str, days: int = 30):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if tier == 'free':
        cursor.execute("UPDATE users SET tier = 'free', expire_date = NULL WHERE user_id = ?", (user_id,))
    else:
        exp_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT OR REPLACE INTO users (user_id, tier, expire_date) VALUES (?, ?, ?)", (user_id, tier, exp_date))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, tier FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows
