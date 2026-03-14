import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def get_conn():
    # main.py şu an conn.execute(...) kullandığı için connection döndürüyoruz
    return engine.connect()

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id TEXT UNIQUE NOT NULL,
                eggs_ay INTEGER DEFAULT 0,
                usdt_balance DOUBLE PRECISION DEFAULT 0,
                last_collect_at TEXT,
                referrer_id TEXT
            )
        """))

        conn.execute(text("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS referrer_id TEXT
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_dragons (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                dragon_code TEXT NOT NULL,
                eggs_per_day INTEGER NOT NULL,
                purchased_usdt DOUBLE PRECISION DEFAULT 0,
                started_at TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0
            )
        """))


        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                dragon_code TEXT NOT NULL,
                expected_amount DOUBLE PRECISION NOT NULL,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                paid_txid TEXT
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS withdraw_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                telegram_id TEXT NOT NULL,
                amount_net_usdt DOUBLE PRECISION NOT NULL,
                fee_usdt DOUBLE PRECISION NOT NULL,
                amount_gross_usdt DOUBLE PRECISION NOT NULL,
                address TEXT NOT NULL,
                status TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS processed_txs (
                txid TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            )
        """))
