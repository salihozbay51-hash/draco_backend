from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
load_dotenv()
import hashlib # <--- Buranın olduğundan ve kaydedildiğinden emin ol
import threading
import time
import requests

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from random import randint
from db import init_db
from sqlalchemy import text
from db import engine  # db.py içinde engine var
from fastapi.middleware.cors import CORSMiddleware

# .evn isimli bir dosya kullanıyorsan ismini buraya yazmalısın
# Eğer dosya adını .env yaptıysan parantez içini boş bırakabilirsin: load_dotenv()
load_dotenv() 

def _get_env_float(name: str, default: float) -> float:
    v = os.getenv(name, "")
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default

# Değişkenleri burada bir kez tanımlıyoruz
MIN_WITHDRAW_USDT = _get_env_float("MIN_WITHDRAW_USDT", 5.0)
WITHDRAW_FEE_USDT = _get_env_float("WITHDRAW_FEE_USDT", 0.5)
ADMIN_TOKEN_HASH = os.getenv("ADMIN_TOKEN_HASH", "").strip()
USDT_CONTRACT = os.getenv(
    "USDT_CONTRACT",
    "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
).strip()

from db import get_conn, init_db
from models import DRAGONS, MINIK

app = FastAPI(title="Draco Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dracofrontend-production.up.railway.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

@app.get("/health")
def health():
    return {"ok": True}

@app.on_event("startup")
def _start_watcher():
    print("[DB] initializing...")
    init_db()
    print("[DB] ready")
    
    print("[WATCHER] startup event çalıştı")
    threading.Thread(target=_watcher_loop, daemon=True).start()

# --------- Helpers ---------
def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    # isoformat string bekliyoruz
    try:
        dt = datetime.fromisoformat(s)
        # timezone yoksa UTC varsay
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def require_admin(x_admin_token: str | None):
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="Admin token gerekli")

    if _hash_token(x_admin_token) != ADMIN_TOKEN_HASH:
        raise HTTPException(status_code=403, detail="Geçersiz admin token")

def _get_user_by_telegram(conn, telegram_id: str):
    cur = conn.execute(
        text("SELECT * FROM users WHERE telegram_id = :tg"),
        {"tg": telegram_id},
    )
    row = cur.mappings().fetchone()
    return dict(row) if row else None

def _get_user_by_id(conn, user_id: int):
    cur = conn.execute(
        text("SELECT * FROM users WHERE id = :uid"),
        {"uid": int(user_id)},
    )
    row = cur.mappings().fetchone()
    return dict(row) if row else None


def _dragon_price_by_code(dragon_code: str) -> float:
    dragon = DRAGONS.get(str(dragon_code).lower())
    if not dragon:
        return 0.0
    return float(getattr(dragon, "price_usdt", 0) or 0)


def _pay_referral_bonus(conn, buyer_user_id: int, purchase_usdt: float):
    """
    3 seviyeli referral:
    level 1 -> %8
    level 2 -> %3
    level 3 -> %1

    Ödül AY olarak verilir.
    500 AY = 1 USDT
    """
    buyer = _get_user_by_id(conn, buyer_user_id)
    if not buyer:
        return []

    rates = [0.08, 0.03, 0.01]
    payouts = []
    visited_ids = {int(buyer_user_id)}

    current_ref_tg = buyer.get("referrer_id")

    for level, rate in enumerate(rates, start=1):
        if not current_ref_tg:
            break

        ref_user = _get_user_by_telegram(conn, str(current_ref_tg))
        if not ref_user:
            break

        ref_user_id = int(ref_user["id"])
        if ref_user_id in visited_ids:
            break

        visited_ids.add(ref_user_id)

        reward_ay = int(round(float(purchase_usdt) * rate * EGG_TO_USDT_RATE))
        if reward_ay > 0:
            conn.execute(
                text("""
                    UPDATE users
                    SET eggs_ay = eggs_ay + :reward
                    WHERE id = :uid
                """),
                {"reward": reward_ay, "uid": ref_user_id},
            )

            payouts.append({
                "level": level,
                "telegram_id": ref_user["telegram_id"],
                "reward_ay": reward_ay,
            })

        current_ref_tg = ref_user.get("referrer_id")

    return payouts

def _grant_minik_if_missing(conn, user_id: int):
    cur = conn.execute(
        text("SELECT 1 FROM user_dragons WHERE user_id = :uid AND dragon_code = :code LIMIT 1"),
        {"uid": user_id, "code": MINIK.code},
    )
    if cur.fetchone():
        return

    now = utcnow()
    expires = (now + timedelta(days=MINIK.lifetime_days)).isoformat()
    now_str = now.isoformat()

    conn.execute(
        text("""
            INSERT INTO user_dragons
              (user_id, dragon_code, eggs_per_day, started_at, expires_at, is_active, level, xp)
            VALUES
              (:uid, :code, :epd, :started, :expires, 1, 1, 0)
        """),
        {
            "uid": user_id,
            "code": MINIK.code,
            "epd": MINIK.eggs_per_day,
            "started": now_str,
            "expires": expires,
        },
    )
    
def _fetch_incoming_usdt_trc20(deposit_address: str, limit: int = 50) -> list[dict]:
    base = os.getenv("TRONGRID_BASE", "https://api.trongrid.io").strip().rstrip("/")
    url = f"{base}/v1/accounts/{deposit_address}/transactions/trc20"

    params = {
        "limit": limit,
        "only_to": "true",
        "only_confirmed": "true",
        "contract_address": USDT_CONTRACT,
    }

    api_key = os.getenv("TRONGRID_API_KEY", "").strip()
    headers = {"TRON-PRO-API-KEY": api_key} if api_key else {}

    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()

    payload = r.json()
    return payload.get("data", []) or []

