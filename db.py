import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "draco.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    try:
        # USERS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE NOT NULL,
            eggs_ay INTEGER DEFAULT 0,
            usdt_balance REAL DEFAULT 0,
            last_collect_at TEXT
        )
        """)

        # USER DRAGONS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_dragons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            dragon_code TEXT NOT NULL,
            eggs_per_day INTEGER NOT NULL,
            purchased_usdt REAL DEFAULT 0,
            started_at TEXT,
            expires_at TEXT,
            is_active INTEGER DEFAULT 1
        )
        """)

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
