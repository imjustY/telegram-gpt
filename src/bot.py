import logging
import json
import os

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

from openai import OpenAI

# ---------------- НАСТРОЙКИ ----------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не задан")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY не задан")

client = OpenAI(api_key=OPENAI_API_KEY)
MODEL = "gpt-4o-mini"

# ---------------- СОСТОЯНИЯ ----------------

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

# ---------------- СТАРТ ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "Этот бот помогает собрать текст видеовизитки для кастинга.\n"
        "Не резюме. Не рассказ о себе.\n"
        "А короткое впечатление человека, которого хочется смотреть дальше.\n\n"
        "Займёт 5–7 минут.",
        reply_markup=ReplyKeyboardMarkup(
            [["Начать"]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return PROJECT

# ---------------- БЛОК 1. ПРОЕКТ ----------------

async def project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для какого проекта вы делаете визитку?",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Современная драма", "Комедия"],
                ["Реклама", "Подростковый проект"],
                ["Исторический", "Триллер / мистика"]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
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
                ["Обновить материалы под кастинги"],
                ["Подготовить визитку под самопробы"]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return NAME

# ---------------- БЛОК 2. ФАКТЫ ----------------

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["task"] = update.message.text
    await update.message.reply_text("Как вас зовут?")
    return EDUCATION

async def education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text

    await update.message.reply_text(
        "Образование (если есть). Можно коротко.",
        reply_markup=ReplyKeyboardMarkup(
            [["Пропустить"]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return ACTION

# ---------------- БЛОК 3. ПОВЕДЕНИЕ ----------------

async def action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Пропустить":
        context.user_data["education"] = update.message.text

    await update.message.reply_text(
        "В этой визитке вы в кадре в первую очередь:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Очаровываю"],
                ["Удерживаю внимание"],
                ["Вовлекаю в диалог"]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return PRESENCE

async def presence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["action"] = update.message.text

    await update.message.reply_text(
        "Как вы присутствуете в кадре?",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Спокойный центр"],
                ["Живой собеседник"],
                ["Загадка"]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
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
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return UNIVERSAL

# ---------------- БЛОК 4. УНИВЕРСАЛЬНОСТЬ ----------------

async def universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["behavior"] = update.message.text

    await update.message.reply_text(
        "Вы хотите визитку строго под этот проект или более универсальную?",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Строго под этот проект"],
                ["Более универсальную"]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return GENERATE

# ---------------- ГЕНЕРАЦИЯ ----------------

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["universal"] = update.message.text

    await update.message.reply_text("Собираю две версии текста…")

    system_prompt = f"""
Ты — профессиональный редактор актёрских видеовизиток 2026 года.

Создай ДВЕ версии текста видеовизитки под проект: {context.user_data['project']}.

Данные:
Имя: {context.user_data.get('name')}
Образование: {context.user_data.get('education', 'не указано')}
Действие: {context.user_data['action']}
Тип присутствия: {context.user_data['presence']}
Поведение: {context.user_data['behavior']}

Правила:
- не резюме
- не объяснение
- одно впечатление
- читаемость без звука
- недосказанность

После текстов:
1. кратко опиши впечатление,
2. дай 1–2 рекомендации по записи.
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system_prompt}],
        temperature=0.7
    )

    result = response.choices[0].message.content

    await update.message.reply_text(result)

    return ConversationHandler.END

# ---------------- MAIN ----------------

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
