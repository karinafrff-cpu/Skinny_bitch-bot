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

# Google Sheets setup
creds_dict = json.loads(GOOGLE_CREDENTIALS)
creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
sheets = build("sheets", "v4", credentials=creds).spreadsheets()

user_diaries = {}

SYSTEM_PROMPT = f"""Ты дружел​​​​​​​​​​​​​​​​
