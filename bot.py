import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv(
    "WEB_APP_URL",
    "https://dracofrontend-production.up.railway.app"
).rstrip("/")


import requests

API_URL = "https://dracobackend-production-6b8f.up.railway.app"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WELCOME_IMAGE = os.path.join(BASE_DIR, "assets", "welcome.png")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = str(update.effective_user.id)

    referrer = None
    if context.args:
        referrer = context.args[0]

    payload = {
        "telegram_id": user_id,
        "referrer_id": referrer
    }

    # kullanıcıyı register et
    try:
        requests.post(f"{API_URL}/users/register", json=payload)
    except:
        pass

    play_url = WEB_APP_URL
if referrer:
    play_url = f"{WEB_APP_URL}?ref={referrer}"

keyboard = [
    [
        InlineKeyboardButton(
            text="🎮 Play Game",
            web_app=WebAppInfo(url=play_url)
        )
    ]
]

    reply_markup = InlineKeyboardMarkup(keyboard)

    with open(WELCOME_IMAGE, "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption=(
                "🐉 *Draco Kingdom*\n\n"
                "Merhaba Dragon Master!\n\n"
                "Dragon satın al, altın yumurtalarını gerçek paraya dönüştür.\n"
                "Arkadaşlarını davet et, kazancını katla.\n\n"
                "👇 Oyuna başlamak için butona bas."
            ),
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN / TELEGRAM_BOT_TOKEN env yok.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    print("Bot başladı.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
