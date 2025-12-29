import logging
import os
import re
import requests
import urllib3
from datetime import datetime
from typing import Dict, List, Tuple

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ================= SSL FIX =================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= НАСТРОЙКИ =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AMVERA_TOKEN = os.getenv("OPENAI_API_KEY")  # длинный токен Amvera
AMVERA_URL = "https://kong-proxy.yc.amvera.ru/api/v1/models/gpt"
AMVERA_MODEL = "gpt-5"

if not TELEGRAM_TOKEN or not AMVERA_TOKEN:
    raise RuntimeError("Не заданы TELEGRAM_TOKEN или OPENAI_API_KEY")

# ================= СОСТОЯНИЯ =================
(
    START_MENU,
    PROJECT,
    TYPECAST,
    NAME,
    GENDER,
    EDUCATION,
    TEMPO,
    ATTENTION,
    BORDER,
    ANCHOR,
    GENERATE,
) = range(11)

# ================= AMVERA =================
def amvera_chat(messages: List[Dict[str, str]]) -> str:
    try:
        amvera_messages = [{"role": m["role"], "content": m.get("content", "")} for m in messages]

        payload = {
            "model": AMVERA_MODEL,
            "messages": amvera_messages,
            "temperature": 1,               # обязательно 1
            "max_completion_tokens": 1600   # нам не нужно 3500, иначе начнёт расползаться
        }

        logging.info(f"Amvera payload size: {sum(len(m['content']) for m in amvera_messages)} chars")
        response = requests.post(
            AMVERA_URL,
            headers={
                "X-Auth-Token": f"Bearer {AMVERA_TOKEN}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=(10, 300),
            verify=False
        )

        response.raise_for_status()
        data = response.json()

        if "choices" not in data or not data["choices"]:
            raise RuntimeError(f"Некорректный ответ Amvera: {data}")

        return data["choices"][0]["message"]["content"]

    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTPError: {e.response.status_code} {e.response.text}")
        raise RuntimeError(f"Ошибка генерации: {e}")
    except Exception as e:
        logging.exception("Ошибка Amvera API")
        raise RuntimeError(f"Ошибка генерации: {e}")

# ================= АРХИВ =================
def save_to_archive(context, payload):
    context.user_data.setdefault("archive", []).append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **payload
    })

# ================= ВАЛИДАЦИЯ ТЕКСТА =================
GREETINGS = ("Здравствуйте.", "Добрый день.")
FORBIDDEN_SUBSTRINGS = [
    # Самопробы/сцены/партнёры/обстоятельства
    "самопр", "сцена", "партн", "обстоятель",
    # поучения/разрешения/закрытие коммуникации
    "этого достаточно", "можно двигаться", "дальше без", "без комментар", "без пояснен",
    # манифест/высокомерие
    "я не для", "со мной не", "я работаю с", "такой подход", "не упрощаю",
    # мета-отчётность
    "функция в сцене", "режимы сцены", "цена отсутствия",
]

ALLOWED_ENDINGS_FEMALE = [
    "Буду рада совместной работе.",
    "Рада возможности совместной работы.",
    "Открыта к профессиональному сотрудничеству."
]
ALLOWED_ENDINGS_MALE = [
    "Буду рад совместной работе.",
    "Рад возможности совместной работы.",
    "Открыт к профессиональному сотрудничеству."
]

_word_re = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+")

def count_words(line: str) -> int:
    return len(_word_re.findall(line.strip()))

def normalize_text(t: str) -> str:
    # Убираем лишние пробелы, приводим переносы
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.split("\n")]
    # убираем пустые хвосты, но оставляем пустые строки как разделители
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()

