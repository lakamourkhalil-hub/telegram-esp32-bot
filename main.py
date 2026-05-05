import base64
import json
import logging
import os
import threading
import time

import telebot
from flask import Flask, jsonify, request
import google.generativeai as genai

# -----------------------------
# Configuration
# -----------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"].strip()
HTTP_PORT = int(os.environ.get("PORT", "10000"))

# Gemini setup
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

OLED_PAGE_CHARS = 220
TELEGRAM_CHUNK = 3500

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

lock = threading.RLock()
user_data = {}
active_uid = None


def new_state():
    return {
        "prompt": "",
        "ready": False,
        "cards": [],
        "status": "idle",
    }


def activate_user(uid):
    global active_uid
    with lock:
        if uid not in user_data:
            user_data[uid] = new_state()
        active_uid = uid
        return user_data[uid]


def split_chunks(text, limit=TELEGRAM_CHUNK):
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def split_for_screen(text, limit=OLED_PAGE_CHARS):
    words = text.split()
    pages = []
    current = ""

    for w in words:
        if len(current) + len(w) + 1 <= limit:
            current += " " + w
        else:
            pages.append(current.strip())
            current = w

    if current:
        pages.append(current.strip())

    return pages


def analyze_image(prompt, image_bytes):
    try:
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])

        text = response.text.strip()
        pages = split_for_screen(text)

        return [{
            "label": "Answer",
            "pages": pages
        }]

    except Exception as e:
        return [{"label": "Error", "pages": [str(e)]}]


def send_cards(chat_id, cards):
    for i, card in enumerate(cards, 1):
        text = f"{i}. {card['label']}\n"
        for j, p in enumerate(card["pages"], 1):
            text += f"{j}) {p}\n"

        for chunk in split_chunks(text):
            bot.send_message(chat_id, chunk)


# -----------------------------
# Telegram
# -----------------------------
@bot.message_handler(commands=["start"])
def start(msg):
    user_data[msg.chat.id] = new_state()
    bot.reply_to(msg, "Send your prompt")


@bot.message_handler(commands=["haya"])
def haya(msg):
    state = activate_user(msg.chat.id)

    if not state["prompt"]:
        bot.reply_to(msg, "Send prompt first")
        return

    state["ready"] = True
    bot.reply_to(msg, "Send image now")


@bot.message_handler(content_types=["text"])
def text(msg):
    if msg.text.startswith("/"):
        return

    state = activate_user(msg.chat.id)
    state["prompt"] = msg.text
    bot.reply_to(msg, "Saved. Send /haya")


@bot.message_handler(content_types=["photo"])
def photo(msg):
    state = activate_user(msg.chat.id)

    if not state["ready"]:
        bot.reply_to(msg, "Send /haya first")
        return

    file_info = bot.get_file(msg.photo[-1].file_id)
    image_bytes = bot.download_file(file_info.file_path)

    bot.send_chat_action(msg.chat.id, "typing")

    cards = analyze_image(state["prompt"], image_bytes)
    state["cards"] = cards

    send_cards(msg.chat.id, cards)


# -----------------------------
# HTTP API
# -----------------------------
@app.route("/")
def home():
    return "Server is working"


@app.route("/get")
def get_data():
    uid = active_uid
    if uid is None:
        return jsonify({"cards": []})

    return jsonify(user_data.get(uid, {}))


def run_http():
    app.run(host="0.0.0.0", port=HTTP_PORT)


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    threading.Thread(target=run_http).start()
    bot.infinity_polling()
