import os
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

API_BASE = (
    os.getenv("BACKEND_URL")
    or os.getenv("API_BASE")
    or "https://dracobackend-production.up.railway.app"
).rstrip("/")

def create_order(telegram_id: str, dragon_code: str) -> dict:
    r = requests.post(
        f"{API_BASE}/shop/orders",
        json={"telegram_id": telegram_id, "dragon_code": dragon_code},
        timeout=25,
    )
    r.raise_for_status()
    return r.json()

def get_order(order_id: int) -> dict:
    r = requests.get(f"{API_BASE}/shop/orders/{order_id}", timeout=25)
    r.raise_for_status()
    return r.json()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton(
                text="🎮 Play Game",
                web_app=WebAppInfo(url="https://dracobackend-production.up.railway.app")
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🐉 *Draco Kingdom*\n\n"
        "Welcome Dragon Master.\n\n"
        "Oyuna başlamak için aşağıdaki butona bas."
    )

    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kullanım: /buy <dragon_code>\nÖrnek: /buy CIRAK")
        return

    dragon_code = context.args[0].strip().upper()
    telegram_id = str(update.effective_user.id)

    try:
        order = create_order(telegram_id=telegram_id, dragon_code=dragon_code)
    except Exception as e:
        await update.message.reply_text(f"❌ Sipariş oluşturulamadı.\nHata: {e}")
        return

    order_id = order.get("id") or order.get("order_id")
    amount = order.get("expected_amount_usdt") or order.get("expected_amount")
    pay_to = order.get("pay_to") or ""
    expires_at = order.get("expires_at", "")

    text = (
        "✅ *Sipariş oluşturuldu!*\n\n"
        f"🧾 Order ID: *{order_id}*\n"
        f"🐲 Dragon: *{dragon_code}*\n\n"
        f"💳 Ödeme: *{amount} USDT (TRC20)*\n"
        f"📬 Adres: `{pay_to}`\n"
        f"⏳ Son: {expires_at}\n\n"
        f"🔎 Durum kontrol: /status {order_id}\n\n"
        "⚠️ *Tam tutarı* gönder."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kullanım: /status <order_id>\nÖrnek: /status 12")
        return

    try:
        order_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Order ID sayı olmalı. Örnek: /status 12")
        return

    try:
        o = get_order(order_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Order bulunamadı veya hata.\nHata: {e}")
        return

    st = (o.get("status") or "").lower()
    amount = o.get("expected_amount_usdt")
    dragon_code = o.get("dragon_code")
    expires_at = o.get("expires_at")
    paid_txid = o.get("paid_txid")

    if st in ("paid", "completed"):
        msg = (
            "✅ *Ödeme onaylandı!*\n\n"
            f"🧾 Order: *{order_id}*\n"
            f"🐲 Dragon: *{dragon_code}*\n"
            f"💳 Tutar: *{amount} USDT*\n"
            f"🔗 TX: `{paid_txid}`"
        )
    elif st in ("expired", "canceled", "cancelled"):
        msg = (
            "⌛️ *Sipariş süresi dolmuş (expired).* \n\n"
            f"🧾 Order: *{order_id}*\n"
            "Tekrar satın almak için: /buy <dragon_code>"
        )
    else:
        msg = (
            "⏳ *Ödeme bekleniyor...*\n\n"
            f"🧾 Order: *{order_id}*\n"
            f"🐲 Dragon: *{dragon_code}*\n"
            f"💳 Tutar: *{amount} USDT*\n"
            f"⏳ Son: {expires_at}\n\n"
            f"Birkaç dakika sonra tekrar: /status {order_id}"
        )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

import time
from telegram.error import Conflict

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env yok. Önce BOT_TOKEN ayarla.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("status", status))

    print("Bot başladı.")

    while True:
        try:
            app.run_polling(drop_pending_updates=True, close_loop=False)
        except Conflict as e:
            print(f"[BOT] Conflict algılandı, 10 sn bekleniyor: {e}")
            time.sleep(10)
            continue