def validate_script(text: str, gender: str) -> Tuple[bool, List[str]]:
    """
    gender: 'female' or 'male'
    """
    problems = []
    t = normalize_text(text)

    # Общие запреты
    low = t.lower()
    for s in FORBIDDEN_SUBSTRINGS:
        if s in low:
            problems.append(f"Запрещённый фрагмент: '{s}'")

    # Должно начинаться с приветствия
    if not any(t.startswith(g) for g in GREETINGS):
        problems.append("Нет приветствия ('Здравствуйте.' или 'Добрый день.').")

    # Должна быть формула "Меня зовут ..."
    if "Меня зовут" not in t:
        problems.append("Нет формулы представления: 'Меня зовут ...'.")

    # Образование: должна быть строка с "Я окончил/окончила"
    if gender == "female":
        if "Я окончила" not in t:
            problems.append("Нет женской формы в образовании: 'Я окончила ...'.")
        allowed_endings = ALLOWED_ENDINGS_FEMALE
    else:
        if "Я окончил" not in t:
            problems.append("Нет мужской формы в образовании: 'Я окончил ...'.")
        allowed_endings = ALLOWED_ENDINGS_MALE

    # Финальная вежливая формула должна быть из списка
    if not any(t.endswith(e) for e in allowed_endings):
        problems.append("Нет корректной финальной формулы готовности к совместной работе (или не совпадает род).")

    # Запрет на "Имя Фамилия." без глагола: примитивно ловим строку, состоящую из 2 слов и точки
    for ln in t.split("\n"):
        s = ln.strip()
        if s and s.endswith(".") and count_words(s) == 2 and "Меня зовут" not in s and s not in GREETINGS:
            # это может быть нормальная фраза из 2 слов, но чаще это "Иван Иванов."
            # страхуемся: если оба слова с заглавной
            parts = s[:-1].split()
            if all(p[:1].isupper() for p in parts):
                problems.append("Обнаружена строка вида 'Имя Фамилия.' без формулы 'Меня зовут ...'.")

    # Ритм: ядро (3–4 строки) должно быть 6–14 слов/строка, без телеграфа
    lines = [ln for ln in t.split("\n") if ln.strip() != ""]
    if len(lines) < 6:
        problems.append("Слишком мало строк: ожидается приветствие, имя, образование, 3–4 строки ядра и финал.")
    else:
        # Ожидаем структуру:
        # 0 greeting
        # 1 "Меня зовут..."
        # 2 "Я окончил/окончила..."
        # далее 3-4 строки ядра
        # последняя строка финал
        greeting_line = lines[0]
        if greeting_line not in GREETINGS:
            problems.append("Первая строка не является допустимым приветствием.")

        # Проверяем ядро по длине строк
        # Индексы ядра: 3..(len(lines)-2)
        core = lines[3:-1] if len(lines) >= 7 else []
        if not (3 <= len(core) <= 4):
            problems.append("Ядро должно быть 3–4 строки.")
        else:
            for ln in core:
                wc = count_words(ln)
                if wc < 6 or wc > 14:
                    problems.append(f"Нарушение ритма: строка ядра '{ln}' содержит {wc} слов (норма 6–14).")

            # анти-телеграф: запрещаем 2 строки подряд <=7 слов
            short_streak = 0
            for ln in core:
                if count_words(ln) <= 7:
                    short_streak += 1
                else:
                    short_streak = 0
                if short_streak >= 2:
                    problems.append("Телеграфный ритм: две короткие строки подряд в ядре.")
                    break

    return (len(problems) == 0, problems)

# ================= КОНТЕНТ БЛОКИ ПОСЛЕ ТЕКСТА =================
RECORDING_RECOMMENDATIONS = """Рекомендации по съёмке (обязательно)

Камера и кадр
- Статичная камера
- Крупный или средний план
- Один кадр

Взгляд
- В камеру или чуть мимо
- Осознанно

Свет и звук
- Лицо хорошо читается
- Без жёстких теней
- Чистый звук, без эха
- Без музыки

Запрещено
- Монтаж
- Смена планов
- Эффекты
- Музыка

Качество
- Достаточное
- Не «киношное»
- Стерильный продакшн не является преимуществом

Проверка
- Если визитка не работает без звука — формат нарушен
"""

USAGE_INSTRUCTIONS = """Инструкция использования

- Записывай визитку одним кадром.
- Назови файл: Имя_Фамилия_типаж_год
- Используй визитку не дольше 6–9 месяцев.
- Если меняется внешность, возраст или типаж — визитка собирается заново.
- Готовый текст используется без изменений.
"""

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Этот бот помогает собрать видеовизитку для кастинга.\n\n"
        "Это НЕ резюме.\n"
        "НЕ самопробы.\n"
        "НЕ демонстрация актёрской техники.\n\n"
        "Визитка не объясняет, кто ты.\n"
        "Она даёт почувствовать, какой ты.\n\n"
        "Готов начать?",
        reply_markup=ReplyKeyboardMarkup([["Начать"]], resize_keyboard=True)
    )
    return PROJECT

