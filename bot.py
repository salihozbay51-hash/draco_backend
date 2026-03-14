import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv(
    "WEB_APP_URL",
    "https://dracobackend-production-6b8f.up.railway.app"
).rstrip("/")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = str(update.effective_user.id)

    referrer = None
    if context.args:
        referrer = context.args[0]

    payload = {
        "telegram_id": user_id,
        "referrer_id": referrer
    }

    requests.post(f"{API_URL}/users/register", json=payload)
    
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN / TELEGRAM_BOT_TOKEN env yok.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    print("Bot başladı.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
