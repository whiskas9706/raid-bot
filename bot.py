import json
import time
from pathlib import Path

import requests
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==========================
# НАСТРОЙКИ
# ==========================

import os

TOKEN = os.getenv("BOT_TOKEN")

USERS_FILE = "users.json"

# Защита от спама (15 минут)
RAID_COOLDOWN = 15 * 60

# ==========================
# БАЗА ПОЛЬЗОВАТЕЛЕЙ
# ==========================

def load_users():
    if Path(USERS_FILE).exists():
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)


users_db = load_users()

# ==========================
# КУЛДАУНЫ
# ==========================

last_raid = {}
last_defend = {}

# ==========================
# УЧАСТНИКИ РЕЙДА
# ==========================

raid_participants = {}

# ==========================
# СОХРАНЕНИЕ ПОЛЬЗОВАТЕЛЕЙ
# ==========================

async def save_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.effective_user
    chat_id = str(update.effective_chat.id)

    if chat_id not in users_db:
        users_db[chat_id] = {}

    users_db[chat_id][str(user.id)] = {
        "id": user.id,
        "name": user.first_name
    }

    save_users()


# ==========================
# УПОМИНАНИЯ
# ==========================

def get_mentions(chat_id):
    chat_id = str(chat_id)

    if chat_id not in users_db:
        return ""

    users = users_db[chat_id]

    mentions = []

    for user in users.values():
        mentions.append(
            f'<a href="tg://user?id={user["id"]}">{user["name"]}</a>'
        )

    return " ".join(mentions)


# ==========================
# ПРОВЕРКА КУЛДАУНА
# ==========================

def cooldown_ok(storage, chat_id):
    now = time.time()

    if chat_id not in storage:
        return True

    return now - storage[chat_id] >= RAID_COOLDOWN


# ==========================
# КНОПКИ
# ==========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    key = f"{query.message.chat_id}:{query.message.message_id}"

    if key not in raid_participants:
        raid_participants[key] = set()

    raid_participants[key].add(user.first_name)

    count = len(raid_participants[key])

    if query.data == "raid_join":
        button_text = f"✅ Иду ({count})"
        callback = "raid_join"

    else:
        button_text = f"🛡️ Помогаю ({count})"
        callback = "defend_join"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                button_text,
                callback_data=callback
            )
        ]
    ])

    await query.edit_message_reply_markup(
        reply_markup=keyboard
    )


# ==========================
# /РЕЙД
# ==========================

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id

    if not cooldown_ok(last_raid, chat_id):
        await update.message.reply_text(
            "⏳ Рейд уже объявлялся недавно."
        )
        return

    last_raid[chat_id] = time.time()

    mentions = get_mentions(chat_id)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Иду (0)",
                callback_data="raid_join"
            )
        ]
    ])

    text = (
        "⚔️ Идет сбор на рейд желающие в игру\n\n"
        f"{mentions}"
    )

    await update.message.reply_html(
        text,
        reply_markup=keyboard
    )


# ==========================
# /РЕЙДЯТ
# ==========================

async def raided(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat_id = update.effective_chat.id

    if not cooldown_ok(last_defend, chat_id):
        await update.message.reply_text(
            "⏳ Уведомление уже отправлялось недавно."
        )
        return

    last_defend[chat_id] = time.time()

    mentions = get_mentions(chat_id)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🛡️ Помогаю (0)",
                callback_data="defend_join"
            )
        ]
    ])

    text = (
        "🚨 Нас рейдят просьба зайти помочь\n\n"
        f"{mentions}"
    )

    await update.message.reply_html(
        text,
        reply_markup=keyboard
    )


# ==========================
# /МЕМАСИК
# ==========================

import os
import random
import requests

# Токен берём из окружения (в Render → Environment переменная VK_TOKEN),
# локально можно вписать в кавычки
VK_TOKEN = os.environ.get("VK_TOKEN", "")
VK_GROUP_ID = -29369324   # id паблика со знаком минус, как число
VK_VERSION = "5.199"


def vk_call(method, **params):
    """Единый запрос к VK API с понятной ошибкой."""
    params.update({
        "access_token": VK_TOKEN,
        "v": VK_VERSION,
    })
    response = requests.get(
        f"https://api.vk.com/method/{method}",
        params=params,
        timeout=10,
    )
    data = response.json()

    if "error" in data:
        raise Exception(
            f"VK {data['error']['error_code']}: {data['error']['error_msg']}"
        )
    return data["response"]


def get_meme_url():
    # Берём посты со стены сообщества и вытаскиваем из них фото
    posts = vk_call(
        "wall.get",
        owner_id=VK_GROUP_ID,
        count=100,
        filter="all",
    )["items"]

    photos = []

    for post in posts:
        attachments = post.get("attachments") or []
        for att in attachments:
            if att.get("type") == "photo":
                photos.append(att["photo"])

    if not photos:
        raise Exception("На стене сообщества нет ни одного фото")

    photo = random.choice(photos)
    best = max(photo["sizes"], key=lambda s: s["width"] * s["height"])
    return best["url"]


async def meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = get_meme_url()
        await update.message.reply_photo(
            photo=url,
            caption="😂 Случайный мем"
        )
    except Exception as e:
        await update.message.reply_text(
            f"Не удалось получить мем: {e} 😢"
        )
# ==========================
# /СТАРТ
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Привет!\n\n"
        "/raid - сбор на рейд\n"
        "/reidet - нужна помощь\n"
        "/memas - случайный мем"
    )


# ==========================
# ЗАПУСК
# ==========================

def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("raid", raid))
    app.add_handler(CommandHandler("reided", raided))
    app.add_handler(CommandHandler("memas", meme))

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            save_member
        )
    )

    port = int(os.environ.get("PORT", 8443))
    webhook_url = os.environ.get("WEBHOOK_URL", "")

    if webhook_url:
        print("Бот запущен (вебхук)!")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TOKEN,
            webhook_url=f"{webhook_url}/{TOKEN}",
        )
    else:
        print("Бот запущен (polling)!")
        app.run_polling()

if __name__ == "__main__":
    main()