# ================= ЭКРАН 1: ПРОЕКТ =================
async def project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text != "Начать":
        # не душим пользователя, просто возвращаем к кнопке
        await update.message.reply_text(
            "Нажми «Начать».",
            reply_markup=ReplyKeyboardMarkup([["Начать"]], resize_keyboard=True)
        )
        return PROJECT

    await update.message.reply_text(
        "Для какого типа проекта ты собираешь эту видеовизитку?",
        reply_markup=ReplyKeyboardMarkup(
            [["Кино / сериал"], ["Театр"], ["Реклама"]],
            resize_keyboard=True
        )
    )
    return TYPECAST

# ================= ЭКРАН 2: ТИПАЖ =================
async def typecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["project"] = (update.message.text or "").strip()

    await update.message.reply_text(
        "В каком качестве тебя стабильно приглашают сейчас?\n"
        "(не «хочу», не «могу», а именно сейчас)"
    )
    return NAME

# ================= ЭКРАН 3: ИМЯ =================
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tc = (update.message.text or "").strip()
    low = tc.lower()
    if any(w in low for w in ["хочу", "могу", "планир", "мечта", "было бы"]):
        await update.message.reply_text(
            "Нужен ответ про то, как тебя приглашают СЕЙЧАС. Одной фразой, без желаний."
        )
        return NAME

    context.user_data["typecast"] = tc

    await update.message.reply_text("Как тебя зовут? (имя и фамилия)")
    return GENDER

# ================= ЭКРАН 4: ПОЛ =================
async def gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = (update.message.text or "").strip()

    await update.message.reply_text(
        "Укажи пол для корректной формулировки текста (это важно для русского языка).",
        reply_markup=ReplyKeyboardMarkup([["Мужской"], ["Женский"]], resize_keyboard=True)
    )
    return EDUCATION

# ================= ЭКРАН 5: ОБРАЗОВАНИЕ =================
async def education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    g = (update.message.text or "").strip()
    if g not in ("Мужской", "Женский"):
        await update.message.reply_text(
            "Выбери кнопку: «Мужской» или «Женский».",
            reply_markup=ReplyKeyboardMarkup([["Мужской"], ["Женский"]], resize_keyboard=True)
        )
        return EDUCATION

    context.user_data["gender"] = "male" if g == "Мужской" else "female"

    await update.message.reply_text(
        "Какое актёрское образование ты получил(а)?\n(вуз и мастер)\n"
        "Если нет профильного — нажми «Нет профильного образования».",
        reply_markup=ReplyKeyboardMarkup([["Нет профильного образования"]], resize_keyboard=True)
    )
    return TEMPO

# ================= ЭКРАН 5.1: ТЕМП =================
async def tempo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    edu = (update.message.text or "").strip()
    context.user_data["education"] = edu

    await update.message.reply_text(
        "Когда начинается работа, тебе комфортнее:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["не спешить и разбираться постепенно"],
                ["держать ровный, рабочий темп"],
                ["сразу быть собранным и включённым"],
            ],
            resize_keyboard=True
        )
    )
    return ATTENTION

# ================= ЭКРАН 5.2: ВНИМАНИЕ =================
async def attention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tempo"] = (update.message.text or "").strip()

    await update.message.reply_text(
        "В работе ты чаще всего следишь за:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["тем, что происходит между людьми"],
                ["реакциями другого человека"],
                ["тем, чтобы дело не развалилось"],
            ],
            resize_keyboard=True
        )
    )
    return BORDER

# ================= ЭКРАН 5.3: ГРАНИЦА =================
async def border(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["attention"] = (update.message.text or "").strip()

    await update.message.reply_text(
        "Про тебя чаще говорят, что ты:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["не торопишь и не подгоняешь"],
                ["не давишь, даже когда сложно"],
                ["не сглаживаешь острые моменты"],
            ],
            resize_keyboard=True
        )
    )
    return ANCHOR

# ================= ЭКРАН 5.4: ОПОРА =================
async def anchor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["border"] = (update.message.text or "").strip()

    await update.message.reply_text(
        "Что в тебе остаётся одинаковым, даже если меняется ситуация?",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["мой темп"],
                ["моё внимание"],
                ["моя реакция"],
            ],
            resize_keyboard=True
        )
    )
    return GENERATE