def _as_decimal_amount(tx: dict) -> float:
    # TronGrid çoğu zaman value'yu string olarak döner; decimals genelde 6 (USDT)
    value_str = tx.get("value", "0")
    token_info = tx.get("token_info") or {}
    decimals = int(token_info.get("decimals", 6))
    try:
        return int(value_str) / (10 ** decimals)
    except Exception:
        # bazı durumlarda value zaten "30.95" gibi gelebilir
        try:
            return float(value_str)
        except Exception:
            return 0.0

def _match_order_by_amount(conn, amount_usdt: float) -> dict | None:
    amount_2 = round(amount_usdt + 1e-9, 2)
    now_iso = utcnow().isoformat()

    cur = conn.execute(
        text("""
            SELECT id, user_id, dragon_code, expected_amount, expires_at
            FROM purchase_orders
            WHERE status = 'awaiting_payment'
              AND expires_at > :now
              AND expected_amount = :amt
            ORDER BY id ASC
            LIMIT 1
        """),
        {"now": now_iso, "amt": float(amount_2)},
    )
    row = cur.mappings().fetchone()
    return dict(row) if row else None

def _process_tx_if_matches(tx: dict) -> bool:
    txid = tx.get("transaction_id") or tx.get("transactionId") or tx.get("hash")
    if not txid:
        return False

    amount = _as_decimal_amount(tx)
    amount_2 = float(round(float(amount) + 1e-9, 2))
    now_iso = utcnow().isoformat()

    # Tek atomik transaction
    with engine.begin() as conn:
        # 1) txid'yi processed_txs'e "claim" et (idempotency)
        # txid zaten varsa rowcount=0 olur -> daha önce işlenmiş
        ins = conn.execute(
            text("""
                INSERT INTO processed_txs (txid, processed_at)
                VALUES (:txid, :ts)
                ON CONFLICT (txid) DO NOTHING
            """),
            {"txid": txid, "ts": now_iso},
        )
        if ins.rowcount == 0:
            return False

        # 2) Order'ı atomik olarak "paid" yap (awaiting + expire kontrol + amount match)
        cur = conn.execute(
            text("""
                UPDATE purchase_orders
                SET status = 'paid', paid_txid = :txid
                WHERE id = (
                    SELECT id
                    FROM purchase_orders
                    WHERE status = 'awaiting_payment'
                      AND expires_at > :now
                      AND expected_amount = :amt
                    ORDER BY id ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, user_id, dragon_code
            """),
            {"txid": txid, "now": now_iso, "amt": amount_2},
        )
        order = cur.mappings().fetchone()
        if not order:
            # eşleşen order yok -> az önce inserted processed_txs kaydını geri al
            # (transaction içinde olduğumuz için raise ile rollback yapmak yerine delete edelim)
            conn.execute(
                text("DELETE FROM processed_txs WHERE txid = :txid"),
                {"txid": txid},
            )
            return False

        # 3) Ejderhayı ver
        _grant_dragon(conn, int(order["user_id"]), str(order["dragon_code"]))
        purchase_usdt = _dragon_price_by_code(str(order["dragon_code"]))
        if purchase_usdt > 0:
            _pay_referral_bonus(conn, int(order["user_id"]), purchase_usdt)

        return True

def _grant_dragon(conn, user_id: int, dragon_code: str):
    dragon_code = dragon_code.strip().upper()

    EGGS_PER_DAY = {
        "MINIK": 2,
        "CIRAK": 170,
        "BRONZ": 335,
        "GUMUS": 500,
        "ALTIN": 725,
        "EFSANE": 1170,
    }

    if dragon_code not in EGGS_PER_DAY:
        raise HTTPException(status_code=400, detail="Geçersiz ejderha")

    # zaten aktif varsa tekrar verme
    cur = conn.execute(
        text("""
            SELECT 1
            FROM user_dragons
            WHERE user_id = :uid AND dragon_code = :code AND is_active = 1
            LIMIT 1
        """),
        {"uid": int(user_id), "code": dragon_code},
    )
    if cur.fetchone():
        return

    now = utcnow()
    expires = (now + timedelta(days=90)).isoformat()
    now_str = now.isoformat()

    conn.execute(
        text("""
            INSERT INTO user_dragons
                (user_id, dragon_code, eggs_per_day, started_at, expires_at, is_active, level, xp)
            VALUES
                (:uid, :code, :epd, :started, :expires, 1, 1, 0)
        """),
        {
            "uid": int(user_id),
            "code": dragon_code,
            "epd": int(EGGS_PER_DAY[dragon_code]),
            "started": now_str,
            "expires": expires,
        },
    )    
def production_multiplier(level: int) -> float:
    """
    Level 1 = bonus yok
    Her level için +%5 üretim
    """
    level = int(level or 1)
    if level < 1:
        level = 1
    return 1.0 + (level - 1) * 0.05


def upgrade_cost_eggs(level: int) -> int:
    """
    Upgrade maliyeti: 50 * level
    """
    level = int(level or 1)
    if level < 1:
        level = 1
    return 50 * level

def xp_gain_from_collect(eggs: int) -> int:
    return int(eggs * 0.10)

def xp_needed_for_level(level: int) -> int:
    level = int(level or 1)
    return 100 * level

def _dragon_pending(d: dict, last_collect_at, now) -> int:
    code = d["dragon_code"]
    dragon_type = DRAGONS.get(code)
    if not dragon_type:
        return 0

    started = parse_dt(d["started_at"]) or now
    expires = parse_dt(d["expires_at"]) or now

    start = started
    if last_collect_at and last_collect_at > start:
        start = last_collect_at

    end = now if now < expires else expires
    if end <= start:
        return 0

    seconds = (end - start).total_seconds()
    days = seconds / 86400.0
    return int(days * dragon_type.eggs_per_day)

