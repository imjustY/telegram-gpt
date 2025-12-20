import logging
import json
import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackContext, ConversationHandler
)
import openai
import requests

# --- Настройки ---
logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
USE_AMVERA = os.environ.get("USE_AMVERA", "False") == "True"
AMVERA_API_KEY = os.environ.get("AMVERA_API_KEY") or OPENAI_API_KEY
AMVERA_MODEL = os.environ.get("AMVERA_MODEL", "gpt-5")

openai.api_key = OPENAI_API_KEY

# --- Состояния ---
(TYPE_PROJECT, MOOD, ACTION, NAME, TYPE, SKILLS, STATE, HIDDEN_Q, LENGTH, TONE, CTA, GENERATE) = range(12)
DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

# --- Вспомогательные функции ---
def save_user_json(user_id, data):
    path = os.path.join(DATA_DIR, f"{user_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_user_json(user_id):
    path = os.path.join(DATA_DIR, f"{user_id}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def amvera_chat(messages):
    url = "https://api.amvera.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AMVERA_API_KEY}"}
    data = {"model": AMVERA_MODEL, "messages": messages}
    r = requests.post(url, json=data, headers=headers)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def gpt_chat(messages):
    if USE_AMVERA:
        return amvera_chat(messages)
    else:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7
        )
        return response['choices'][0]['message']['content']

# --- Диалоговый флоу ---
def start(update: Update, context: CallbackContext):
    context.user_data['current_state'] = TYPE_PROJECT
    update.message.reply_text(
        "Привет! Я помогу создать актёрскую видеовизитку под конкретный кастинг 2026 года.\n"
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup([["Собрать визитку", "Переписать мой текст"]], one_time_keyboard=True)
    )
    return TYPE_PROJECT

def type_project(update: Update, context: CallbackContext):
    context.user_data['current_state'] = MOOD
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
        "review": {
            "scores": {
                "эмоциональное попадание": 0,
                "соответствие одному типажу": 0,
                "минимум информации, максимум ощущения": 0,
                "ответ на скрытый вопрос": 0
            },
            "changes": ""
        }
    }
    save_user_json(user_id, user_json)

    update.message.reply_text(
        "Выберите тип проекта:",
        reply_markup=ReplyKeyboardMarkup([
            ["современная драма","лёгкая драма","комедия"],
            ["подростковый","реклама","историческая","триллер"]
        ], one_time_keyboard=True)
    )
    return MOOD

