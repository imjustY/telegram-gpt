import logging
import os
import requests
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ================= НАСТРОЙКИ =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AMVERA_TOKEN = os.getenv("OPENAI_API_KEY")  # да, именно так
AMVERA_MODEL = "gpt-5"
AMVERA_URL = "https://api.amvera.com/v1/chat/completions"

if not TELEGRAM_TOKEN or not AMVERA_TOKEN:
    raise RuntimeError("Не заданы TELEGRAM_TOKEN или OPENAI_API_KEY")

# ================= СОСТОЯНИЯ =================

(
    PROJECT,
    TASK,
    NAME,
    EDUCATION,
    ACTION,
    PRESENCE,
    BEHAVIOR,
    UNIVERSAL,
    GENERATE
) = range(9)

# ================= AMVERA =================

def amvera_chat(messages: list[dict]) -> str:
    try:
        response = requests.post(
            AMVERA_URL,
            headers={
                "X-Auth-Token": f"Bearer {AMVERA_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "model": AMVERA_MODEL,
                "messages": messages,
                "temperature": 0.7
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()

        # Жёсткая проверка структуры
        if (
            not isinstance(data, dict)
            or "choices" not in data
            or not data["choices"]
            or "message" not in data["choices"][0]
            or "content" not in data["choices"][0]["message"]
        ):
            logging.error(f"Некорректный ответ Amvera: {data}")
            raise RuntimeError("Некорректная структура ответа LLM")

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        logging.exception("Ошибка Amvera API")
        raise RuntimeError(f"Ошибка генерации: {e}")

# ================= АРХИВ =================

def save_to_archive(context, payload):
    record = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **payload
    }
    context.user_data.setdefault("archive", []).append(record)

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["archive"] = []

    await update.message.reply_text(
        "Этот бот помогает собрать текст видеовизитки для кастинга.\n"
        "Не резюме. Не рассказ о себе.\n"
        "А впечатление человека, которого хочется смотреть дальше.\n\n"
        "Займёт 5–7 минут.",
        reply_markup=ReplyKeyboardMarkup([["Начать"]], resize_keyboard=True)
    )
    return PROJECT

# ================= БЛОК 1. ПРОЕКТ =================

async def project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для какого проекта вы делаете визитку?",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Современная драма", "Комедия"],
                ["Реклама", "Подростковый проект"],
                ["Исторический", "Триллер / мистика"]
            ],
            resize_keyboard=True
        )
    )
    return TASK

async def task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["project"] = update.message.text
    await update.message.reply_text(
        "Какую задачу должна решать эта визитка?",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Познакомить кастинг со мной"],
                ["Закрепить конкретный типаж"],
                ["Обновить материалы"],
                ["Подготовить под самопробы"]
            ],
            resize_keyboard=True
        )
    )
    return NAME

# ================= БЛОК 2. ФАКТЫ =================

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["task"] = update.message.text
    await update.message.reply_text("Как вас зовут?")
    return EDUCATION

async def education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text(
        "Образование (если есть):",
        reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
    )
    return ACTION

# ================= БЛОК 3. ПОВЕДЕНИЕ =================

async def action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Пропустить":
        context.user_data["education"] = update.message.text

    await update.message.reply_text(
        "В этой визитке вы в кадре в первую очередь:",
        reply_markup=ReplyKeyboardMarkup(
            [["Очаровываю"], ["Удерживаю внимание"], ["Вовлекаю"]],
            resize_keyboard=True
        )
    )
    return PRESENCE

async def presence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["action"] = update.message.text
    await update.message.reply_text(
        "Как вы присутствуете в кадре?",
        reply_markup=ReplyKeyboardMarkup(
            [["Спокойный центр"], ["Живой собеседник"], ["Загадка"]],
            resize_keyboard=True
        )
    )
    return BEHAVIOR

async def behavior(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["presence"] = update.message.text
    await update.message.reply_text(
        "В кадре вы ведёте себя как человек, который:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Не торопится и даёт себя рассмотреть"],
                ["Спокойно удерживает контакт"],
                ["Мягко притягивает внимание"],
                ["Смотрит прямо и не объясняется"],
                ["Чуть недоговаривает"]
            ],
            resize_keyboard=True
        )
    )
    return UNIVERSAL

# ================= УНИВЕРСАЛЬНОСТЬ =================

async def universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["behavior"] = update.message.text
    await update.message.reply_text(
        "Визитка строго под этот проект или более универсальная?",
        reply_markup=ReplyKeyboardMarkup(
            [["Строго под проект"], ["Более универсальная"]],
            resize_keyboard=True
        )
    )
    return GENERATE

# ================= ГЕНЕРАЦИЯ + CRITIC =================

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["universal"] = update.message.text
    await update.message.reply_text("Генерирую и проверяю текст…")

    system_prompt = f"""
Ты — профессиональный редактор актёрских видеовизиток 2026 года.

Проект: {context.user_data['project']}
Имя: {context.user_data['name']}
Образование: {context.user_data.get('education', 'не указано')}
Действие: {context.user_data['action']}
Тип присутствия: {context.user_data['presence']}
Поведение: {context.user_data['behavior']}

Сделай ДВЕ версии текста видеовизитки.
Не резюме. Не объяснение. Недосказанно.
"""

    draft = amvera_chat([{"role": "system", "content": system_prompt}])

    critic_prompt = f"""
Оцени текст по критериям (1–5):
1. Читается ли человек без звука?
2. Есть ли одно доминирующее впечатление?
3. Понятно ли, под какой проект визитка?
4. Нет ли лишних объяснений?
5. Хочется ли смотреть дальше?

Текст:
{draft}

Если средний балл ниже 4:
— перепиши текст,
— сохрани поведение,
— усили впечатление,
— сократи объяснения.

Верни строго в формате:
ВЕРСИЯ 1:
...
ВЕРСИЯ 2:
...
ПОЯСНЕНИЕ:
...
"""

    final = amvera_chat([{"role": "system", "content": critic_prompt}])

    save_to_archive(
        context,
        {
            "project": context.user_data["project"],
            "task": context.user_data["task"],
            "behavior": {
                "action": context.user_data["action"],
                "presence": context.user_data["presence"],
                "formula": context.user_data["behavior"]
            },
            "result": final
        }
    )

    await update.message.reply_text(final)
    return ConversationHandler.END

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PROJECT: [MessageHandler(filters.TEXT, project)],
            TASK: [MessageHandler(filters.TEXT, task)],
            NAME: [MessageHandler(filters.TEXT, name)],
            EDUCATION: [MessageHandler(filters.TEXT, education)],
            ACTION: [MessageHandler(filters.TEXT, action)],
            PRESENCE: [MessageHandler(filters.TEXT, presence)],
            BEHAVIOR: [MessageHandler(filters.TEXT, behavior)],
            UNIVERSAL: [MessageHandler(filters.TEXT, universal)],
            GENERATE: [MessageHandler(filters.TEXT, generate)],
        },
        fallbacks=[]
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