def distribute_xp(total_xp: int, per_dragon_pending: list[tuple[int, int]]) -> dict[int, int]:
    total_pending = sum(p for _, p in per_dragon_pending)
    if total_pending <= 0 or total_xp <= 0:
        return {dragon_id: 0 for dragon_id, _ in per_dragon_pending}

    xp_map = {}
    used = 0

    for dragon_id, pending in per_dragon_pending:
        share = int(total_xp * (pending / total_pending))
        xp_map[dragon_id] = share
        used += share

    # rounding farkını en çok üretene ver
    remaining = total_xp - used
    if remaining > 0:
        per_dragon_pending.sort(key=lambda x: x[1], reverse=True)
        i = 0
        while remaining > 0:
            did = per_dragon_pending[i % len(per_dragon_pending)][0]
            xp_map[did] += 1
            remaining -= 1
            i += 1

    return xp_map

# ===== DEBUG ENDPOINTS =====

@app.post("/debug/users/{telegram_id}/add-usdt")
def debug_add_usdt(telegram_id: str, amount_usdt: float = 10):
    telegram_id = telegram_id.strip()

    with engine.begin() as conn:
        cur = conn.execute(
            text("""
                UPDATE users
                SET usdt_balance = usdt_balance + :amount
                WHERE telegram_id = :tg
            """),
            {"amount": float(amount_usdt), "tg": telegram_id},
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        return {"ok": True, "telegram_id": telegram_id, "added_usdt": amount_usdt}


@app.post("/debug/users/{telegram_id}/rewind_collect")
def debug_rewind_collect(telegram_id: str, hours: int = 24):
    if not DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    telegram_id = telegram_id.strip()

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        now = utcnow()
        new_last = (now - timedelta(hours=int(hours))).isoformat()

        conn.execute(
            text("""
                UPDATE users
                SET last_collect_at = :last_collect
                WHERE id = :uid
            """),
            {"last_collect": new_last, "uid": int(user["id"])},
        )

        return {
            "ok": True,
            "telegram_id": telegram_id,
            "hours_rewound": int(hours),
            "last_collect_at": new_last,
        }

def _deactivate_expired_dragons(conn, user_id: int, now: datetime) -> int:
    cur = conn.execute(text("""
        UPDATE user_dragons
        SET is_active = 0
        WHERE user_id = :uid
          AND is_active = 1
          AND expires_at IS NOT NULL
          AND expires_at <= :now
    """), {"uid": user_id, "now": now.isoformat()})
    return cur.rowcount

def _get_active_dragons(conn, user_id: int):
    cur = conn.execute(text("""
        SELECT
            id,
            dragon_code,
            started_at,
            expires_at,
            is_active,
            level,
            xp
        FROM user_dragons
        WHERE user_id = :uid AND is_active = 1
        ORDER BY id ASC
    """), {"uid": user_id})
    return [dict(r) for r in cur.mappings().all()]

# --------- Schemas ---------
class RegisterRequest(BaseModel):
    telegram_id: str
    referrer_id: str | None = None

class RegisterResponse(BaseModel):
    user_id: int
    telegram_id: str
    dragons: list[dict]

class EggsStatusResponse(BaseModel):
    telegram_id: str
    stored_eggs_ay: int
    pending_eggs_ay: int
    total_eggs_ay: int
    last_collect_at: str | None
    active_dragons: list[dict]

class CollectResponse(BaseModel):
    telegram_id: str
    added_eggs_ay: int
    new_total_eggs_ay: int
    collected_at: str


class UpgradeResponse(BaseModel):
    telegram_id: str
    dragon_id: int
    old_level: int
    new_level: int
    cost_eggs: int
    remaining_eggs_ay:int


# --------- Core production logic ---------
def production_multiplier(level: int) -> float:
    """
    Level 1 = bonus yok.
    Level 2 = +%5, Level 3 = +%10 ...
    """
    level = int(level or 1)
    if level < 1:
        level = 1
    return 1.0 + (level - 1) * 0.05

def compute_pending_eggs(dragons: list[dict], last_collect_at: datetime | None, now: datetime) -> int:
    total = 0
    for d in dragons:
        code = d["dragon_code"]
        dragon_type = DRAGONS.get(code)
        if not dragon_type:
            continue

        started = parse_dt(d["started_at"]) or now
        expires = parse_dt(d["expires_at"]) or now

        start = started
        if last_collect_at and last_collect_at > start:
            start = last_collect_at

        end = now if now < expires else expires

        if end <= start:
            continue

        seconds = (end - start).total_seconds()
        days = seconds / 86400.0

        level = int(d.get("level") or 1)
        mult = production_multiplier(level)

        produced = int(days * int(dragon_type.eggs_per_day) * mult)

        if produced > 0:
            total += produced

    return total

# --------- Routes ---------
@app.get("/")
def root():
    return {"status": "Draco backend çalışıyor 🐉"}

@app.post("/users/register", response_model=RegisterResponse)
def register_user(payload: RegisterRequest):

    telegram_id = payload.telegram_id.strip()
    referrer = payload.referrer_id

    conn = get_conn()

    try:
        user = _get_user_by_telegram(conn, telegram_id)

        if user is None:

            conn.execute(
                text("""
                    INSERT INTO users
                    (telegram_id, eggs_ay, usdt_balance, last_collect_at, referrer_id)
                    VALUES
                    (:tg, 0, 0, NULL, :ref)
                """),
                {
                    "tg": telegram_id,
                    "ref": referrer
                }
            )

            conn.commit()

        user = _get_user_by_telegram(conn, telegram_id)

        dragons = _get_active_dragons(conn, user["id"])

        return RegisterResponse(
            user_id=user["id"],
            telegram_id=user["telegram_id"],
            dragons=dragons
        )

    finally:
        conn.close()

@app.get("/users/{telegram_id}/eggs", response_model=EggsStatusResponse)
def eggs_status(telegram_id: str):
    telegram_id = telegram_id.strip()

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı. Önce /users/register çağır.")

        now = utcnow()
        _deactivate_expired_dragons(conn, int(user["id"]), now)

        dragons = _get_active_dragons(conn, int(user["id"]))
        last_collect = parse_dt(user["last_collect_at"])
        stored = int(user["eggs_ay"] or 0)
        pending = compute_pending_eggs(dragons, last_collect, now)

        return EggsStatusResponse(
            telegram_id=user["telegram_id"],
            stored_eggs_ay=stored,
            pending_eggs_ay=pending,
            total_eggs_ay=stored + pending,
            last_collect_at=user["last_collect_at"],
            active_dragons=dragons
        )
    
@app.post("/users/{telegram_id}/collect", response_model=CollectResponse)
def collect_eggs(telegram_id: str):
    telegram_id = telegram_id.strip()
    now = utcnow()

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı. Önce /users/register çağır.")

        user_id = int(user["id"])

        _deactivate_expired_dragons(conn, user_id, now)
        dragons = _get_active_dragons(conn, user_id)

        last_collect = parse_dt(user.get("last_collect_at"))
        stored = int(user.get("eggs_ay") or 0)

        pending = compute_pending_eggs(dragons, last_collect, now)
        new_total = stored + pending

        total_xp = xp_gain_from_collect(pending)

        per_dragon_pending: list[tuple[int, int]] = []
        for d in dragons:
            d_pending = _dragon_pending(d, last_collect, now)
            per_dragon_pending.append((int(d["id"]), int(d_pending)))

        xp_map = distribute_xp(total_xp, per_dragon_pending)

        # Dragon level/xp güncelle
        for d in dragons:
            did = int(d["id"])
            gain = int(xp_map.get(did, 0))

            current_level = int(d.get("level") or 1)
            current_xp = int(d.get("xp") or 0)
            new_xp = current_xp + gain

            while new_xp >= xp_needed_for_level(current_level):
                new_xp -= xp_needed_for_level(current_level)
                current_level += 1

            conn.execute(
                text("UPDATE user_dragons SET level = :lvl, xp = :xp WHERE id = :id"),
                {"lvl": current_level, "xp": new_xp, "id": did},
            )

        # Kullanıcı eggs + last_collect_at güncelle
        conn.execute(
            text("UPDATE users SET eggs_ay = :eggs, last_collect_at = :ts WHERE id = :id"),
            {"eggs": int(new_total), "ts": now.isoformat(), "id": user_id},
        )

        return CollectResponse(
            telegram_id=user["telegram_id"],
            added_eggs_ay=int(pending),
            new_total_eggs_ay=int(new_total),
            collected_at=now.isoformat(),
        )
    
class DragonItem(BaseModel):
    id: int
    dragon_code: str
    started_at: str
    expires_at: str
    is_active: int

class DragonsListResponse(BaseModel):
    telegram_id: str
    dragons: list[DragonItem]

def _get_all_dragons(conn, user_id: int):
    cur = conn.execute(
        text("""
            SELECT
                id,
                dragon_code,
                started_at,
                expires_at,
                is_active,
                level,
                xp
            FROM user_dragons
            WHERE user_id = :uid
            ORDER BY id ASC
        """),
        {"uid": int(user_id)},
    )
    return [dict(r) for r in cur.mappings().all()]

@app.get("/users/{telegram_id}/dragons", response_model=DragonsListResponse)
def list_user_dragons(telegram_id: str):
    telegram_id = telegram_id.strip()

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        dragons = _get_all_dragons(conn, int(user["id"]))
        return {
            "telegram_id": user["telegram_id"],
            "dragons": dragons
        }


@app.get("/shop/orders/{order_id}")
def get_order(order_id: int):
    with engine.begin() as conn:
        cur = conn.execute(
            text("""
                SELECT
                    id,
                    dragon_code,
                    expected_amount,
                    status,
                    expires_at,
                    paid_txid
                FROM purchase_orders
                WHERE id = :oid
            """),
            {"oid": int(order_id)},
        )
        row = cur.mappings().fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Order bulunamadı")

        return {
            "id": row["id"],
            "dragon_code": row["dragon_code"],
            "expected_amount_usdt": row["expected_amount"],
            "status": row["status"],
            "expires_at": row["expires_at"],
            "paid_txid": row["paid_txid"],
        }


   # --------- AY -> USDT CONVERT ---------

class ConvertResponse(BaseModel):
    telegram_id: str
    converted_usdt: float
    remaining_eggs_ay: int
    new_usdt_balance: float

EGG_TO_USDT_RATE = 500

@app.post("/users/{telegram_id}/convert", response_model=ConvertResponse)
def convert_eggs_to_usdt(telegram_id: str):
    telegram_id = telegram_id.strip()

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        eggs = int(user["eggs_ay"] or 0)
        usdt_balance = float(user["usdt_balance"] or 0)

        if eggs < EGG_TO_USDT_RATE:
            raise HTTPException(status_code=400, detail="Yeterli AY yok (min 500 AY)")

        converted = eggs // EGG_TO_USDT_RATE
        remaining = eggs % EGG_TO_USDT_RATE
        new_balance = usdt_balance + float(converted)

        conn.execute(
            text("""
                UPDATE users
                SET eggs_ay = :eggs, usdt_balance = :bal
                WHERE id = :uid
            """),
            {"eggs": int(remaining), "bal": float(new_balance), "uid": int(user["id"])},
        )

        return ConvertResponse(
            telegram_id=user["telegram_id"],
            converted_usdt=float(converted),
            remaining_eggs_ay=remaining,
            new_usdt_balance=new_balance
        )

# --------- DEBUG (TEST) ENDPOINT: YUMURTA EKLE ---------

class AddEggsRequest(BaseModel):
    amount: int = Field(..., ge=1, le=1000000)

@app.post("/debug/users/{telegram_id}/add-eggs")
def debug_add_eggs(telegram_id: str, payload: AddEggsRequest):
    telegram_id = telegram_id.strip()

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        current = int(user["eggs_ay"] or 0)
        new_total = current + int(payload.amount)

        conn.execute(
            text("""
                UPDATE users
                SET eggs_ay = :eggs
                WHERE id = :uid
            """),
            {"eggs": int(new_total), "uid": int(user["id"])},
        )

        return {"telegram_id": user["telegram_id"], "new_eggs_ay": new_total}

 
# --------- MARKET: EJDERHA SATIN AL ---------

class BuyDragonResponse(BaseModel):
    telegram_id: str
    dragon_code: str
    price_usdt: float
    remaining_usdt_balance: float
    started_at: str
    expires_at: str


@app.post("/users/{telegram_id}/buy/{dragon_code}", response_model=BuyDragonResponse)
def buy_dragon(telegram_id: str, dragon_code: str):
    telegram_id = telegram_id.strip()
    dragon_code = dragon_code.strip()

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        now = utcnow()
        _deactivate_expired_dragons(conn, int(user["id"]), now)

        dragon = DRAGONS.get(dragon_code.lower())
        if dragon is None:
            raise HTTPException(status_code=404, detail="Ejderha bulunamadı")

        price = float(dragon.price_usdt)
        usdt_balance = float(user.get("usdt_balance") or 0)

        if usdt_balance < price:
            raise HTTPException(status_code=400, detail=f"Yetersiz bakiye. Gerekli: {price} USDT")

        started = utcnow()
        expires = started + timedelta(days=dragon.lifetime_days)
        new_balance = usdt_balance - price

        conn.execute(
            text("""
                INSERT INTO user_dragons
                (user_id, dragon_code, eggs_per_day, purchased_usdt, started_at, expires_at, is_active, level, xp)
                VALUES (:uid, :code, :epd, :price, :started, :expires, 1, 1, 0)
            """),
            {
                "uid": int(user["id"]),
                "code": dragon.code,
                "epd": int(dragon.eggs_per_day),
                "price": float(price),
                "started": started.isoformat(),
                "expires": expires.isoformat(),
            }
        )

        conn.execute(
            text("""
                UPDATE users
                SET usdt_balance = :bal
                WHERE id = :uid
            """),
            {"bal": float(new_balance), "uid": int(user["id"])},
        )
        
        _pay_referral_bonus(conn, int(user["id"]), float(price))

        return BuyDragonResponse(
            telegram_id=user["telegram_id"],
            dragon_code=dragon.code,
            price_usdt=price,
            remaining_usdt_balance=new_balance,
            started_at=started.isoformat(),
            expires_at=expires.isoformat()
        )

# --------- PROFILE (Mini App için tek endpoint) ---------

class ProfileDragonItem(BaseModel):
    id: int
    dragon_code: str
    eggs_per_day: int
    price_usdt: float
    started_at: str
    expires_at: str
    is_active: int
    remaining_days: int
    pending_eggs_ay: int
    level: int
    xp: int

class ProfileResponse(BaseModel):
    telegram_id: str
    usdt_balance: float
    stored_eggs_ay: int
    pending_eggs_ay: int
    total_eggs_ay: int
    last_collect_at: str | None
    dragons: list[ProfileDragonItem]

def _safe_price_usdt(dragon_type):
    # models.py içinde Dragon(price_usdt, eggs_per_day, lifetime_days) kullanıyorsun
    # yine de garanti olsun diye fallback bıraktım
    return float(getattr(dragon_type, "price_usdt", 0) or 0)

def _dragon_pending(d_row: dict, last_collect_at: datetime | None, now: datetime) -> int:
    """
    Tek ejderha için pending hesaplar
    """
    code = d_row["dragon_code"]
    dragon_type = DRAGONS.get(code)
    if not dragon_type:
        return 0

    started = parse_dt(d_row["started_at"]) or now
    expires = parse_dt(d_row["expires_at"]) or now

    start = started
    if last_collect_at and last_collect_at > start:
        start = last_collect_at

    end = now if now < expires else expires
    if end <= start:
        return 0

    seconds = (end - start).total_seconds()
    days = seconds / 86400.0
    produced = int(days * int(getattr(dragon_type, "eggs_per_day", 0) or 0))
    return max(0, produced)

@app.get("/users/{telegram_id}/profile", response_model=ProfileResponse)
def user_profile(telegram_id: str):
    telegram_id = telegram_id.strip()
    conn = get_conn()
    try:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı. Önce /users/register çağır.")

        now = utcnow()
        last_collect = parse_dt(user["last_collect_at"])

        stored = int(user["eggs_ay"] or 0)
        usdt_balance = float(user["usdt_balance"] or 0)

        # aktif ejderhalar
        dragons = _get_active_dragons(conn, user["id"])

        # toplam pending (senin mevcut fonksiyonun)
        pending_total = compute_pending_eggs(dragons, last_collect, now)

        out_dragons: list[ProfileDragonItem] = []
        for d in dragons:
            code = d["dragon_code"]
            dragon_type = DRAGONS.get(code)

            expires = parse_dt(d["expires_at"]) or now
            remaining_days = int(max(0, (expires - now).total_seconds() // 86400))

            eggs_per_day = int(getattr(dragon_type, "eggs_per_day", 0) or 0) if dragon_type else 0
            price_usdt = _safe_price_usdt(dragon_type) if dragon_type else 0.0

            d_pending = _dragon_pending(d, last_collect, now)

            out_dragons.append(
                ProfileDragonItem(
                    id=d["id"],
                    dragon_code=d["dragon_code"],
                    eggs_per_day=dragon_type.eggs_per_day,
                    price_usdt=dragon_type.price_usdt,
                    started_at=d["started_at"],
                    expires_at=d["expires_at"],
                    is_active=d["is_active"],
                    remaining_days=remaining_days,
                    pending_eggs_ay=d_pending,
                    level=int(d.get("level") or 1),
                    xp=int(d.get("xp") or 0),
            ))
            
        return ProfileResponse(
            telegram_id=user["telegram_id"],
            usdt_balance=usdt_balance,
            stored_eggs_ay=stored,
            pending_eggs_ay=pending_total,
            total_eggs_ay=stored + pending_total,
            last_collect_at=user["last_collect_at"],
            dragons=out_dragons
        )
    finally:
        conn.close()

# --------- MARKET LIST ---------

class MarketDragonItem(BaseModel):
    code: str
    price_usdt: float
    eggs_per_day: int
    lifetime_days: int
    is_starter_only: bool  # minik gibi markette satılmasın diye

class MarketListResponse(BaseModel):
    dragons: list[MarketDragonItem]

def _dragon_price(dragon_type) -> float:
    # models.py'de price_usdt ekledik; yine de güvenli olsun
    val = (
        getattr(dragon_type, "price_usdt", None)
        or getattr(dragon_type, "price", None)
        or getattr(dragon_type, "cost_usdt", None)
        or getattr(dragon_type, "usdt", None)
        or 0
    )
    return float(val)

@app.get("/market/dragons", response_model=MarketListResponse, operation_id="market_list_dragons")
def market_list_dragons():
    items: list[MarketDragonItem] = []

    # DRAGONS: {code: Dragon}
    for code, d in DRAGONS.items():
        code_norm = str(getattr(d, "code", code)).lower()

        eggs_per_day = int(getattr(d, "eggs_per_day", 0) or 0)
        lifetime_days = int(getattr(d, "lifetime_days", 90) or 90)
        price_usdt = _dragon_price(d)

        # minik sadece starter olsun: fiyat 0 ise satılmasın
        is_starter_only = (code_norm == "minik") or (price_usdt <= 0)

        items.append(MarketDragonItem(
            code=code_norm,
            price_usdt=price_usdt,
            eggs_per_day=eggs_per_day,
            lifetime_days=lifetime_days,
            is_starter_only=is_starter_only
        ))

    # markette satılanları önce göster (starter_only en sona)
    items.sort(key=lambda x: (x.is_starter_only, x.price_usdt))

    return MarketListResponse(dragons=items)

# --------- WITHDRAW (V1: MANUEL) ---------

class WithdrawRequestBody(BaseModel):
    amount_usdt: float = Field(..., gt=0)
    address: str = Field(..., min_length=8, max_length=256)

class WithdrawRequestResponse(BaseModel):
    telegram_id: str
    withdraw_id: int
    amount_usdt: float
    status: str
    remaining_usdt_balance: float

class CreateOrderRequest(BaseModel):
    telegram_id: str
    dragon_code: str
    
@app.post("/users/{telegram_id}/withdraw/request", response_model=WithdrawRequestResponse)
def withdraw_request(telegram_id: str, body: WithdrawRequestBody):
    telegram_id = telegram_id.strip()
    amount_net = float(body.amount_usdt)
    address = body.address.strip()

    if amount_net < MIN_WITHDRAW_USDT:
        raise HTTPException(status_code=400, detail=f"Minimum çekim {MIN_WITHDRAW_USDT} USDT")

    fee = WITHDRAW_FEE_USDT
    total_debit = amount_net + fee

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        cur = conn.execute(
            text("""
                SELECT 1
                FROM withdraw_requests
                WHERE user_id = :uid AND status = 'pending'
                LIMIT 1
            """),
            {"uid": int(user["id"])},
        )
        if cur.fetchone() is not None:
            raise HTTPException(status_code=400, detail="Zaten beklemede olan bir çekim talebin var")

        balance = float(user.get("usdt_balance") or 0)
        if balance < total_debit:
            raise HTTPException(
                status_code=400,
                detail=f"Yetersiz bakiye. Net {amount_net} + fee {fee} = {total_debit} USDT gerekir",
            )

        now = utcnow().isoformat()
        new_balance = balance - total_debit

        conn.execute(
            text("""
                UPDATE users
                SET usdt_balance = :bal
                WHERE id = :uid
            """),
            {"bal": float(new_balance), "uid": int(user["id"])},
        )

        cur = conn.execute(
            text("""
                INSERT INTO withdraw_requests
                  (user_id, telegram_id,
                   amount_net_usdt, fee_usdt, amount_gross_usdt,
                   address, status, note, created_at, updated_at)
                VALUES
                  (:uid, :tg, :net, :fee, :gross, :addr, 'pending', NULL, :created, :updated)
                RETURNING id
            """),
            {
                "uid": int(user["id"]),
                "tg": user["telegram_id"],
                "net": float(amount_net),
                "fee": float(fee),
                "gross": float(total_debit),
                "addr": address,
                "created": now,
                "updated": now,
            },
        )

        withdraw_id = int(cur.mappings().fetchone()["id"])

        return WithdrawRequestResponse(
            telegram_id=user["telegram_id"],
            withdraw_id=withdraw_id,
            amount_usdt=amount_net,
            status="pending",
            remaining_usdt_balance=new_balance,
        )


class AdminActionBody(BaseModel):
    note: str | None = None

@app.get("/admin/withdraws")
def admin_list_withdraws(status: str = "pending", x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)

    with engine.begin() as conn:
        cur = conn.execute(
            text("""
                SELECT
                    id, telegram_id, amount_net_usdt, fee_usdt, amount_gross_usdt,
                    address, status, created_at, updated_at, note
                FROM withdraw_requests
                WHERE status = :status
                ORDER BY id ASC
            """),
            {"status": status},
        )
        return {"items": [dict(r) for r in cur.mappings().all()]}


@app.post("/admin/withdraw/{withdraw_id}/approve")
def admin_approve_withdraw(withdraw_id: int, body: AdminActionBody, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)

    with engine.begin() as conn:
        now = utcnow().isoformat()
        cur = conn.execute(
            text("""
                UPDATE withdraw_requests
                SET status = 'approved', note = :note, updated_at = :updated
                WHERE id = :wid AND status = 'pending'
            """),
            {"note": body.note, "updated": now, "wid": int(withdraw_id)},
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=400, detail="Talep yok veya pending değil")

        return {"ok": True, "status": "approved"}

@app.post("/admin/withdraw/{withdraw_id}/paid")
def admin_mark_paid(withdraw_id: int, body: AdminActionBody, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)

    with engine.begin() as conn:
        now = utcnow().isoformat()
        cur = conn.execute(
            text("""
                UPDATE withdraw_requests
                SET status = 'paid', note = :note, updated_at = :updated
                WHERE id = :wid AND status = 'approved'
            """),
            {"note": body.note, "updated": now, "wid": int(withdraw_id)},
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=400, detail="Talep yok veya approved değil")

        return {"ok": True, "status": "paid"}

@app.post("/admin/withdraw/{withdraw_id}/reject")
def admin_reject_withdraw(
    withdraw_id: int,
    body: AdminActionBody,
    x_admin_token: str | None = Header(default=None),
):
    require_admin(x_admin_token)

    with engine.begin() as conn:
        now = utcnow().isoformat()

        cur = conn.execute(
            text("""
                SELECT id, user_id, amount_gross_usdt, status
                FROM withdraw_requests
                WHERE id = :wid
            """),
            {"wid": int(withdraw_id)},
        )
        w = cur.mappings().fetchone()

        if not w:
            raise HTTPException(status_code=404, detail="Talep bulunamadı")

        if w["status"] != "pending":
            raise HTTPException(status_code=400, detail="Sadece pending reddedilebilir")

        conn.execute(
            text("""
                UPDATE withdraw_requests
                SET status = 'rejected', note = :note, updated_at = :updated
                WHERE id = :wid
            """),
            {"note": body.note, "updated": now, "wid": int(withdraw_id)},
        )

        conn.execute(
            text("""
                UPDATE users
                SET usdt_balance = usdt_balance + :amount
                WHERE id = :uid
            """),
            {"amount": float(w["amount_gross_usdt"]), "uid": int(w["user_id"])},
        )

        return {"ok": True, "status": "rejected"}


from fastapi import Body

@app.post("/admin/payments/confirm")
def admin_confirm_payment(
    order_id: int = Body(...),
    txid: str = Body(...),
    x_admin_token: str | None = Header(default=None),
):
    require_admin(x_admin_token)

    with engine.begin() as conn:
        cur = conn.execute(
            text("SELECT 1 FROM processed_txs WHERE txid = :txid"),
            {"txid": txid},
        )
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Bu tx daha önce işlendi")

        cur = conn.execute(
            text("""
                SELECT po.*, u.telegram_id
                FROM purchase_orders po
                JOIN users u ON u.id = po.user_id
                WHERE po.id = :oid AND po.status = 'awaiting_payment'
            """),
            {"oid": int(order_id)},
        )
        order = cur.mappings().fetchone()

        if not order:
            raise HTTPException(status_code=404, detail="Sipariş bulunamadı veya aktif değil")

        _grant_dragon(conn, int(order["user_id"]), str(order["dragon_code"]))

        purchase_usdt = _dragon_price_by_code(str(order["dragon_code"]))
        if purchase_usdt > 0:
            _pay_referral_bonus(conn, int(order["user_id"]), purchase_usdt)

        conn.execute(
            text("""
                UPDATE purchase_orders
                SET status = 'paid', paid_txid = :txid
                WHERE id = :oid
            """),
            {"txid": txid, "oid": int(order_id)},
        )

        conn.execute(
            text("""
                INSERT INTO processed_txs (txid, processed_at)
                VALUES (:txid, :processed_at)
            """),
            {"txid": txid, "processed_at": utcnow().isoformat()},
        )

        return {
            "status": "ok",
            "message": "Ödeme onaylandı, ejderha kullanıcıya verildi",
            "telegram_id": order["telegram_id"],
            "dragon": order["dragon_code"],
        }

@app.post("/shop/orders")
def create_shop_order(req: CreateOrderRequest):
    dragon_code = req.dragon_code.strip().upper()

    VALID_DRAGONS = {"MINIK", "CIRAK", "BRONZ", "GUMUS", "ALTIN", "EFSANE"}
    if dragon_code not in VALID_DRAGONS:
        raise HTTPException(status_code=400, detail="Geçersiz ejderha")

    DRAGON_PRICES = {
        "MINIK": 0,
        "CIRAK": 15,
        "BRONZ": 30,
        "GUMUS": 45,
        "ALTIN": 65,
        "EFSANE": 105,
    }
    price_usdt = DRAGON_PRICES[dragon_code]
    if price_usdt <= 0:
        raise HTTPException(status_code=400, detail="Bu ejderha satın alınamaz")

    deposit_address = os.getenv("TRON_DEPOSIT_ADDRESS", "").strip()
    if not deposit_address:
        raise HTTPException(status_code=500, detail="TRON_DEPOSIT_ADDRESS ayarlı değil")

    # Tek transaction
    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, req.telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        # Benzersiz tutar
        unique_cents = randint(1, 99) / 100
        expected_amount = round(price_usdt + unique_cents, 2)

        now = utcnow()
        expires_at = (now + timedelta(minutes=30)).isoformat()
        created_at = now.isoformat()

        cur = conn.execute(
            text("""
                INSERT INTO purchase_orders
                    (user_id, dragon_code, expected_amount, status, expires_at, created_at)
                VALUES
                    (:uid, :code, :amt, 'awaiting_payment', :exp, :created)
                RETURNING id
            """),
            {
                "uid": int(user["id"]),
                "code": dragon_code,
                "amt": float(expected_amount),
                "exp": expires_at,
                "created": created_at,
            },
        )
        order_id = int(cur.mappings().fetchone()["id"])

    return {
        "order_id": order_id,
        "pay_to": deposit_address,
        "expected_amount_usdt": expected_amount,
        "network": "TRON (TRC-20)",
        "expires_at": expires_at,
        "note": "Lütfen tutarı aynen gönderin (benzersiz tutar eşleştirme için).",
    }

# ===== WATCHER (TRC20 USDT) + ORDER TIMEOUT CLEANUP =====

_stop_watcher = threading.Event()

def _expire_old_orders(conn) -> int:
    now_iso = utcnow().isoformat()
    cur = conn.execute(
        text("""
            UPDATE purchase_orders
            SET status = 'expired'
            WHERE status = 'awaiting_payment'
              AND expires_at <= :now
        """),
        {"now": now_iso},
    )
    return cur.rowcount

def _watcher_loop():
    interval = int(os.getenv("WATCHER_INTERVAL_SECONDS", "20") or "20")
    print(f"[WATCHER] Başladı. Interval: {interval} sn")

    deposit_address = os.getenv("TRON_DEPOSIT_ADDRESS", "").strip()
    if not deposit_address:
        print("[WATCHER] TRON_DEPOSIT_ADDRESS yok. Watcher durduruldu.")
        return
    
        # --- DB hazır mı? (purchase_orders tablosu oluşana kadar bekle) ---
    import time
    while True:
        try:
            conn = get_conn()
            conn.execute("SELECT 1 FROM purchase_orders LIMIT 1")
            conn.close()
            print("[WATCHER] DB hazır, watcher devam ediyor ✅")
            break
        except Exception as e:
            print(f"[WATCHER] DB henüz hazır değil, 2 sn bekleniyor... ({e})")
            time.sleep(2)

    while not _stop_watcher.is_set():
        try:
            conn = get_conn()
            try:
                # 1) Önce süresi geçen order'ları temizle
                expired = _expire_old_orders(conn)
                if expired:
                    print(f"[WATCHER] {expired} sipariş süresi doldu (expired).")

                conn.commit()

                # 2) TronGrid'den transferleri çek
                txs = _fetch_incoming_usdt_trc20(deposit_address)

                # 3) Eşleşen ödemeleri işle
                matched = 0
                for tx in txs:
                    if _process_tx_if_matches(conn, tx):
                        matched += 1

                if matched:
                    print(f"[WATCHER] {matched} ödeme işlendi ✅")

                conn.commit()

            finally:
                conn.close()

        except Exception as e:
            print("[WATCHER] HATA:", e)

        time.sleep(interval)


@app.post("/users/{telegram_id}/dragons/{dragon_id}/upgrade", response_model=UpgradeResponse)
def upgrade_dragon(telegram_id: str, dragon_id: int):
    telegram_id = telegram_id.strip()

    with engine.begin() as conn:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        cur = conn.execute(
            text("""
                SELECT id, level
                FROM user_dragons
                WHERE id = :did AND user_id = :uid AND is_active = 1
            """),
            {"did": int(dragon_id), "uid": int(user["id"])},
        )
        d = cur.mappings().fetchone()

        if not d:
            raise HTTPException(status_code=404, detail="Ejderha bulunamadı")

        old_level = int(d["level"] or 1)
        cost = upgrade_cost_eggs(old_level)
        stored_eggs = int(user["eggs_ay"] or 0)

        if stored_eggs < cost:
            raise HTTPException(
                status_code=400,
                detail=f"Yetersiz yumurta. Gerekli: {cost}, Sende: {stored_eggs}"
            )

        new_level = old_level + 1
        new_eggs = stored_eggs - cost

        conn.execute(
            text("""
                UPDATE users
                SET eggs_ay = :eggs
                WHERE id = :uid
            """),
            {"eggs": int(new_eggs), "uid": int(user["id"])},
        )

        conn.execute(
            text("""
                UPDATE user_dragons
                SET level = :lvl
                WHERE id = :did
            """),
            {"lvl": int(new_level), "did": int(dragon_id)},
        )

        return UpgradeResponse(
            telegram_id=user["telegram_id"],
            dragon_id=int(dragon_id),
            old_level=old_level,
            new_level=new_level,
            cost_eggs=cost,
            remaining_eggs_ay=new_eggs
        )
