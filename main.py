import os
import json
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler
from google import genai
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from PIL import Image
import io

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_KEY = os.environ["GEMINI_KEY"]
TAVILY_KEY = os.environ["TAVILY_KEY"]
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]
SPREADSHEET_ID = "10OPWVG5zM8M0KllDrJ-EJbwh7U08gqCwk5p-A8UE4V0"

DAILY_CALORIES = 1500
DAILY_PROTEIN = 100
DAILY_FAT = 50
DAILY_CARBS = 150

client = genai.Client(api_key="test")

SYSTEM_PROMPT = (
"You are a friendly nutrition diary assistant. "
"Always respond in Russian language only. "
"Daily norm: 1500 kcal, protein 100g, fat 50g, carbs 150g. "
"When user describes food or sends photo, calculate nutrition. "
"Always include this tag in response: "
"<KBJU>calories,protein,fat,carbs,food description</KBJU> "
"Example: <KBJU>200,6,4,35,oatmeal 200g</KBJU> "
"After the tag write a short friendly message in Russian with remaining daily budget."
)

def parse_kbju(text):
try:
start = text.index("<KBJU>") + 6
end = text.index("</KBJU>")
parts = text[start:end].split(",")
return {
"calories": float(parts[0]),
"protein": float(parts[1]),
"fat": float(parts[2]),
"carbs": float(parts[3]),
"food": parts[4].strip()
}
except Exception:
return None

def save_to_sheets(sheets, kbju):
now = datetime.now()
row = [[
now.strftime(”%Y-%m-%d”),
now.strftime(”%H:%M”),
kbju["food"],
kbju["calories"],
kbju["protein"],
kbju["fat"],
kbju["carbs"]
]]
sheets.values().append(
spreadsheetId=SPREADSHEET_ID,
range="A:G",
valueInputOption="RAW",
body={"values": row}
).execute()

def get_sheet_rows(sheets):
result = sheets.values().get(
spreadsheetId=SPREADSHEET_ID,
range="A2:G1000"
).execute()
return result.get(“values”, [])

