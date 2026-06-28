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

client = genai.Client(api_key=GEMINI_KEY)

creds_dict = json.loads(GOOGLE_CREDENTIALS)
creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
sheets = build("sheets", "v4", credentials=creds).spreadsheets()

user_diaries = {}

SYSTEM_PROMPT = (
    "Ty druzhelyubny pomoshchnik po dnevniku pitaniya. "
    "Dnevnaya norma: 1500 kkal, belki 100g, zhiry 50g, uglevody 150g. "
    "Kogda polzovatel opisyvaet edu ili prisylaet foto poschitay KBZHU. "
    "Otvechay po-russki kratko i druzhelyubno. "
    "Format otveta: "
    "<KBJU>kalorii,belki,zhiry,uglevody,opisanie edy</KBJU> "
    "Primer: <KBJU>350,25,8,40,ovsyanka 200g s bananom</KBJU> "
    "Posle tega napishi kratkiy druzhelyubny otvet s ostatkom na den."
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
    except:
        return None

def save_to_sheets(kbju):
    now = datetime.now()
    row = [[
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
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

def get_week_data():
    result = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="A2:G1000"
    ).execute()
    rows = result.get("values", [])
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return [r for r in rows if len(r) >= 7 and r[0] >= week_ago]

def get_today_data():
    result = sheets.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="A2:G1000"
    ).execute()
    rows = result.get("values", [])
    today = datetime.now().strftime("%Y-%m-%d")
    return [r for r in rows if len(r) >= 7 and r[0] == today]

async def week_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_week_data()
    if not rows:
        await update.message.reply_text("Net zapisey za 7 dney!")
        return
    total_cal = sum(float(r[3]) for r in rows)
    total_p = sum(float(r[4]) for r in rows)
    total_f = sum(float(r[5]) for r in rows)
    total_c = sum(float(r[6]) for r in rows)
    days = len(set(r[0] for r in rows))
    reply = (
        "Svodka za 7 dney:\n\n"
        "Vsego priemov pishchi: " + str(len(rows)) + "\n"
        "Aktivnykh dney: " + str(days) + "\n\n"
        "Itogo:\n"
        "Kalorii: " + str(round(total_cal)) + " kkal\n"
        "Belki: " + str(round(total_p)) + "g\n"
        "Zhiry: " + str(round(total_f)) + "g\n"
        "Uglevody: " + str(round(total_c)) + "g\n\n"
        "V srednem v den:\n"
        "Kalorii: " + str(round(total_cal/days)) + " kkal\n"
        "Belki: " + str(round(total_p/days)) + "g\n"
        "Zhiry: " + str(round(total_f/days)) + "g\n"
        "Uglevody: " + str(round(total_c/days)) + "g"
    )
    await update.message.reply_text(reply)

async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_today_data()
    if not rows:
        await update.message.reply_text("Segodnya eshche net zapisey!")
        return
    total_cal = sum(float(r[3]) for r in rows)
    total_p = sum(float(r[4]) for r in rows)
    total_f = sum(float(r[5]) for r in rows)
    total_c = sum(float(r[6]) for r in rows)
    reply = (
        "Segodnya:\n\n"
        "Kalorii: " + str(round(total_cal)) + " / 1500 kkal\n"
        "Belki: " + str(round(total_p)) + " / 100g\n"
        "Zhiry: " + str(round(total_f)) + " / 50g\n"
        "Uglevody: " + str(round(total_c)) + " / 150g\n\n"
        "Ostalos:\n"
        "Kalorii: " + str(1500 - round(total_cal)) + " kkal\n"
        "Belki: " + str(100 - round(total_p)) + "g\n"
        "Zhiry: " + str(50 - round(total_f)) + "g\n"
        "Uglevody: " + str(150 - round(total_c)) + "g"
    )
    await update.message.reply_text(reply)

def search_nutrition(query):
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": "KBZHU kalorii " + query, "max_results": 3}
        )
        results = response.json().get("results", [])
        return "\n".join([r["content"][:300] for r in results[:2]])
    except:
        return ""

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_diaries:
        user_diaries[user_id] = []

    history = user_diaries[user_id]

    if update.message.photo:
        photo = await update.message.photo[-1].get_file()
        photo_bytes = await photo.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[SYSTEM_PROMPT, image]
        )
        reply = response.text
    else:
        text = update.message.text
        search_context = ""
        if any(w in text.lower() for w in ["shokoladnitsa", "makdo", "burger", "sushi", "pizza", "kafe", "restoran"]):
            search_context = search_nutrition(text)

        full_text = text
        if search_context:
            full_text = text + "\n\n[Search data: " + search_context + "]"

        if not history:
            history.append({"role": "user", "parts": [SYSTEM_PROMPT + "\n\n" + full_text]})
        else:
            history.append({"role": "user", "parts": [full_text]})

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=history
        )
        reply = response.text
        history.append({"role": "model", "parts": [reply]})

    kbju = parse_kbju(reply)
    if kbju:
        save_to_sheets(kbju)
        clean_reply = reply.replace("<KBJU>" + reply[reply.find("<KBJU>")+6:reply.find("</KBJU>")] + "</KBJU>", "").strip()
        await update.message.reply_text(clean_reply)
    else:
        await update.message.reply_text(reply)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("week", week_summary))
app.add_handler(CommandHandler("today", today_summary))
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
app.run_polling(drop_pending_updates=True)
