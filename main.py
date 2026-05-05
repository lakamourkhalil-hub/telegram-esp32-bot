import base64
import json
import logging
import os
import threading
import time

import telebot
from flask import Flask, jsonify, request
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Missing environment variables")

client = OpenAI(api_key=OPENAI_API_KEY)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

# -----------------------------
# STATE
# -----------------------------
lock = threading.Lock()
user_data = {}

def new_user():
    return {
        "prompt": "",
        "ready": False,
        "cards": [],
    }

# -----------------------------
# HELPERS
# -----------------------------
def to_data_url(image_bytes):
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:image/jpeg;base64,{b64}"

def split_text(text, limit=200):
    return [text[i:i+limit] for i in range(0, len(text), limit)]

# -----------------------------
# OPENAI
# -----------------------------
def analyze_image(prompt, image_bytes):
    try:
        img = to_data_url(image_bytes)

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": img},
                    ],
                }
            ],
        )

        return response.output_text

    except Exception as e:
        logger.error(e)
        return f"Error: {e}"

# -----------------------------
# TELEGRAM
# -----------------------------
@bot.message_handler(commands=["start"])
def start(msg):
    user_data[msg.chat.id] = new_user()
    bot.reply_to(msg, "Send prompt")

@bot.message_handler(commands=["haya"])
def haya(msg):
    state = user_data.get(msg.chat.id)

    if not state or not state["prompt"]:
        bot.reply_to(msg, "Send prompt first")
        return

    state["ready"] = True
    bot.reply_to(msg, "Send images")

@bot.message_handler(content_types=["text"])
def handle_text(msg):
    if msg.text.startswith("/"):
        return

    state = user_data.setdefault(msg.chat.id, new_user())

    if not state["ready"]:
        state["prompt"] = msg.text
        bot.reply_to(msg, "Saved. Send /haya")
    else:
        bot.reply_to(msg, "Send image")

@bot.message_handler(content_types=["photo"])
def handle_photo(msg):
    state = user_data.get(msg.chat.id)

    if not state or not state["ready"]:
        bot.reply_to(msg, "Send /haya first")
        return

    try:
        file_info = bot.get_file(msg.photo[-1].file_id)
        image_bytes = bot.download_file(file_info.file_path)

        answer = analyze_image(state["prompt"], image_bytes)

        pages = split_text(answer)

        state["cards"].append(pages)

        for p in pages:
            bot.send_message(msg.chat.id, p)

    except Exception as e:
        bot.send_message(msg.chat.id, f"Error: {e}")

# -----------------------------
# API (ESP32)
# -----------------------------
@app.route("/")
def home():
    return "Server is working"

@app.route("/get")
def get_data():
    if not user_data:
        return jsonify([])

    uid = list(user_data.keys())[0]
    return jsonify(user_data[uid]["cards"])

@app.route("/clear", methods=["POST"])
def clear():
    if not user_data:
        return jsonify({"cleared": 0})

    uid = list(user_data.keys())[0]
    count = len(user_data[uid]["cards"])
    user_data[uid]["cards"] = []
    return jsonify({"cleared": count})

# -----------------------------
# RUN
# -----------------------------
def run_bot():
    while True:
        try:
            logger.info("Bot polling...")
            bot.infinity_polling(skip_pending=True)
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            time.sleep(5)

# مهم لـ Render (gunicorn)
if __name__ != "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

# تشغيل محلي
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=3000)
