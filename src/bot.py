import logging
import os
import requests
import urllib3
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

# ================= SSL FIX =================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= НАСТРОЙКИ =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AMVERA_TOKEN = os.getenv("OPENAI_API_KEY")
AMVERA_URL = "https://kong-proxy.yc.amvera.ru/api/v1/models/gpt"
AMVERA_MODEL = "gpt-5"

if not TELEGRAM_TOKEN or not AMVERA_TOKEN:
    raise RuntimeError("Не заданы TELEGRAM_TOKEN или OPENAI_API_KEY")

# ================= СОСТОЯНИЯ =================

(
    PROJECT,
    NAME,
    EDUCATION,
    ACTION,
    PRESENCE,
    BEHAVIOR,
    FORMAT,
    GENERATE
) = range(8)

# ================= AMVERA =================

def amvera_chat(messages: list[dict]) -> str:
    try:
        amvera_messages = [
            {"role": m["role"], "text": m.get("content", "")}
            for m in messages
        ]

        response = requests.post(
            AMVERA_URL,
            headers={
                "X-Auth-Token": f"Bearer {AMVERA_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "model": AMVERA_MODEL,
                "messages": amvera_messages,
                "temperature": 1,
                "max_tokens": 3500
            },
            timeout=(10, 150),   # ⬅ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ
            verify=False
        )

        response.raise_for_status()
        data = response.json()

        if (
            not isinstance(data, dict)
            or "choices" not in data
            or not data["choices"]
            or "message" not in data["choices"][0]
            or "content" not in data["choices"][0]["message"]
        ):
            raise RuntimeError(f"Некорректный ответ Amvera: {data}")

        return data["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        logging.error("Amvera timeout")
        raise RuntimeError("Генерация заняла слишком много времени. Попробуйте ещё раз.")

    except Exception as e:
        logging.exception("Ошибка Amvera API")
        raise RuntimeError(f"Ошибка генерации: {e}")

# ================= АРХИВ =================

def save_to_archive(context, payload):
    context.user_data.setdefault("archive", []).append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **payload
    })

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Этот бот собирает ТЕКСТ ВИДЕОВИЗИТКИ ДЛЯ КАСТИНГА.\n\n"
        "Не резюме.\n"
        "Не самопробы.\n"
        "А рабочее присутствие в кадре.\n\n"
        "Отвечай просто.",
        reply_markup=ReplyKeyboardMarkup([["Начать"]], resize_keyboard=True)
    )
    return PROJECT

# ================= ВОПРОСЫ =================

async def project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Где ты хочешь, чтобы эта визитка работала?",
        reply_markup=ReplyKeyboardMarkup(
            [["Кино / сериалы"], ["Реклама"], ["Самопробы"]],
            resize_keyboard=True
        )
    )
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["project"] = update.message.text
    await update.message.reply_text("Как тебя зовут?")
    return EDUCATION

async def education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text(
        "Образование (вуз и мастер).\nЕсли нет — нажми «Пропустить».",
        reply_markup=ReplyKeyboardMarkup([["Пропустить"]], resize_keyboard=True)
    )
    return ACTION

async def action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["education"] = (
        update.message.text if update.message.text != "Пропустить" else "не указано"
    )
    await update.message.reply_text(
        "Что ты в первую очередь делаешь в кадре?",
        reply_markup=ReplyKeyboardMarkup(
            [["Удерживаю форму"], ["Создаю давление"], ["Не мешаю сцене"]],
            resize_keyboard=True
        )
    )
    return PRESENCE

async def presence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["action"] = update.message.text
    await update.message.reply_text(
        "Как ты присутствуешь?",
        reply_markup=ReplyKeyboardMarkup(
            [["Спокойно"], ["С паузами"], ["Через взгляд"]],
            resize_keyboard=True
        )
    )
    return BEHAVIOR

async def behavior(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["presence"] = update.message.text
    await update.message.reply_text(
        "Что про тебя часто говорят в кадре?",
        reply_markup=ReplyKeyboardMarkup(
            [["Не торопится"], ["Не объясняет"], ["Чуть неудобный"]],
            resize_keyboard=True
        )
    )
    return FORMAT

async def format_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["behavior"] = update.message.text
    await update.message.reply_text(
        "Выбери формат визитки:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["A — широкий вход"],
                ["B — узкий удар"],
                ["C — стабилизация сцены"]
            ],
            resize_keyboard=True
        )
    )
    return GENERATE

# ================= ГЕНЕРАЦИЯ =================

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["format"] = update.message.text
    await update.message.reply_text("Собираю текст и режу лишнее…")

    system_prompt = f"""
Ты — профессиональный редактор видеовизиток для кастинга.

ФОРМАТ:
A — широкий вход, управляемость
B — давление, риск, неизбежность
C — присутствие без запроса, стабилизация сцены

ВЫБРАННЫЙ ФОРМАТ: {context.user_data['format']}

ПРАВИЛА:
— Только произносимый текст
— До 14 слов в строке
— Минимум 2 паузы
— Один поведенческий приём
— Никакой самопрезентации
— Формат C не убеждает и не давит

ДАННЫЕ АКТЁРА:
Имя: {context.user_data['name']}
Образование: {context.user_data['education']}
Действие: {context.user_data['action']}
Присутствие: {context.user_data['presence']}
Неровность: {context.user_data['behavior']}

ВЫВОД:

ТЕКСТ ДЛЯ КАДРА:
(5–7 строк)

ДЛЯ КАСТИНГА:
Функция в сцене:
Режимы сцены:
Цена отсутствия:
"""

    draft = amvera_chat([{"role": "system", "content": system_prompt}])

    critic_prompt = f"""
Проверь текст.

ЕСЛИ ХОТЬ ОДИН ПУНКТ НЕТ — ПЕРЕПИШИ:

— Можно говорить спокойно?
— Можно молчать и не развалиться?
— Понятно, зачем этот человек в сцене?
— Без него сцена беднее?

Текст:
{draft}

Верни ТОЛЬКО финальную версию
в том же формате.
"""

    final = amvera_chat([{"role": "system", "content": critic_prompt}])

    save_to_archive(context, {
        "actor": context.user_data["name"],
        "format": context.user_data["format"],
        "result": final
    })

    await update.message.reply_text(final)
    return ConversationHandler.END

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PROJECT: [MessageHandler(filters.TEXT, project)],
            NAME: [MessageHandler(filters.TEXT, name)],
            EDUCATION: [MessageHandler(filters.TEXT, education)],
            ACTION: [MessageHandler(filters.TEXT, action)],
            PRESENCE: [MessageHandler(filters.TEXT, presence)],
            BEHAVIOR: [MessageHandler(filters.TEXT, behavior)],
            FORMAT: [MessageHandler(filters.TEXT, format_select)],
            GENERATE: [MessageHandler(filters.TEXT, generate)],
        },
        fallbacks=[]
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
