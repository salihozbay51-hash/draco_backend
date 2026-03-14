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
    keyboard = [
        [
            InlineKeyboardButton(
                text="🎮 Play Game",
                web_app=WebAppInfo(url=WEB_APP_URL)
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
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
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
