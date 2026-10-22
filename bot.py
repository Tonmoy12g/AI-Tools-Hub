import os
import requests
import asyncio
import tempfile
import logging
import subprocess
import shutil
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime
from threading import Thread

import edge_tts
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip().strip('"').strip("'")
PORT = int(os.environ.get("PORT", "8080"))

# ---------- মেনু ----------
MENU = {
    "🤖 AI চ্যাট": "chat", "🎙️ ভয়েস বানান": "voice", "🌐 অনুবাদ": "translate",
    "✍️ ক্যাপশন": "caption", "📖 গল্প/কবিতা": "story", "🕌 নামাজের সময়": "prayer",
    "🌦️ আবহাওয়া": "weather", "💱 কারেন্সি রেট": "currency", "📚 অভিধান": "dict",
    "📰 আজকের খবর": "news", "🎂 বয়স হিসাব": "age", "🔐 পাসওয়ার্ড": "password",
    "ℹ️ About": "about", "❓ সাহায্য": "help"
}

def menu_keyboard():
    rows = [[KeyboardButton(a), KeyboardButton(b)] for a, b in zip(list(MENU)[::2], list(MENU)[1::2])]
    rows.append([KeyboardButton("🏠 মেনু")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

MODE = {}
HISTORY = {}
PENDING_TRANS = {}

# ---------- AI (Groq) ----------
def ai_chat(messages, temperature=0.7):
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    # Groq এর সবচেয়ে স্ট্যাবল মডেল ব্যবহার করা হয়েছে
    payload = {"model": "llama3-8b-8192", "messages": messages, "temperature": temperature}
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

def ai_one(system, user):
    return ai_chat([{"role": "system", "content": system}, {"role": "user", "content": user}])

# ---------- হ্যান্ডলার ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = update.effective_user.first_name or "User"
    await update.message.reply_text(
        f"আসসালামু আলাইকুম {name}! 🤖\nআমি একটি AI বট। নিচের মেনু থেকে টুল বেছে নিন 👇",
        reply_markup=menu_keyboard()
    )

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    chat_id = q.message.chat_id
    if data.startswith("tr:"):
        lang = data.split(":")[1]
        PENDING_TRANS[chat_id] = lang
        await q.edit_message_text(f"✅ অনুবাদ ল্যাঙ্গুয়েজ: {lang}\nএবার লেখাটি পাঠান।")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    if text == "🏠 মেনু":
        await update.message.reply_text("মেনু:", reply_markup=menu_keyboard())
        return

    if text in MENU:
        mode = MENU[text]
        MODE[chat_id] = mode
        if mode == "chat": await update.message.reply_text("🤖 আপনার প্রশ্ন লিখুন:")
        elif mode == "voice": await update.message.reply_text("🎙️ আপনার লেখাটি পাঠান (সর্বোচ্চ ৫০০ অক্ষর):")
        elif mode == "translate":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("বাংলা → English", callback_data="tr:en")],
                [InlineKeyboardButton("English → বাংলা", callback_data="tr:bn")]
            ])
            await update.message.reply_text("🌐 কোন দিকে অনুবাদ করবেন?", reply_markup=kb)
        elif mode == "caption": await update.message.reply_text("✍️ ক্যাপশনের বিষয় লিখুন:")
        elif mode == "story": await update.message.reply_text("📖 গল্প/কবিতার বিষয় লিখুন:")
        elif mode == "prayer": await update.message.reply_text("🕌 শহরের নাম লিখুন (English):")
        elif mode == "weather": await update.message.reply_text("🌦️ শহরের নাম লিখুন (English):")
        elif mode == "currency": await update.message.reply_text("💱 ফরম্যাট: 100 USD (বা 50 BDT):")
        elif mode == "dict": await update.message.reply_text("📚 শব্দ লিখুন:")
        elif mode == "age": await update.message.reply_text("🎂 জন্মতারিখ লিখুন (যেমন: 15/08/2009):")
        elif mode == "password":
            import secrets, string
            pw = "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%^&*") for _ in range(14))
            await update.message.reply_text(f"🔐 আপনার পাসওয়ার্ড:\n`{pw}`", parse_mode="Markdown")
            MODE[chat_id] = None
        elif mode == "about":
            await update.message.reply_text("🤖 AI বট — Groq API দ্বারা চালিত।\nসব ফিচার ফ্রি।")
            MODE[chat_id] = None
        elif mode == "help":
            await update.message.reply_text("❓ সাহায্য:\n- যেকোনো বাটনে চাপুন\n- লেখা পাঠান\n- ফলাফল পাবেন")
            MODE[chat_id] = None
        elif mode == "news":
            await update.message.reply_text("📰 খবর আনছি...")
            try:
                r = requests.get("https://news.google.com/rss?hl=bn&gl=BD&ceid=BD:bn", timeout=30)
                root = ET.fromstring(r.content)
                items = root.findall(".//item")[:5]
                news = "📰 আজকের খবর:\n\n" + "\n".join([f"{i+1}. {it.findtext('title')}" for i, it in enumerate(items)])
                await update.message.reply_text(news, disable_web_page_preview=True)
            except Exception:
                await update.message.reply_text("খবর আনতে সমস্যা হয়েছে।")
            MODE[chat_id] = None
        return

    mode = MODE.get(chat_id)
    if not mode:
        await update.message.reply_text("আগে মেনু থেকে টুল বেছে নিন 👇", reply_markup=menu_keyboard())
        return

    if mode == "chat":
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            hist = HISTORY.get(chat_id, [])
            msgs = [{"role": "system", "content": "You are a helpful assistant. Reply in the same language as the user."}] + hist[-6:] + [{"role": "user", "content": text}]
            reply = ai_chat(msgs)
            hist += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
            HISTORY[chat_id] = hist[-10:]
            await update.message.reply_text(reply)
        except Exception as e:
            log.error(f"Chat error: {e}")
            await update.message.reply_text("AI উত্তর দিতে পারছে না। আবার চেষ্টা করুন।")

    elif mode == "voice":
        if len(text) > 500:
            await update.message.reply_text("লেখাটি বড় হয়ে গেছে। ৫০০ অক্ষরের মধ্যে দিন।")
            return
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
        try:
            tts = edge_tts.Communicate(text, "bn-BD-PradeepNeural")
            mp3_path = os.path.join(tempfile.gettempdir(), f"voice_{chat_id}.mp3")
            await tts.save(mp3_path)
            ogg_path = os.path.join(tempfile.gettempdir(), f"voice_{chat_id}.ogg")
            
            # ffmpeg দিয়ে OGG ফরম্যাটে কনভার্ট করা
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                subprocess.run([ffmpeg, "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "32k", ogg_path], check=True, capture_output=True)
                with open(ogg_path, "rb") as f:
                    await update.message.reply_voice(voice=f)
                os.unlink(ogg_path)
            else:
                with open(mp3_path, "rb") as f:
                    await update.message.reply_audio(audio=f, title="Voice")
            
            os.unlink(mp3_path)
        except Exception as e:
            log.error(f"Voice error: {e}")
            await update.message.reply_text("ভয়েস তৈরি করতে সমস্যা হয়েছে।")

    elif mode == "translate":
        lang = PENDING_TRANS.get(chat_id, "en")
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            sys = "Translate to English. Output only translation." if lang == "en" else "Translate to Bangla. Output only translation."
            reply = ai_one(sys, text)
            await update.message.reply_text(reply)
        except Exception:
            await update.message.reply_text("অনুবাদে সমস্যা হয়েছে।")

    elif mode == "caption":
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            reply = ai_one("Write 5 short emotional Bangla captions for social media. Number them.", text)
            await update.message.reply_text(reply)
        except Exception:
            await update.message.reply_text("ক্যাপশন তৈরি করতে সমস্যা হয়েছে।")

    elif mode == "story":
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            reply = ai_one("Write a short Bangla story or poem based on the topic.", text)
            await update.message.reply_text(reply)
        except Exception:
            await update.message.reply_text("গল্প তৈরি করতে সমস্যা হয়েছে।")

    elif mode == "prayer":
        try:
            r = requests.get("https://api.aladhan.com/v1/timingsByCity", params={"city": text, "country": "Bangladesh", "method": 1}, timeout=30)
            t = r.json()["data"]["timings"]
            await update.message.reply_text(f"🕌 {text}:\nফজর: {t['Fajr'][:5]}\nযোহর: {t['Dhuhr'][:5]}\nআসর: {t['Asr'][:5]}\nমাগরিব: {t['Maghrib'][:5]}\nএশা: {t['Isha'][:5]}")
        except Exception:
            await update.message.reply_text("নামাজের সময় আনতে সমস্যা হয়েছে।")

    elif mode == "weather":
        try:
            g = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": text, "count": 1}, timeout=30).json()
            if not g.get("results"):
                await update.message.reply_text("শহর পাওয়া যায়নি।")
                return
            lat, lon = g["results"][0]["latitude"], g["results"][0]["longitude"]
            w = requests.get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code"}, timeout=30).json()
            c = w["current"]
            await update.message.reply_text(f"🌦️ {text}:\nতাপমাত্রা: {c['temperature_2m']}°C\nকোড: {c['weather_code']}")
        except Exception:
            await update.message.reply_text("আবহাওয়া আনতে সমস্যা হয়েছে।")

    elif mode == "currency":
        try:
            parts = text.upper().split()
            amount = float(parts[0])
            src = parts[1] if len(parts) > 1 else "USD"
            dst = parts[2] if len(parts) > 2 else "BDT"
            r = requests.get(f"https://open.er-api.com/v6/latest/{src}", timeout=30).json()
            rate = r["rates"][dst]
            await update.message.reply_text(f"💱 {amount} {src} = {amount * rate:.2f} {dst}")
        except Exception:
            await update.message.reply_text("ফরম্যাট: 100 USD")

    elif mode == "dict":
        try:
            r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{text}", timeout=30)
            if r.ok:
                d = r.json()[0]
                meaning = d["meanings"][0]["definitions"][0]["definition"]
                await update.message.reply_text(f"📚 {d['word']}: {meaning}")
            else:
                reply = ai_one("Give the meaning of the word in simple Bangla.", text)
                await update.message.reply_text(reply)
        except Exception:
            await update.message.reply_text("শব্দের অর্থ আনতে সমস্যা হয়েছে।")

    elif mode == "age":
        try:
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
                try:
                    born = datetime.strptime(text, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                raise ValueError
            today = date.today()
            years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
            await update.message.reply_text(f"🎂 আপনার বয়স: {years} বছর")
        except Exception:
            await update.message.reply_text("ফরম্যাট: 15/08/2009")
    else:
        await update.message.reply_text("কিছু একটা সমস্যা হয়েছে। মেনু থেকে আবার চেষ্টা করুন।", reply_markup=menu_keyboard())

# ---------- Web সার্ভার (Render পোর্টের জন্য) ----------
web = Flask(__name__)
@web.route("/")
def home(): return "Bot is running."

def run_web(): web.run(host="0.0.0.0", port=PORT)

def main():
    if not TOKEN or not GROQ_KEY:
        raise SystemExit("TELEGRAM_BOT_TOKEN and GROQ_API_KEY required")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    Thread(target=run_web, daemon=True).start()
    log.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()