async def week_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
try:
creds_dict = json.loads(os.environ[“GOOGLE_CREDENTIALS”])
creds = Credentials.from_service_account_info(creds_dict, scopes=[“https://www.googleapis.com/auth/spreadsheets”])
sheets = build(“sheets”, “v4”, credentials=creds).spreadsheets()
rows = get_sheet_rows(sheets)
week_ago = (datetime.now() - timedelta(days=7)).strftime(”%Y-%m-%d”)
rows = [r for r in rows if len(r) >= 7 and r[0] >= week_ago]
if not rows:
await update.message.reply_text(“За последние 7 дней нет записей!”)
return
total_cal = sum(float(r[3]) for r in rows)
total_p = sum(float(r[4]) for r in rows)
total_f = sum(float(r[5]) for r in rows)
total_c = sum(float(r[6]) for r in rows)
days = len(set(r[0] for r in rows))
msg = (
“\U0001f4ca За 7 дней:\n\n”
“Приёмов пищи: “ + str(len(rows)) + “\n”
“Активных дней: “ + str(days) + “\n\n”
“Итого:\n”
“\U0001f525 Калории: “ + str(round(total_cal)) + “ ккал\n”
“\U0001f357 Белки: “ + str(round(total_p)) + “г\n”
“\U0001f9c8 Жиры: “ + str(round(total_f)) + “г\n”
“\U0001f35e Углеводы: “ + str(round(total_c)) + “г\n\n”
“В среднем в день:\n”
“\U0001f525 “ + str(round(total_cal/days)) + “ ккал | “
“\U0001f357 “ + str(round(total_p/days)) + “г | “
“\U0001f9c8 “ + str(round(total_f/days)) + “г | “
“\U0001f35e “ + str(round(total_c/days)) + “г”
)
await update.message.reply_text(msg)
except Exception as e:
await update.message.reply_text(“Ошибка: “ + str(e))

async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
try:
creds_dict = json.loads(os.environ[“GOOGLE_CREDENTIALS”])
creds = Credentials.from_service_account_info(creds_dict, scopes=[“https://www.googleapis.com/auth/spreadsheets”])
sheets = build(“sheets”, “v4”, credentials=creds).spreadsheets()
rows = get_sheet_rows(sheets)
today = datetime.now().strftime(”%Y-%m-%d”)
rows = [r for r in rows if len(r) >= 7 and r[0] == today]
if not rows:
await update.message.reply_text(“Сегодня ещё нет записей!”)
return
total_cal = sum(float(r[3]) for r in rows)
total_p = sum(float(r[4]) for r in rows)
total_f = sum(float(r[5]) for r in rows)
total_c = sum(float(r[6]) for r in rows)
msg = (
“\U0001f4ca Сегодня съела:\n\n”
“\U0001f525 Калории: “ + str(round(total_cal)) + “ / “ + str(DAILY_CALORIES) + “ ккал\n”
“\U0001f357 Белки: “ + str(round(total_p)) + “ / “ + str(DAILY_PROTEIN) + “г\n”
“\U0001f9c8 Жиры: “ + str(round(total_f)) + “ / “ + str(DAILY_FAT) + “г\n”
“\U0001f35e Углеводы: “ + str(round(total_c)) + “ / “ + str(DAILY_CARBS) + “г\n\n”
“Осталось:\n”
“\U0001f525 “ + str(DAILY_CALORIES - round(total_cal)) + “ ккал | “
“\U0001f357 “ + str(DAILY_PROTEIN - round(total_p)) + “г | “
“\U0001f9c8 “ + str(DAILY_FAT - round(total_f)) + “г | “
“\U0001f35e “ + str(DAILY_CARBS - round(total_c)) + “г”
)
await update.message.reply_text(msg)
except Exception as e:
await update.message.reply_text(“Ошибка: “ + str(e))

def search_nutrition(query):
try:
response = requests.post(
“https://api.tavily.com/search”,
json={“api_key”: os.environ[“TAVILY_KEY”], “query”: “calories nutrition “ + query, “max_results”: 3},
timeout=5
)
results = response.json().get(“results”, [])
return “\n”.join([r[“content”][:300] for r in results[:2]])
except Exception:
return “”

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
ai_client = genai.Client(api_key=os.environ[“GEMINI_KEY”])

```
try:
    if update.message.photo:
        photo = await update.message.photo[-1].get_file()
        photo_bytes = await photo.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[SYSTEM_PROMPT + " What food is in the photo? Calculate nutrition.", image]
        )
    else:
        text = update.message.text
        search_context = ""
        keywords = ["mcdonalds", "burger king", "kfc", "sushi", "pizza", "starbucks"]
        if any(w in text.lower() for w in keywords):
            search_context = search_nutrition(text)
        prompt = SYSTEM_PROMPT + "\n\nUser: " + text
        if search_context:
            prompt += "\n\nSearch data: " + search_context
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )

    reply = response.text
    kbju = parse_kbju(reply)

    if kbju:
        try:
            creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
            sheets = build("sheets", "v4", credentials=creds).spreadsheets()
            save_to_sheets(sheets, kbju)
        except Exception as e:
            print("Sheets error: " + str(e))

        tag_content = reply[reply.find("<KBJU>"):reply.find("</KBJU>") + 7]
        clean_reply = reply.replace(tag_content, "").strip()
        await update.message.reply_text(clean_reply)
    else:
        await update.message.reply_text(reply)

except Exception as e:
    await update.message.reply_text("Произошла ошибка, попробуй ещё раз.")
    print("Error: " + str(e))
```

app = ApplicationBuilder().token(os.environ[“TELEGRAM_TOKEN”]).build()
app.add_handler(CommandHandler(“week”, week_summary))
app.add_handler(CommandHandler(“today”, today_summary))
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
app.run_polling(drop_pending_updates=True)
