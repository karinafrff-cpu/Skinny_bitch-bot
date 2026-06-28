import os
import requests
import base64
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from PIL import Image
import io

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_KEY = os.environ["GEMINI_KEY"]
TAVILY_KEY = os.environ["TAVILY_KEY"]

# Твои параметры — измени под себя!
DAILY_CALORIES = 1500
DAILY_PROTEIN = 100
DAILY_FAT = 50
DAILY_CARBS = 150

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

user_diaries = {}

SYSTEM_PROMPT = f"""Ты дружелюбный помощник по дневнику питания.
Дневная норма пользователя: {DAILY_CALORIES} ккал, белки {DAILY_PROTEIN}г, жиры {DAILY_FAT}г, углеводы {DAILY_CARBS}г.

Когда пользователь описывает еду или отправляет фото:
1. Определи продукты и примерный вес порции
2. Посчитай КБЖУ
3. Покажи сколько осталось до нормы
4. Отвечай по-русски, коротко и дружелюбно

Формат ответа:
🍽 [что съела]
Калории: Xккал | Б: Xг | Ж: Xг | У: Xг

📊 Осталось сегодня:
Калории: X | Б: X | Ж: X | У: X"""

def search_nutrition(query):
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": f"КБЖУ калории {query}", "max_results": 3}
        )
        results = response.json().get("results", [])
        return "\n".join([r["content"][:300] for r in results[:2]])
    except:
        return ""

def build_history(messages):
    """Конвертируем историю в формат Gemini"""
    history = []
    for msg in messages:
        if isinstance(msg["content"], str):
            history.append({
                "role": msg["role"] if msg["role"] == "user" else "model",
                "parts": [msg["content"]]
            })
    return history

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_diaries:
        user_diaries[user_id] = []

    messages = user_diaries[user_id]

    # Сброс дневника
    if update.message.text and update.message.text == "/reset":
        user_diaries[user_id] = []
        await update.message.reply_text("✅ Дневник на сегодня сброшен!")
        return

    # Если фото
    if update.message.photo:
        photo = await update.message.photo[-1].get_file()
        photo_bytes = await photo.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))

        prompt = SYSTEM_PROMPT + "\n\nЧто на фото? Посчитай КБЖУ и обнови дневник."
        response = model.generate_content([prompt, image])
        reply = response.text

    else:
        text = update.message.text

        # Поиск в интернете для ресторанов
        search_context = ""
        if any(word in text.lower() for word in ["шоколадница", "макдonald", "бургер", "суши", "пицца", "кафе", "ресторан"]):
            search_context = search_nutrition(text)

        user_text = text
        if search_context:
            user_text += f"\n\n[Данные из интернета: {search_context}]"

        # Отправляем с историей
        history = build_history(messages)
        chat = model.start_chat(history=history)
        full_prompt = SYSTEM_PROMPT + "\n\n" + user_text if not history else user_text
        response = chat.send_message(full_prompt)
        reply = response.text

        messages.append({"role": "user", "content": text})
        messages.append({"role": "assistant", "content": reply})

    await update.message.reply_text(reply)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
app.run_polling()
