import logging
import json
import os
import requests

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ---------------- НАСТРОЙКИ ----------------

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
USE_AMVERA = os.environ.get("USE_AMVERA", "False") == "True"
AMVERA_API_KEY = os.environ.get("AMVERA_API_KEY") or OPENAI_API_KEY
AMVERA_MODEL = os.environ.get("AMVERA_MODEL", "gpt-5")

DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------- СОСТОЯНИЯ ----------------

(
    TYPE_PROJECT,
    MOOD,
    ACTION,
    NAME,
    TYPE,
    SKILLS,
    STATE,
    HIDDEN_Q,
    LENGTH,
    TONE,
    CTA,
    GENERATE,
) = range(12)

# ---------------- ХРАНЕНИЕ ----------------

def save_user_json(user_id: str, data: dict):
    path = os.path.join(DATA_DIR, f"{user_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_user_json(user_id: str):
    path = os.path.join(DATA_DIR, f"{user_id}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# ---------------- LLM ----------------

def amvera_chat(messages):
    url = "https://api.amvera.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AMVERA_API_KEY}"}
    data = {"model": AMVERA_MODEL, "messages": messages}
    r = requests.post(url, json=data, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def gpt_chat(messages):
    return amvera_chat(messages)

# ---------------- ДИАЛОГ ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет. Я помогу собрать актёрскую видеовизитку под конкретный проект.\n"
        "Это не резюме, а впечатление.\n\nНачнём.",
        reply_markup=ReplyKeyboardMarkup(
            [["Собрать визитку"]], one_time_keyboard=True
        ),
    )
    return TYPE_PROJECT

async def type_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)

    user_json = {
        "user_id": user_id,
        "project": {},
        "actor": {},
        "focus": {},
        "length": "",
        "tone": "",
        "cta": "",
        "drafts": [],
        "final": None,
    }
    save_user_json(user_id, user_json)

    await update.message.reply_text(
        "Выберите тип проекта:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["современная драма", "лёгкая драма", "комедия"],
                ["подростковый", "реклама", "историческая", "триллер"],
            ],
            one_time_keyboard=True,
        ),
    )
    return MOOD

async def mood_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["project"]["type"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text(
        "Выберите настроение:",
        reply_markup=ReplyKeyboardMarkup(
            [["спокойное", "лёгкое", "сдержанно-уверенное"]],
            one_time_keyboard=True,
        ),
    )
    return ACTION

async def action_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["project"]["mood"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text(
        "Выберите действие в кадре:",
        reply_markup=ReplyKeyboardMarkup(
            [["установить контакт", "удерживать внимание", "мягко вовлекать"]],
            one_time_keyboard=True,
        ),
    )
    return NAME

async def name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["project"]["action"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text("Введите ваше имя:")
    return TYPE

async def type_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["actor"]["name"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text("Введите ваш вуз (или напишите «пропустить»):")
    return SKILLS

async def skills_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    if update.message.text.lower() != "пропустить":
        user_json["actor"]["school"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text("Опишите один ключевой типаж:")
    return STATE

async def state_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["actor"]["type"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text("Укажите релевантные навыки (через запятую):")
    return HIDDEN_Q

async def hidden_question_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["actor"]["skills"] = [s.strip() for s in update.message.text.split(",")]
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text("Какое состояние хотите передать в кадре?")
    return LENGTH

async def length_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["focus"]["state"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text(
        "Выберите длительность:",
        reply_markup=ReplyKeyboardMarkup([["30s", "45s"]], one_time_keyboard=True),
    )
    return TONE

async def tone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["length"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text(
        "Выберите тон:",
        reply_markup=ReplyKeyboardMarkup(
            [["дружелюбный", "строгий", "лёгкая ирония"]],
            one_time_keyboard=True,
        ),
    )
    return CTA

async def cta_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json["tone"] = update.message.text
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text("Введите финальный CTA (или «пропустить»):")
    return GENERATE

async def generate_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_json = load_user_json(str(update.message.from_user.id))
    if update.message.text.lower() != "пропустить":
        user_json["cta"] = update.message.text

    system_prompt = f"""
Ты — эксперт по актёрским видеовизиткам 2026 года.
Создай 2 версии текста визитки под проект "{user_json['project']['type']}".

Правила:
- Не резюме. Не биография.
- Один типаж. Одно впечатление.
- Минимум слов, максимум присутствия.
- Длина: {user_json['length']}
- Тон: {user_json['tone']}
"""

    messages = [{"role": "system", "content": system_prompt}]
    drafts = gpt_chat(messages)

    user_json["drafts"] = drafts.split("\n\n")
    user_json["final"] = drafts
    save_user_json(user_json["user_id"], user_json)

    await update.message.reply_text(
        f"Готово.\n\n{drafts}"
    )
    return ConversationHandler.END

# ---------------- ДОП. HANDLERS ----------------

async def ignore_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Голосовые сообщения пока не поддерживаются.")

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите /start чтобы начать заново.")
    return TYPE_PROJECT

# ---------------- ЗАПУСК ----------------

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TYPE_PROJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_project)],
            MOOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, mood_step)],
            ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, action_step)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_step)],
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_step)],
            SKILLS: [MessageHandler(filters.TEXT & ~filters.COMMAND, skills_step)],
            STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_step)],
            HIDDEN_Q: [MessageHandler(filters.TEXT & ~filters.COMMAND, hidden_question_step)],
            LENGTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, length_step)],
            TONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tone_step)],
            CTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, cta_step)],
            GENERATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_step)],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)],
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.VOICE, ignore_voice))

    app.run_polling()

if __name__ == "__main__":
    main()