def mood_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = ACTION
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['project']['type'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text(
        "Выберите настроение:",
        reply_markup=ReplyKeyboardMarkup([["спокойное","лёгкое","сдержанно-уверенное"]], one_time_keyboard=True)
    )
    return ACTION

def action_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = NAME
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['project']['mood'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text(
        "Выберите действие видеовизитки:",
        reply_markup=ReplyKeyboardMarkup([
            ["установить контакт","удерживать внимание","мягко вовлекать","предложить партнёрство"]
        ], one_time_keyboard=True)
    )
    return NAME

def name_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = TYPE
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['project']['action'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text("Введите ваше имя:")
    return TYPE

def type_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = SKILLS
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['actor']['name'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text("Введите ваш вуз:")
    return SKILLS

def skills_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = STATE
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['actor']['school'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text("Опишите ключевой типаж (один образ):")
    return STATE

def state_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = HIDDEN_Q
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['actor']['type'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text("Укажите релевантные навыки (через запятую):")
    return HIDDEN_Q

def hidden_question_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = LENGTH
    user_json = load_user_json(str(update.message.from_user.id))
    skills = [s.strip() for s in update.message.text.split(",")]
    user_json['actor']['skills'] = skills
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text("Какое состояние хотите передать в кадре?")
    return LENGTH

def length_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = TONE
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['focus']['state'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text("На какой вопрос кастинг-директора вы хотите ответить?")
    return TONE

def tone_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = CTA
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['focus']['hidden_question'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text(
        "Выберите длительность визитки:",
        reply_markup=ReplyKeyboardMarkup([["30s","45s"]], one_time_keyboard=True)
    )
    return CTA

def cta_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = GENERATE
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['length'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text(
        "Выберите тон текста:",
        reply_markup=ReplyKeyboardMarkup([["дружелюбный","строгий","лёгкая ирония"]], one_time_keyboard=True)
    )
    return GENERATE

def generate_step(update: Update, context: CallbackContext):
    context.user_data['current_state'] = None
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['tone'] = update.message.text
    save_user_json(user_json['user_id'], user_json)
    update.message.reply_text("Введите финальный CTA (или пропустите):")
    return finalize_step

def finalize_step(update: Update, context: CallbackContext):
    user_json = load_user_json(str(update.message.from_user.id))
    user_json['cta'] = update.message.text
    save_user_json(user_json['user_id'], user_json)

    system_prompt = f"""
Роль: эксперт по актёрским видеовизиткам 2026 года
Создай 2–3 версии текста визитки под выбранный тип проекта, с фокусом на эмоциональное попадание и состояние, а не на информацию.
Правила:
- Не рассказывать о себе, не использовать биографии или резюме.
- Один типаж, одно настроение, одна визитка.
- Минимум текста, максимум ощущения.
- Drafts должны отвечать хотя бы на один скрытый вопрос кастинг-директора: {user_json['focus']['hidden_question']}
- Длина: {user_json['length']}
- Тон: {user_json['tone']}
- Вывод: drafts + краткий отчёт самопроверки + советы по записи
"""
    messages = [{"role": "system", "content": system_prompt}]
    drafts_text = gpt_chat(messages)

    critique_prompt = f"""
Оцени следующие тексты по критериям:
1. Эмоциональное попадание
2. Соответствие одному типажу и настроению
3. Минимум информации, максимум ощущения
4. Ответ на скрытый вопрос кастинг-директора

Тексты: {drafts_text}

Если средний балл <4, перепиши, чтобы улучшить по всем критериям. Кратко объясни изменения (не более 4 строк).
"""
    critique_messages = [{"role": "user", "content": critique_prompt}]
    final_text = gpt_chat(critique_messages)

    user_json['drafts'] = drafts_text.split("\n\n")
    user_json['final'] = final_text
    save_user_json(user_json['user_id'], user_json)

    update.message.reply_text(
        f"Визитка готова!\n\nDrafts:\n{drafts_text}\n\nФинал с самопроверкой:\n{final_text}"
    )
    return ConversationHandler.END

# --- Игнорирование голосовых сообщений ---
async def ignore_voice(update: Update, context: CallbackContext):
    await update.message.reply_text("Голосовые сообщения временно не поддерживаются.")

# --- Просмотр визиток ---
def mycards(update: Update, context: CallbackContext):
    user_json = load_user_json(str(update.message.from_user.id))
    if not user_json or not user_json['drafts']:
        update.message.reply_text("Вы ещё не создавали визитки.")
        return
    text = f"Drafts:\n"
    for i, d in enumerate(user_json['drafts'], 1):
        text += f"{i}. {d[:100]}...\n"
    text += f"\nФинал:\n{user_json['final']}"
    update.message.reply_text(text)

# --- Fallback для активного ConversationHandler ---
def fallback(update: Update, context: CallbackContext):
    update.message.reply_text("Пожалуйста, начните с команды /start")
    return TYPE_PROJECT

# --- Запуск ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
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
            TONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cta_step)],
            CTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_step)],
            GENERATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_step)],
        },
        fallbacks=[MessageHandler(filters.TEXT & ~filters.COMMAND, fallback)]
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.VOICE, ignore_voice))
    app.add_handler(CommandHandler('mycards', mycards))

    app.run_polling()

if __name__ == "__main__":
    main()
