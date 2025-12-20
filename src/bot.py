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

# ---------- НАСТРОЙКИ ----------

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
AMVERA_API_KEY = os.environ.get("AMVERA_API_KEY")
AMVERA_MODEL = os.environ.get("AMVERA_MODEL", "gpt-5")

DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

# ---------- СОСТОЯНИЯ ----------

(
    TYPE_PROJECT,
    MOOD,
    ACTION,
    NAME,
    SCHOOL,
    TYPE,
    SKILLS,
    STATE,
    LENGTH,
    TONE,
    CTA,
    GENERATE,
) = range(12)

# ---------- CTA ПУЛЫ ----------

CTA_POOLS = {
    "современная драма": [
        "Открыт(а) к самопробам",
        "Буду рад(а) продолжить диалог по проекту",
        "Готов(а) к следующему этапу",
    ],
    "комедия": [
        "Открыт(а) к самопробам",
        "Готов(а) продолжить диалог",
        "Буду рад(а) следующему шагу",
    ],
    "реклама": [
        "Открыт(а) к кастингу",
        "Готов(а) к дальнейшему этапу",
        "Буду рад(а) сотрудничеству",
    ],
    "подростковый": [
        "Открыт(а) к кастингу",
        "Готов(а) к самопробам",
        "Буду рад(а) продолжить",
    ],
    "историческая": [
        "Открыт(а) к продолжению отбора",
        "Готов(а) к следующему этапу",
        "Буду рад(а) диалогу по проекту",
    ],
    "триллер": [
        "Открыт(а) к самопробам",
        "Готов(а) продолжить диалог",
        "Буду рад(а) следующему этапу",
    ],
}

# ---------- УТИЛИТЫ ----------

def save_user(user_id, data):
    with open(f"{DATA_DIR}/{user_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_user(user_id):
    path = f"{DATA_DIR}/{user_id}.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def amvera_chat(messages):
    r = requests.post(
        "https://api.amvera.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {AMVERA_API_KEY}"},
        json={"model": AMVERA_MODEL, "messages": messages},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# ---------- ДИАЛОГ ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я помогу собрать актёрскую видеовизитку под конкретный проект.\n"
        "Это не резюме, а впечатление.\n\nНачнём.",
        reply_markup=ReplyKeyboardMarkup(
            [["Собрать визитку"]], resize_keyboard=True, one_time_keyboard=True
        ),
    )
    return TYPE_PROJECT

async def type_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    save_user(user_id, {"project": {}, "actor": {}, "focus": {}})

    await update.message.reply_text(
        "Выберите тип проекта:",
        reply_markup=ReplyKeyboardMarkup(
            [["современная драма", "комедия", "реклама"],
             ["подростковый", "историческая", "триллер"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return MOOD

async def mood_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    u["project"]["type"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    await update.message.reply_text(
        "Выберите настроение:",
        reply_markup=ReplyKeyboardMarkup(
            [["спокойное", "лёгкое", "сдержанно-уверенное"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return ACTION

async def action_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    u["project"]["mood"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            [["очаровывать", "удерживать внимание", "вовлекать"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return NAME

async def name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    u["project"]["action"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    await update.message.reply_text("Ваше имя:")
    return SCHOOL

async def school_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    u["actor"]["name"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    await update.message.reply_text("Вуз (или «пропустить»):")
    return TYPE

async def type_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    if update.message.text.lower() != "пропустить":
        u["actor"]["school"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    await update.message.reply_text("Типаж (один):")
    return SKILLS

async def skills_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    u["actor"]["type"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    await update.message.reply_text("Релевантные навыки (через запятую):")
    return STATE

async def state_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    u["actor"]["skills"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    await update.message.reply_text(
        "Длительность:",
        reply_markup=ReplyKeyboardMarkup([["30s", "45s"]], resize_keyboard=True),
    )
    return TONE

async def tone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    u["length"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    await update.message.reply_text(
        "Тон:",
        reply_markup=ReplyKeyboardMarkup(
            [["дружелюбный", "строгий", "лёгкая ирония"]],
            resize_keyboard=True,
        ),
    )
    return CTA

async def cta_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    u["tone"] = update.message.text
    save_user(str(update.message.from_user.id), u)

    project = u["project"]["type"]
    pool = CTA_POOLS.get(project, CTA_POOLS["современная драма"])

    await update.message.reply_text(
        "Выберите финальный CTA:",
        reply_markup=ReplyKeyboardMarkup(
            [[c] for c in pool] + [["Свой вариант"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return GENERATE

async def generate_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = load_user(str(update.message.from_user.id))
    text = update.message.text.strip()

    if text == "Свой вариант":
        await update.message.reply_text("Введите ваш CTA:")
        return GENERATE

    u["cta"] = text
    save_user(str(update.message.from_user.id), u)

    prompt = f"""
Ты — эксперт по актёрским видеовизиткам 2026 года.
Создай 2 версии видеовизитки под проект "{u['project']['type']}".

Имя: {u['actor'].get('name')}
Типаж: {u['actor'].get('type')}
Действие: {u['project'].get('action')}
Настроение: {u['project'].get('mood')}
Длина: {u['length']}
Тон: {u['tone']}
Финальный CTA: {u['cta']}

Правила:
- Не резюме
- Одно впечатление
- Минимум слов
"""

    result = amvera_chat([{"role": "system", "content": prompt}])

    await update.message.reply_text(
        f"Готово.\n\n{result}"
    )

    return ConversationHandler.END

# ---------- ЗАПУСК ----------

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TYPE_PROJECT: [MessageHandler(filters.TEXT, type_project)],
            MOOD: [MessageHandler(filters.TEXT, mood_step)],
            ACTION: [MessageHandler(filters.TEXT, action_step)],
            NAME: [MessageHandler(filters.TEXT, name_step)],
            SCHOOL: [MessageHandler(filters.TEXT, school_step)],
            TYPE: [MessageHandler(filters.TEXT, type_step)],
            SKILLS: [MessageHandler(filters.TEXT, skills_step)],
            STATE: [MessageHandler(filters.TEXT, state_step)],
            LENGTH: [MessageHandler(filters.TEXT, state_step)],
            TONE: [MessageHandler(filters.TEXT, tone_step)],
            CTA: [MessageHandler(filters.TEXT, cta_step)],
            GENERATE: [MessageHandler(filters.TEXT, generate_step)],
        },
        fallbacks=[],
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
