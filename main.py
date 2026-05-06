import os
import telebot
import requests
import time
import threading
from flask import Flask
from PIL import Image
from io import BytesIO
import google.generativeai as genai

# ================== إعدادات ==================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# تحقق من القيم
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN missing")

if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY missing")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro-vision")

app = Flask(__name__)

# ================== حالة المستخدم ==================

user_state = {}

# ================== أوامر ==================

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🤖 البوت يعمل!\nأرسل /haya ثم صورة")

@bot.message_handler(commands=['haya'])
def haya(message):
    user_state[message.chat.id] = "waiting_image"
    bot.reply_to(message, "📸 أرسل الصورة الآن")

# ================== استقبال الصور ==================

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        chat_id = message.chat.id

        if user_state.get(chat_id) != "waiting_image":
            bot.reply_to(message, "❗ أرسل /haya أولاً")
            return

        bot.reply_to(message, "⏳ جاري تحليل الصورة...")

        # تحميل الصورة
        file_info = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        response = requests.get(file_url)

        # تحويل الصورة
        img = Image.open(BytesIO(response.content)).convert("RGB")

        # إرسال إلى Gemini
        result = model.generate_content(
            ["حل هذا التمرين و اشرح بالتفصيل", img]
        )

        # تحقق من الرد
        if not result.text:
            bot.reply_to(message, "❌ لم أستطع تحليل الصورة")
            return

        bot.reply_to(message, result.text)

        user_state[chat_id] = None

    except Exception as e:
        print("ERROR:", e)
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ================== Debug ==================

@bot.message_handler(func=lambda message: True)
def debug(message):
    print("📩 Message received:", message.text)

# ================== Flask ==================

@app.route('/')
def home():
    return "Bot is running"

# ================== تشغيل البوت ==================

def run_bot():
    while True:
        try:
            print("🤖 Bot started polling...")
            bot.infinity_polling(skip_pending=True)
        except Exception as e:
            print("❌ Bot crashed:", e)
            time.sleep(5)

threading.Thread(target=run_bot, daemon=True).start()

# ================== تشغيل السيرفر ==================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
