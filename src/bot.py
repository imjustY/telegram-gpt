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
    filters
)

# ------------------ НАСТРОЙКИ ------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AMVERA_API_KEY = os.getenv("OPENAI_API_KEY")  # длинный токен Amvera
AMVERA_MODEL = "gpt-5"
AMVERA_URL = "https://api.amvera.com/v1/chat/completions"

DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

# ------------------ СОСТОЯНИЯ ------------------

(
    TYPE_PROJECT,
    MOOD,
    ACTION,
    NAME,
    SCHOOL,
    TYPECAST,
    SKILLS,
    STATE,
    HIDDEN_Q,
    LENGTH,
    TONE,
    CTA,
    GENERATE
) = range(13)

# ------------------ УТИЛИТЫ ------------------

def user_file(user_id: str) -> str:
    return os.path.join(DATA_DIR, f"{user_id}.json")

def save_user(user_id: str, data: dict):
    with open(user_file(user_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_user(user_id: str) -> dict:
    if os.path.exists(user_file(user_id)):
        with open(user_file(user_id), "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def amvera_chat(messages: list[str]) -> str:
    headers = {
        "Authorization": f"Bearer {AMVERA_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": AMVERA_MODEL,
        "messages": messages,
        "temperature": 0.7
    }

    r = requests.post(
        AMVERA_URL,
        headers=headers,
        json=payload,
        timeout=60
    )

    if r.status_code != 200:
        logging.error(f"Amvera error {r.status_code}: {r.text}")
        raise RuntimeError("Ошибка запроса к LLM")

    data = r.json()

    return data["choices"][0]["message"]["content"]

# ------------------ ДИАЛОГ ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    save_user(user_id, {
        "project": {},
        "actor": {},
        "focus": {}
    })

    await update.message.reply_text(
        "Привет. Я помогу собрать актёрскую видеовизитку под логику кастинга 2026 года.\n\nВыберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            [["Собрать визитку"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return TYPE_PROJECT

async def type_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Тип проекта:",
        reply_markup=ReplyKeyboardMarkup(
            [["современная драма", "комедия"],
             ["историческая", "триллер"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return MOOD

async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["project"]["type"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text(
        "Настроение визитки:",
        reply_markup=ReplyKeyboardMarkup(
            [["спокойное", "сдержанно-уверенное", "лёгкое"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return ACTION

async def action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["project"]["mood"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text(
        "Действие в кадре:",
        reply_markup=ReplyKeyboardMarkup(
            [["установить контакт", "удерживать внимание", "мягко вовлекать"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["project"]["action"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text("Ваше имя:")
    return SCHOOL

async def school(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["actor"]["name"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text("Вуз:")
    return TYPECAST

async def typecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["actor"]["school"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text("Один ключевой типаж:")
    return SKILLS

async def skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["actor"]["type"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text("Релевантные навыки (через запятую):")
    return STATE

async def state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["actor"]["skills"] = [s.strip() for s in update.message.text.split(",")]
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text("Какое состояние создаёте в кадре?")
    return HIDDEN_Q

async def hidden_q(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["focus"]["state"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text("На какой скрытый вопрос кастинг-директора вы отвечаете?")
    return LENGTH

async def length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["focus"]["hidden_question"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text(
        "Длительность:",
        reply_markup=ReplyKeyboardMarkup(
            [["30 секунд", "45 секунд"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return TONE

async def tone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["length"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text(
        "Тон визитки:",
        reply_markup=ReplyKeyboardMarkup(
            [["дружелюбный", "строгий", "лёгкая ирония"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return CTA

async def cta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["tone"] = update.message.text
    save_user(str(update.effective_user.id), user)

    await update.message.reply_text(
        "Финальный CTA:",
        reply_markup=ReplyKeyboardMarkup(
            [["Готов к пробам", "Буду рад встрече", "Открыт к диалогу"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    return GENERATE

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = load_user(str(update.effective_user.id))
    user["cta"] = update.message.text

    system_prompt = f"""
Ты — эксперт по актёрским видеовизиткам 2026 года.
Создай 2–3 короткие версии текста видеовизитки.

Правила:
- Один типаж, одно настроение.
- Не резюме, не биография.
- Минимум слов, максимум присутствия.
- Длина: {user['length']}
- Тон: {user['tone']}
- Скрытый вопрос: {user['focus']['hidden_question']}
- Финальный CTA: {user['cta']}
"""

    messages = [{"role": "system", "content": system_prompt}]

    try:
        result = amvera_chat(messages)
    except Exception as e:
        await update.message.reply_text(f"Ошибка генерации: {e}")
        return ConversationHandler.END

    await update.message.reply_text(
        "Готово. Варианты визитки:\n\n" + result
    )

    return ConversationHandler.END

# ------------------ MAIN ------------------

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TYPE_PROJECT: [MessageHandler(filters.TEXT, type_project)],
            MOOD: [MessageHandler(filters.TEXT, mood)],
            ACTION: [MessageHandler(filters.TEXT, action)],
            NAME: [MessageHandler(filters.TEXT, name)],
            SCHOOL: [MessageHandler(filters.TEXT, school)],
            TYPECAST: [MessageHandler(filters.TEXT, typecast)],
            SKILLS: [MessageHandler(filters.TEXT, skills)],
            STATE: [MessageHandler(filters.TEXT, state)],
            HIDDEN_Q: [MessageHandler(filters.TEXT, hidden_q)],
            LENGTH: [MessageHandler(filters.TEXT, length)],
            TONE: [MessageHandler(filters.TEXT, tone)],
            CTA: [MessageHandler(filters.TEXT, cta)],
            GENERATE: [MessageHandler(filters.TEXT, generate)],
        },
        fallbacks=[]
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
