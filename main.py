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

from db import init_db, get_conn
from models import DRAGONS, MINIK

app = FastAPI(title="Draco Backend")

@app.on_event("startup")
def _start_watcher():
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
    cur = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def _grant_minik_if_missing(conn, user_id: int):
    cur = conn.execute(
        "SELECT 1 FROM user_dragons WHERE user_id=? AND dragon_code=? LIMIT 1",
        (user_id, MINIK.code),
    )
    if cur.fetchone():
        return

    now = utcnow()
    expires = (now + timedelta(days=MINIK.lifetime_days)).isoformat()
    now_str = now.isoformat()

    conn.execute(
        """
        INSERT INTO user_dragons
        (user_id, dragon_code, eggs_per_day, started_at, expires_at, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (user_id, MINIK.code, MINIK.eggs_per_day, now_str, expires),
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
    # 2 hane yuvarlama: B1 unique cents mantığı
    amount_2 = round(amount_usdt + 1e-9, 2)

    now_iso = utcnow().isoformat()
    cur = conn.execute(
        """
        SELECT id, user_id, dragon_code, expected_amount, expires_at
        FROM purchase_orders
        WHERE status='awaiting_payment' AND expires_at > ?
        """,
        (now_iso,),
    )
    rows = cur.fetchall()
    for r in rows:
        expected = float(r["expected_amount"])
        if abs(expected - amount_2) < 0.0001:
            return dict(r)
    return None

def _process_tx_if_matches(conn, tx: dict) -> bool:
    txid = tx.get("transaction_id") or tx.get("transactionId") or tx.get("hash")
    if not txid:
        return False

    # daha önce işlendi mi?
    if conn.execute("SELECT 1 FROM processed_txs WHERE txid=?", (txid,)).fetchone():
        return False

    amount = _as_decimal_amount(tx)
    order = _match_order_by_amount(conn, amount)
    if not order:
        return False

    # --- atomik işlem (çifte işlenmeyi engellemek için) ---
    conn.execute("BEGIN IMMEDIATE")

    # tekrar kontrol (race condition için)
    if conn.execute("SELECT 1 FROM processed_txs WHERE txid=?", (txid,)).fetchone():
        conn.execute("ROLLBACK")
        return False

    # order hala awaiting mi?
    fresh = conn.execute(
        "SELECT status FROM purchase_orders WHERE id=?",
        (order["id"],),
    ).fetchone()
    if not fresh or fresh["status"] != "awaiting_payment":
        conn.execute("ROLLBACK")
        return False

    # ejderhayı ver
    _grant_dragon(conn, order["user_id"], order["dragon_code"])

    # order paid + tx kaydı
    conn.execute(
        "UPDATE purchase_orders SET status='paid', paid_txid=? WHERE id=?",
        (txid, order["id"]),
    )
    conn.execute(
        "INSERT INTO processed_txs (txid, processed_at) VALUES (?, ?)",
        (txid, utcnow().isoformat()),
    )

    conn.execute("COMMIT")
    return True

def _grant_dragon(conn, user_id: int, dragon_code: str):
    dragon_code = dragon_code.strip().upper()

    # eggs_per_day değerleri (500 AY = 1 USDT düzenine göre)
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

    # zaten aktif varsa tekrar verme (opsiyonel ama iyi)
    cur = conn.execute(
        "SELECT 1 FROM user_dragons WHERE user_id=? AND dragon_code=? AND is_active=1 LIMIT 1",
        (user_id, dragon_code),
    )
    if cur.fetchone():
        return

    now = utcnow()
    expires = (now + timedelta(days=90)).isoformat()
    now_str = now.isoformat()

    conn.execute(
        """
        INSERT INTO user_dragons
        (user_id, dragon_code, eggs_per_day, started_at, expires_at, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (user_id, dragon_code, EGGS_PER_DAY[dragon_code], now_str, expires),
    )    

# ===== DEBUG ENDPOINTS =====

@app.post("/debug/users/{telegram_id}/add-usdt")
def debug_add_usdt(telegram_id: str, amount_usdt: float = 10):
    telegram_id = telegram_id.strip()
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET usdt_balance = usdt_balance + ? WHERE telegram_id = ?",
            (float(amount_usdt), telegram_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        conn.commit()
        return {"ok": True, "telegram_id": telegram_id, "added_usdt": amount_usdt}
    finally:
        conn.close()

def _deactivate_expired_dragons(conn, user_id: int, now: datetime) -> int:
    """
    expires_at geçmiş olan ejderhaları pasifleştir (is_active=0).
    Return: kaç kayıt pasifleştirildi
    """
    cur = conn.execute("""
        UPDATE user_dragons
        SET is_active = 0
        WHERE user_id = ?
          AND is_active = 1
          AND expires_at IS NOT NULL
          AND expires_at <= ?
    """, (user_id, now.isoformat()))
    return cur.rowcount

def _get_active_dragons(conn, user_id: int):
    cur = conn.execute("""
        SELECT id, dragon_code, started_at, expires_at, is_active
        FROM user_dragons
        WHERE user_id = ? AND is_active = 1
        ORDER BY id ASC
    """, (user_id,))
    return [dict(r) for r in cur.fetchall()]

# --------- Schemas ---------
class RegisterRequest(BaseModel):
    telegram_id: str = Field(..., min_length=3, max_length=64)

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

# --------- Core production logic ---------
def compute_pending_eggs(dragons: list[dict], last_collect_at: datetime | None, now: datetime) -> int:
    """
    Her ejderha için:
    - üretim başlangıcı: max(last_collect_at, started_at)
    - üretim bitişi: min(now, expires_at)
    - süre (gün) * eggs_per_day
    """
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
        produced = int(days * dragon_type.eggs_per_day)
        if produced > 0:
            total += produced
    return total

# --------- Routes ---------
@app.get("/")
def root():
    return {"status": "Draco backend çalışıyor 🐉"}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/users/register", response_model=RegisterResponse)
def register_user(payload: RegisterRequest):
    telegram_id = payload.telegram_id.strip()
    if not telegram_id:
        raise HTTPException(status_code=400, detail="telegram_id boş olamaz")

    conn = get_conn()
    try:
        user = _get_user_by_telegram(conn, telegram_id)

        if user is None:
            conn.execute("INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,))
            conn.commit()
            user = _get_user_by_telegram(conn, telegram_id)

        _grant_minik_if_missing(conn, user["id"])
        conn.commit()

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
    conn = get_conn()
    try:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı. Önce /users/register çağır.")

        now = utcnow()
        _deactivate_expired_dragons(conn, user["id"], now)
        conn.commit()

        dragons = _get_active_dragons(conn, user["id"])

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
    finally:
        conn.close()

@app.post("/users/{telegram_id}/collect", response_model=CollectResponse)
def collect_eggs(telegram_id: str):
    telegram_id = telegram_id.strip()
    conn = get_conn()
    try:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı. Önce /users/register çağır.")

        now = utcnow()
        _deactivate_expired_dragons(conn, user["id"], now)
        conn.commit()

        dragons = _get_active_dragons(conn, user["id"])
        last_collect = parse_dt(user["last_collect_at"])
        stored = int(user["eggs_ay"] or 0)

        pending = compute_pending_eggs(dragons, last_collect, now)
        new_total = stored + pending

        conn.execute(
            "UPDATE users SET eggs_ay = ?, last_collect_at = ? WHERE id = ?",
            (new_total, now.isoformat(), user["id"])
        )
        conn.commit()

        return CollectResponse(
            telegram_id=user["telegram_id"],
            added_eggs_ay=pending,
            new_total_eggs_ay=new_total,
            collected_at=now.isoformat()
        )
    finally:
        conn.close()

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
    cur = conn.execute("""
        SELECT id, dragon_code, started_at, expires_at, is_active
        FROM user_dragons
        WHERE user_id = ?
        ORDER BY id ASC
    """, (user_id,))
    return [dict(r) for r in cur.fetchall()]

@app.get("/users/{telegram_id}/dragons", response_model=DragonsListResponse)
def list_user_dragons(telegram_id: str):
    telegram_id = telegram_id.strip()
    conn = get_conn()
    try:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        dragons = _get_all_dragons(conn, user["id"])
        return {
            "telegram_id": user["telegram_id"],
            "dragons": dragons
        }
    finally:
        conn.close()



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
    conn = get_conn()
    try:
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
            "UPDATE users SET eggs_ay = ?, usdt_balance = ? WHERE id = ?",
            (remaining, new_balance, user["id"])
        )
        conn.commit()

        return ConvertResponse(
            telegram_id=user["telegram_id"],
            converted_usdt=float(converted),
            remaining_eggs_ay=remaining,
            new_usdt_balance=new_balance
        )
    finally:
        conn.close()


# --------- DEBUG (TEST) ENDPOINT: YUMURTA EKLE ---------

class AddEggsRequest(BaseModel):
    amount: int = Field(..., ge=1, le=1000000)

@app.post("/debug/users/{telegram_id}/add-eggs")
def debug_add_eggs(telegram_id: str, payload: AddEggsRequest):
    telegram_id = telegram_id.strip()
    conn = get_conn()
    try:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        current = int(user["eggs_ay"] or 0)
        new_total = current + int(payload.amount)

        conn.execute(
            "UPDATE users SET eggs_ay = ? WHERE id = ?",
            (new_total, user["id"])
        )
        conn.commit()

        return {"telegram_id": user["telegram_id"], "new_eggs_ay": new_total}
    finally:
        conn.close()
 
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

    conn = get_conn()
    try:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        now = utcnow()
        _deactivate_expired_dragons(conn, user["id"], now) #

        # 1. Ejderhayı güvenli şekilde getir
        dragon = DRAGONS.get(dragon_code.lower())
        if dragon is None:
            raise HTTPException(status_code=404, detail="Ejderha bulunamadı")

        # 2. Fiyat ve Bakiye Kontrolü (Hatalı price_value kaldırıldı)
        price = float(dragon.price_usdt) # Doğrudan modelden alıyoruz
        usdt_balance = float(user.get("usdt_balance") or 0)

        if usdt_balance < price:
            raise HTTPException(status_code=400, detail=f"Yetersiz bakiye. Gerekli: {price} USDT")

        # 3. Tarih Hesaplamaları
        started = utcnow()
        expires = started + timedelta(days=dragon.lifetime_days)
        new_balance = usdt_balance - price

        # 4. Veritabanına Kayıt (Tüm sütunlar eksiksiz)
        conn.execute("""
            INSERT INTO user_dragons
            (user_id, dragon_code, eggs_per_day, purchased_usdt, started_at, expires_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (
            user["id"],
            dragon.code,          # models.py'den geliyor
            dragon.eggs_per_day,   # models.py'den geliyor (Kritik!)
            price,
            started.isoformat(),
            expires.isoformat()
        ))

        conn.execute("UPDATE users SET usdt_balance = ? WHERE id = ?", (new_balance, user["id"]))
        conn.commit()

        return BuyDragonResponse(
            telegram_id=user["telegram_id"],
            dragon_code=dragon.code,
            price_usdt=price,
            remaining_usdt_balance=new_balance,
            started_at=started.isoformat(),
            expires_at=expires.isoformat()
        )
    finally:
        conn.close()
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

            out_dragons.append(ProfileDragonItem(
                id=int(d["id"]),
                dragon_code=code,
                eggs_per_day=eggs_per_day,
                price_usdt=price_usdt,
                started_at=d["started_at"],
                expires_at=d["expires_at"],
                is_active=int(d["is_active"]),
                remaining_days=remaining_days,
                pending_eggs_ay=d_pending
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

    conn = get_conn()
    in_tx = False
    try:
        user = _get_user_by_telegram(conn, telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        # Aynı anda sadece 1 pending withdraw olsun
        cur = conn.execute(
            """
            SELECT 1
            FROM withdraw_requests
            WHERE user_id = ? AND status = 'pending'
            LIMIT 1
            """,
            (user["id"],),
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

        conn.execute("BEGIN")
        in_tx = True

        new_balance = balance - total_debit
        conn.execute(
            "UPDATE users SET usdt_balance = ? WHERE id = ?",
            (new_balance, user["id"]),
        )

        cur = conn.execute(
            """
            INSERT INTO withdraw_requests
              (user_id, telegram_id,
               amount_net_usdt, fee_usdt, amount_gross_usdt,
               address, status, note, created_at, updated_at)
            VALUES
              (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
            """,
            (
                user["id"],
                user["telegram_id"],
                amount_net,
                fee,
                total_debit,
                address,
                now,
                now,
            ),
        )

        withdraw_id = cur.lastrowid
        conn.commit()
        in_tx = False

        return WithdrawRequestResponse(
            telegram_id=user["telegram_id"],
            withdraw_id=int(withdraw_id),
            amount_usdt=amount_net,  # NET
            status="pending",
            remaining_usdt_balance=new_balance,
        )

    except HTTPException:
        # kontrollü hata: transaction başladıysa rollback
        if in_tx:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
        raise
    except Exception:
        if in_tx:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
        raise
    finally:
        conn.close()


class AdminActionBody(BaseModel):
    note: str | None = None

@app.get("/admin/withdraws")
def admin_list_withdraws(status: str = "pending", x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)

    conn = get_conn()
    try:
        cur = conn.execute(
            """
            SELECT id, telegram_id, amount_net_usdt, fee_usdt, amount_gross_usdt, address, status, created_at, updated_at, note
            FROM withdraw_requests
            WHERE status = ?
            ORDER BY id ASC
            """,
            (status,),
        )
        return {"items": [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()

@app.post("/admin/withdraw/{withdraw_id}/approve")
def admin_approve_withdraw(withdraw_id: int, body: AdminActionBody, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)

    conn = get_conn()
    try: 
        now = utcnow().isoformat()
        cur = conn.execute(
            "UPDATE withdraw_requests SET status='approved', note=?, updated_at=? WHERE id=? AND status='pending'",
            (body.note, now, withdraw_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=400, detail="Talep yok veya pending değil")
        return {"ok": True, "status": "approved"}
    finally:
        conn.close()

@app.post("/admin/withdraw/{withdraw_id}/paid")
def admin_mark_paid(withdraw_id: int, body: AdminActionBody, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)

    conn = get_conn()
    try:
        now = utcnow().isoformat()
        cur = conn.execute(
            "UPDATE withdraw_requests SET status='paid', note=?, updated_at=? WHERE id=? AND status='approved'",
            (body.note, now, withdraw_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=400, detail="Talep yok veya approved değil")
        return {"ok": True, "status": "paid"}
    finally:
        conn.close()

@app.post("/admin/withdraw/{withdraw_id}/reject")
def admin_reject_withdraw(
    withdraw_id: int,
    body: AdminActionBody,
    x_admin_token: str | None = Header(default=None),
):
    require_admin(x_admin_token)

    conn = get_conn()
    try:
        now = utcnow().isoformat()
        conn.execute("BEGIN")

        cur = conn.execute(
            "SELECT id, user_id, amount_gross_usdt, status FROM withdraw_requests WHERE id=?",
            (withdraw_id,),
        )
        w = cur.fetchone()

        if not w:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=404, detail="Talep bulunamadı")

        if w["status"] != "pending":
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=400, detail="Sadece pending reddedilebilir")

        conn.execute(
            "UPDATE withdraw_requests SET status='rejected', note=?, updated_at=? WHERE id=?",
            (body.note, now, withdraw_id),
        )

        conn.execute(
            "UPDATE users SET usdt_balance = usdt_balance + ? WHERE id=?",
            (float(w["amount_gross_usdt"]), int(w["user_id"])),
        )

        conn.commit()
        return {"ok": True, "status": "rejected"}

    finally:
        conn.close()



from fastapi import Body

@app.post("/admin/payments/confirm")
def admin_confirm_payment(
    order_id: int = Body(...),
    txid: str = Body(...),
    x_admin_token: str | None = Header(default=None),
):
    require_admin(x_admin_token)

    conn = get_conn()
    try:
        # tx daha önce işlendi mi?
        if conn.execute(
            "SELECT 1 FROM processed_txs WHERE txid = ?", (txid,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="Bu tx daha önce işlendi")

        order = conn.execute(
            """
            SELECT po.*, u.telegram_id
            FROM purchase_orders po
            JOIN users u ON u.id = po.user_id
            WHERE po.id = ? AND po.status = 'awaiting_payment'
            """,
            (order_id,),
        ).fetchone()

        if not order:
            raise HTTPException(status_code=404, detail="Sipariş bulunamadı veya aktif değil")

        # ejderhayı ver
        _grant_dragon(conn, order["user_id"], order["dragon_code"])

        # order + tx işaretle
        conn.execute(
            "UPDATE purchase_orders SET status='paid', paid_txid=? WHERE id=?",
            (txid, order_id),
        )
        conn.execute(
            "INSERT INTO processed_txs (txid, processed_at) VALUES (?, ?)",
            (txid, utcnow().isoformat()),
        )

        conn.commit()

        return {
            "status": "ok",
            "message": "Ödeme onaylandı, ejderha kullanıcıya verildi",
            "telegram_id": order["telegram_id"],
            "dragon": order["dragon_code"],
        }
    finally:
        conn.close()

@app.post("/shop/orders")
def create_shop_order(req: CreateOrderRequest):
    dragon_code = req.dragon_code.strip().upper()

    # Ejderha var mı?

    VALID_DRAGONS = {
    "MINIK",
    "CIRAK",
    "BRONZ",
    "GUMUS",
    "ALTIN",
    "EFSANE",
}

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

    conn = get_conn()
    try:
        user = _get_user_by_telegram(conn, req.telegram_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

        # 🔑 B1: benzersiz tutar
        unique_cents = randint(1, 99) / 100
        expected_amount = round(price_usdt + unique_cents, 2)

        expires_at = (utcnow() + timedelta(minutes=30)).isoformat()
        created_at = utcnow().isoformat()

        cur = conn.execute(
            """
            INSERT INTO purchase_orders
            (user_id, dragon_code, expected_amount, status, expires_at, created_at)
            VALUES (?, ?, ?, 'awaiting_payment', ?, ?)
            """,
            (user["id"], dragon_code, expected_amount, expires_at, created_at)
        )
        conn.commit()

        return {
            "order_id": cur.lastrowid,
            "pay_to": deposit_address,
            "expected_amount_usdt": expected_amount,
            "network": "TRON (TRC-20)",
            "expires_at": expires_at,
            "note": "Lütfen tutarı aynen gönderin (benzersiz tutar eşleştirme için)."
        }
    finally:
        conn.close()

# ===== WATCHER (TRC20 USDT) + ORDER TIMEOUT CLEANUP =====

_stop_watcher = threading.Event()

def _expire_old_orders(conn) -> int:
    """
    Süresi geçen awaiting_payment siparişleri expired yapar.
    Return: kaç sipariş expired oldu
    """
    now_iso = utcnow().isoformat()
    cur = conn.execute("""
        UPDATE purchase_orders
        SET status='expired'
        WHERE status='awaiting_payment'
          AND expires_at <= ?
    """, (now_iso,))
    return cur.rowcount

def _watcher_loop():
    interval = int(os.getenv("WATCHER_INTERVAL_SECONDS", "20") or "20")
    print(f"[WATCHER] Başladı. Interval: {interval} sn")

    deposit_address = os.getenv("TRON_DEPOSIT_ADDRESS", "").strip()
    if not deposit_address:
        print("[WATCHER] TRON_DEPOSIT_ADDRESS yok. Watcher durduruldu.")
        return

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
