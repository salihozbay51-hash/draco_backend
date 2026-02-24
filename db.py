import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def get_conn():
    return engine.connect()

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id TEXT UNIQUE NOT NULL,
            eggs_ay INTEGER DEFAULT 0,
            usdt_balance FLOAT DEFAULT 0,
            last_collect_at TEXT
        )
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_dragons (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            dragon_code TEXT NOT NULL,
            eggs_per_day INTEGER NOT NULL,
            purchased_usdt FLOAT DEFAULT 0,
            started_at TEXT,
            expires_at TEXT,
            is_active INTEGER DEFAULT 1,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0
        )
        """))
        
        # USER DRAGONS tablosunda level/xp yoksa ekle (migration gibi)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(user_dragons)").fetchall()]
        if "level" not in cols:
            conn.execute("ALTER TABLE user_dragons ADD COLUMN level INTEGER DEFAULT 1")
        if "xp" not in cols:
            conn.execute("ALTER TABLE user_dragons ADD COLUMN xp INTEGER DEFAULT 0")

           # PURCHASE ORDERS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            dragon_code TEXT NOT NULL,
            expected_amount REAL NOT NULL,
            status TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            paid_txid TEXT
        )
        """)

        # WITHDRAW REQUESTS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            telegram_id TEXT NOT NULL,
            amount_net_usdt REAL NOT NULL,
            fee_usdt REAL NOT NULL,
            amount_gross_usdt REAL NOT NULL,
            address TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # PROCESSED TXS (idempotency)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_txs (
            txid TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL
        )
        """)

        conn.commit()
    finally:
        conn.close()
