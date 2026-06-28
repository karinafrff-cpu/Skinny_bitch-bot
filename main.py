import os
import requests
import base64
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
from PIL import Image
import io

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_KEY = os.environ["GEMINI_KEY"]
TAVILY_KEY = os.environ["TAVILY_KEY"]

DAILY_CALORIES = 1500
DAILY_PROTEIN = 100
DAILY_FAT = 50
DAILY_CARBS = 150

client = genai.Client(api_key=GEMINI_KEY)

user_diaries = {}

SYSTEM_PROMPT = f"""Ты дружелюбный помощник по дневнику питания.
Дневная норма: {DAILY_CALORIES} ккал, белки {DAILY_PROTEIN}г, жиры {DAILY_FAT}г, углеводы {DAILY_CARBS}г.
Считай КБЖУ, показывай остаток. Отвечай по-русски, коротко.

Формат:
🍽 [что съела]
Калории: Xккал | Б: Xг | Ж: Xг | У: Xг
📊 Осталось: Калории: X | Б: X | Ж: X | У: X"""

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_diaries:
        user_diaries[user_id] = []

    if update.message.text and update.message.text == "/reset":
        user_diaries[user_id] = []
        await update.message.reply_text("✅ Дневник сброшен!")
        return

    history = user_diaries[user_id]

    if update.message.photo:
        photo = await update.message.photo[-1].get_file()
        photo_bytes = await photo.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[SYSTEM_PROMPT + "\n\nЧто на фото? Посчитай КБЖУ.", image]
        )
        reply = response.text
    else:
        text = update.message.text
        search_context = ""
        if any(w in text.lower() for w in ["шоколадница", "макдо", "бургер", "суши", "пицца", "кафе", "ресторан"]):
            search_context = search_nutrition(text)

        full_text = text
        if search_context:
            full_text += "\n\n[Dannye iz interneta: " + search_context + "]"

