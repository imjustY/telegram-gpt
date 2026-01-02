import logging
import os
import re
import time

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ======================
# НАСТРОЙКИ
# ======================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODEL_NAME = "gpt-4o-mini"

MAX_RETRIES = 6
TEMPERATURE = 0.6

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ======================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ======================

def build_system_prompt(user_data: dict) -> str:
    gender = user_data["gender"]
    education = user_data["education"]
    name = user_data["name"]

    education_verb = "закончила" if gender == "female" else "закончил"

    return f"""
Ты создаёшь ТЕКСТ ВИДЕОВИЗИТКИ АКТЁРА для кастинг-директора.

ЖЁСТКИЕ ПРАВИЛА:
1. Это НЕ самопробы.
2. Это НЕ рассказ о себе.
3. Минимум текста.
4. Один типаж.
5. Без объяснений, оценок и комментариев.
6. Вежливо, профессионально, без высокомерия.

ОБЯЗАТЕЛЬНАЯ СТРУКТУРА (СТРОГО):
1. Приветствие: "Здравствуйте." ИЛИ "Добрый день."
2. Представление: "Меня зовут {name}."
3. Образование: "Я {education_verb} {education}."
4. 1–2 строки ощущения / присутствия (не игра, не эмоции).
5. Готовность к сотрудничеству (вежливо).
6. Корректное завершение без закрытия контакта.

ЗАПРЕЩЕНО:
- универсальные формулировки
- демонстрация актёрской техники
- самопробы
- "без комментариев", "дальше не поясняю"
- высокомерие
- обрывать коммуникацию

Пол актёра должен быть ОДНОЗНАЧЕН.
Текст должен звучать как ЖИВАЯ РЕЧЬ, а не отчёт.
""".strip()


def call_llm(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "messages": [
            {"role": "system", "content": prompt},
        ],
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    logging.info("Amvera payload size: %s chars", len(prompt))

    r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    r.raise_for_status()

    return r.json()["choices"][0]["message"]["content"].strip()


def is_greeting(line: str) -> bool:
    return re.match(r"^(Здравствуйте|Добрый день)[.!]?$", line.strip()) is not None


def validate_script(text: str, gender: str) -> list[str]:
    problems = []
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    if not lines:
        return ["Пустой текст."]

    if not is_greeting(lines[0]):
        problems.append("Нет корректного приветствия.")

    if not any(re.match(r"^Меня зовут\s+\S+", ln) for ln in lines):
        problems.append("Нет строки 'Меня зовут ...'.")

    if gender == "female":
        if not any(("Я окончила" in ln or "Я закончила" in ln) for ln in lines):
            problems.append("Нет женской формы образования.")
    else:
        if not any(("Я окончил" in ln or "Я закончил" in ln) for ln in lines):
            problems.append("Нет мужской формы образования.")

    if len(lines) < 4:
        problems.append("Слишком мало строк.")

    forbidden = [
        "самопробы",
        "без комментариев",
        "без пояснений",
        "дальше",
        "я умею",
        "я могу всё",
    ]

    for f in forbidden:
        if f in text.lower():
            problems.append(f"Запрещённая формулировка: {f}")

    return problems


# ======================
# TELEGRAM HANDLERS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет. Я помогу создать текст видеовизитки.\n"
        "Напиши:\n"
        "Имя, пол (м/ж), учебное заведение\n\n"
        "Пример:\n"
        "Анна Смирнова, ж, ГИТИС"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw = update.message.text
        name, gender_raw, education = [x.strip() for x in raw.split(",")]

        gender = "female" if gender_raw.lower().startswith("ж") else "male"

        user_data = {
            "name": name,
            "gender": gender,
            "education": education,
        }

    except Exception:
        await update.message.reply_text(
            "Неверный формат.\n"
            "Пример:\nАнна Смирнова, ж, ГИТИС"
        )
        return

    prompt = build_system_prompt(user_data)

    for attempt in range(1, MAX_RETRIES + 1):
        logging.info("Generation attempt %s", attempt)

        draft = call_llm(prompt)
        logging.info("Draft (first 400 chars): %s", draft[:400].replace("\n", "\\n"))

        problems = validate_script(draft, user_data["gender"])

        if not problems:
            await update.message.reply_text("Готово:\n\n" + draft)
            return

        logging.warning("Validation failed: %s", problems)
        time.sleep(1)

    await update.message.reply_text(
        "Не удалось собрать корректный текст.\n"
        "Попробуй изменить исходные данные."
    )


# ======================
# MAIN
# ======================

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