# ================= ГЕНЕРАЦИЯ =================
def build_system_prompt(d: Dict[str, str]) -> str:
    gender = d["gender"]  # 'male' or 'female'
    if gender == "female":
        education_verb = "окончила"
        end_variants = "\n".join(f"- {x}" for x in ALLOWED_ENDINGS_FEMALE)
    else:
        education_verb = "окончил"
        end_variants = "\n".join(f"- {x}" for x in ALLOWED_ENDINGS_MALE)

    # Образование: если нет профильного, пишем мягко, но всё равно факт
    edu = d.get("education", "").strip()
    if edu == "Нет профильного образования":
        edu_line = f"Я {education_verb} обучение вне профильного актёрского вуза."
    else:
        edu_line = f"Я {education_verb} {edu}."

    return f"""
Ты пишешь видеовизитку для кастинга в России.

КЛЮЧЕВОЕ ПРАВИЛО:
Видеовизитка не объясняет, кто человек.
Она даёт почувствовать, какой он.

ПРОЕКТ: {d["project"]}
ТЕКУЩИЙ ТИПАЖ (СЕЙЧАС): {d["typecast"]}

ЖЁСТКИЙ ПРОТОКОЛ (не нарушать):
1) Приветствие: только "Здравствуйте." или "Добрый день."
2) Представление: строго "Меня зовут {d["name"]}."
3) Образование: одной строкой, с правильным родом. Используй форму "{education_verb}".
4) Ядро: 3–4 строки. Без сцен, партнёров, обстоятельств. Без рассуждений. Без "я умею". Без манифестов.
5) Финал: одна вежливая строка готовности к совместной работе. Только из списка ниже и с правильным родом.

ФИКСАЦИЯ ПОЛА (чтобы не было путаницы):
- в тексте должны быть минимум ДВА маркера рода: в строке образования и в финале.

РИТМ (обязательно):
- строки ядра: 6–14 слов (оптимально 8–12)
- нельзя делать телеграф: две короткие строки подряд (<=7 слов)
- одна строка = одна мысль, без "потому что/поэтому/чтобы"

ЗАПРЕТЫ:
- универсальность ("подойдёт всем")
- демонстрация актёрской техники
- самопробы, сцены, партнёры, "обстоятельства"
- попытка понравиться всем
- поучения/разрешения/закрытие диалога ("Этого достаточно.", "Можно двигаться дальше." и т.п.)
- слова и конструкции: "функция в сцене", "режимы", "цена отсутствия"

ДАННЫЕ ДЛЯ ОЩУЩЕНИЯ (без терминов, только как ориентир):
- Темп: {d["tempo"]}
- Внимание: {d["attention"]}
- Граница: {d["border"]}
- Опора: {d["anchor"]}

СТРОКА ОБРАЗОВАНИЯ (используй как факт, не как резюме):
{edu_line}

ДОПУСТИМЫЕ ФИНАЛЫ (выбери один, без вариаций):
{end_variants}

ФОРМАТ ВЫВОДА (строго):
Приветствие
Меня зовут ...
Строка образования

3–4 строки ядра (каждая с новой строки)

Финал (одна строка)
""".strip()

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["anchor"] = (update.message.text or "").strip()

    await update.message.reply_text("Собираю текст визитки. Убираю лишнее.")

    data = context.user_data
    system_prompt = build_system_prompt(data)

    # молчаливая перегенерация
    last_problems = []
    final_text = None

    for _ in range(6):  # 6 попыток хватает: мы не пишем роман
        draft = amvera_chat([{"role": "system", "content": system_prompt}])
        draft = normalize_text(draft)

        ok, problems = validate_script(draft, data["gender"])
        if ok:
            final_text = draft
            break
        last_problems = problems

    if not final_text:
        # Даже если модель упёрлась, пользователю не надо видеть внутренности.
        # Дадим короткое сообщение + попросим /start (без вопросов по одному).
        logging.error("Не удалось собрать валидный текст. Problems: %s", last_problems)
        await update.message.reply_text(
            "Не собрался корректный текст визитки. Начни заново: /start"
        )
        return ConversationHandler.END

    # сохраняем
    save_to_archive(context, {
        "actor": data.get("name"),
        "project": data.get("project"),
        "typecast": data.get("typecast"),
        "gender": data.get("gender"),
        "result": final_text
    })

    # выдача: текст + рекомендации + инструкция + закрытие
    await update.message.reply_text(final_text)
    await update.message.reply_text(RECORDING_RECOMMENDATIONS)
    await update.message.reply_text(USAGE_INSTRUCTIONS)
    await update.message.reply_text("Визитка собрана.\nИспользуй как есть.")

    return ConversationHandler.END

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PROJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, project)],
            TYPECAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, typecast)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, gender)],
            EDUCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, education)],
            TEMPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, tempo)],
            ATTENTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, attention)],
            BORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, border)],
            ANCHOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, anchor)],
            GENERATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
