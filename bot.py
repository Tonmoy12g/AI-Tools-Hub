"""Telegram BIG All-in-One AI Bot v2 (free stack).
Updated: Groq Model fixed, yt-dlp updated.
"""

import asyncio
import hashlib
import io
import logging
import os
import random
import re
import secrets
import shutil
import sqlite3
import string
import subprocess
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime
from threading import Thread

import edge_tts
import requests
from flask import Flask
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tg-big-ai-bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "").strip().strip('"').strip("'")
# --- মডেল নাম আপডেট করা হয়েছে ---
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b").strip()
PORT = int(os.environ.get("PORT", "8080"))
PREMIUM_MODE = os.environ.get("PREMIUM_MODE", "off").strip().lower() == "on"
FORCE_JOIN = os.environ.get("FORCE_JOIN", "").strip()
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_CHAT_ID", "").replace(" ", "").split(",")
    if x.isdigit()
}
DEVELOPER_URL = "https://t.me/Tonmoy581833"
DEVELOPER_TAG = "@Tonmoy581833"
MAX_VOICE_CHARS = 800
PREMIUM_TOOLS = {"download"}
REF_POINTS = 10
BOT_USERNAME = {"name": ""}  # filled at startup

VOICES = {
    "bn_f": ("🇧🇩 বাংলা — মহিলা কণ্ঠ", "bn-BD-NabanitaNeural"),
    "bn_m": ("🇧🇩 বাংলা — পুরুষ কণ্ঠ", "bn-BD-PradeepNeural"),
    "en_f": ("🇬🇧 English — Female", "en-US-AriaNeural"),
}

MENU = {
    "🤖 AI চ্যাট": "chat", "🎙️ Voice বানান": "voice",
    "🎤 Voice → Text": "stt", "🖼️ AI ছবি": "image",
    "📥 ভিডিও ডাউনলোড": "download", "🌐 অনুবাদ": "translate_pick",
    "✍️ Caption": "caption", "📖 গল্প/কবিতা": "story",
    "📄 ছবি → PDF": "imgpdf", "🕌 নামাজের সময়": "prayer",
    "🌦️ আবহাওয়া": "weather", "💱 কারেন্সি রেট": "currency",
    "🔗 লিংক ছোট": "shorten", "📚 শব্দের অর্থ": "dict",
    "😂 জোকস": "fun", "🧮 BMI": "bmi",
    "📝 PDF সারাংশ": "pdfsum", "🔲 QR মেকার": "qr",
    "📰 আজকের খবর": "news", "📈 ক্রিপ্টোর দাম": "crypto",
    "🎂 বয়স হিসাব": "age", "📏 কনভার্টার": "unit",
    "✍️ ফ্যান্সি টেক্সট": "fancy", "💘 লাভ ক্যালকুলেটর": "love",
    "📸 ছবি কমপ্রেস": "compress", "🎵 লিরিক্স": "lyrics",
    "🔐 পাসওয়ার্ড": "password", "🕌 আজকের দোয়া": "dua",
    "⏰ রিমাইন্ডার": "reminder", "🎮 কুইজ গেম": "quiz",
    "⭐ আমার প্রোফাইল": "profile", "🏆 লিডারবোর্ড": "leaderboard",
    "🎁 ডেইলি বোনাস": "daily", "🎰 স্পিন": "spin",
    "🎁 রেফার": "refer", "🛒 দোকান": "shop",
    "📩 Contact Admin": "contact",
    "ℹ️ About": "about", "❓ সাহায্য": "help", "👨‍💻 Developer": "developer",
}
MODE_NAMES = {
    "chat": "🤖 AI চ্যাট", "voice": "🎙️ Voice Maker", "stt": "🎤 Voice → Text",
    "image": "🖼️ AI ছবি", "download": "📥 ভিডিও ডাউনলোড",
    "tr_bn_en": "🌐 অনুবাদ (বাংলা → English)", "tr_en_bn": "🌐 অনুবাদ (English → বাংলা)",
    "caption": "✍️ Caption মেকার", "story": "📖 গল্প/কবিতা", "imgpdf": "📄 ছবি → PDF",
    "prayer": "🕌 নামাজের সময়", "weather": "🌦️ আবহাওয়া", "currency": "💱 কারেন্সি রেট",
    "shorten": "🔗 লিংক ছোট", "dict": "📚 শব্দের অর্থ", "fun": "😂 জোকস",
    "bmi": "🧮 BMI", "pdfsum": "📝 PDF সারাংশ", "qr": "🔲 QR মেকার",
    "news": "📰 আজকের খবর", "crypto": "📈 ক্রিপ্টোর দাম", "age": "🎂 বয়স হিসাব",
    "unit": "📏 কনভার্টার", "fancy": "✍️ ফ্যান্সি টেক্সট", "love": "💘 লাভ ক্যালকুলেটর",
    "compress": "📸 ছবি কমপ্রেস", "lyrics": "🎵 লিরিক্স", "password": "🔐 পাসওয়ার্ড",
    "dua": "🕌 আজকের দোয়া", "reminder": "⏰ রিমাইন্ডার", "quiz": "🎮 কুইজ গেম",
    "shop": "🛒 দোকান", "contact": "📩 Contact Admin",
}

MODE = {}
USER_VOICE = {}
HISTORY = {}
PENDING_PHOTOS = {}
PENDING_COMPRESS = {}
QUIZ = {}
ORDER_STATE = {}
FORWARD_MAP = {}
WAITING_BROADCAST = set()

# ---------------- SQLite store ----------------
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bigbot.db")

def db():
    return sqlite3.connect(DB_PATH)

def db_init():
    con = db()
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY, first_seen TEXT, name TEXT,
        points INTEGER DEFAULT 0, week_points INTEGER DEFAULT 0, week_key TEXT,
        referred_by INTEGER, last_daily TEXT, last_spin TEXT,
        premium INTEGER DEFAULT 0, banned INTEGER DEFAULT 0)""")
    con.execute("CREATE TABLE IF NOT EXISTS stats (k TEXT PRIMARY KEY, v INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT)")
    con.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price TEXT, desc TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, product TEXT,
        details TEXT, ts TEXT)""")
    con.commit()
    con.close()

def week_key_now():
    y, w, _ = date.today().isocalendar()
    return f"{y}-{w}"

def db_add_user(chat_id, name="", referred_by=None):
    con = db()
    cur = con.execute("SELECT chat_id FROM users WHERE chat_id = ?", (chat_id,))
    is_new = cur.fetchone() is None
    con.execute(
        "INSERT OR IGNORE INTO users (chat_id, first_seen, name, referred_by, week_key) VALUES (?, ?, ?, ?, ?)",
        (chat_id, datetime.now().isoformat(timespec="seconds"), name, referred_by, week_key_now()))
    if name:
        con.execute("UPDATE users SET name = ? WHERE chat_id = ?", (name, chat_id))
    con.commit()
    con.close()
    if is_new and referred_by and referred_by != chat_id:
        add_points(referred_by, REF_POINTS, weekly=True)
        return referred_by
    return None

def add_points(chat_id, pts, weekly=False):
    con = db()
    wk = week_key_now()
    con.execute("UPDATE users SET points = points + ? WHERE chat_id = ?", (pts, chat_id))
    row = con.execute("SELECT week_key FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    if row and row[0] != wk:
        con.execute("UPDATE users SET week_points = 0, week_key = ? WHERE chat_id = ?", (wk, chat_id))
    con.execute("UPDATE users SET week_points = week_points + ? WHERE chat_id = ?", (pts, chat_id))
    con.commit()
    con.close()

def db_points(chat_id):
    con = db()
    row = con.execute("SELECT points FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    con.close()
    return row[0] if row else 0

def level_of(points):
    if points >= 400: return "💎 Diamond"
    if points >= 150: return "🥇 Gold"
    if points >= 50: return "🥈 Silver"
    return "🥉 Bronze"

def db_rank(chat_id):
    pts = db_points(chat_id)
    con = db()
    n = con.execute("SELECT COUNT(*) FROM users WHERE points > ?", (pts,)).fetchone()[0]
    con.close()
    return n + 1

def db_top(weekly=False):
    col = "week_points" if weekly else "points"
    con = db()
    rows = con.execute(f"SELECT chat_id, name, {col} FROM users WHERE {col} > 0 ORDER BY {col} DESC LIMIT 10").fetchall()
    con.close()
    return rows

def db_ref_count(chat_id):
    con = db()
    n = con.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (chat_id,)).fetchone()[0]
    con.close()
    return n

def db_users():
    con = db()
    ids = [r[0] for r in con.execute("SELECT chat_id FROM users")]
    con.close()
    return ids

def db_flag(chat_id, col):
    con = db()
    row = con.execute(f"SELECT {col} FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    con.close()
    return bool(row and row[0])

def db_set(chat_id, col, val):
    con = db()
    con.execute(f"UPDATE users SET {col} = ? WHERE chat_id = ?", (val, chat_id))
    con.commit()
    con.close()

def db_setting(key, default=""):
    con = db()
    row = con.execute("SELECT v FROM settings WHERE k = ?", (key,)).fetchone()
    con.close()
    return row[0] if row else default

def db_set_setting(key, val):
    con = db()
    con.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (key, val))
    con.commit()
    con.close()

def db_bump(key):
    con = db()
    con.execute("INSERT INTO stats VALUES (?, 1) ON CONFLICT(k) DO UPDATE SET v = v + 1", (key,))
    con.commit()
    con.close()

def db_get(key):
    con = db()
    row = con.execute("SELECT v FROM stats WHERE k = ?", (key,)).fetchone()
    con.close()
    return row[0] if row else 0

def bump(chat_id, key, points=1):
    db_bump(key)
    if points:
        add_points(chat_id, points)

# ---------------- keyboards / texts ----------------
MENU_ROWS = [
    ("🤖 AI চ্যাট", "🎙️ Voice বানান"),
    ("🎤 Voice → Text", "🖼️ AI ছবি"),
    ("📥 ভিডিও ডাউনলোড", "🌐 অনুবাদ"),
    ("✍️ Caption", "📖 গল্প/কবিতা"),
    ("📄 ছবি → PDF", "📝 PDF সারাংশ"),
    ("🕌 নামাজের সময়", "🌦️ আবহাওয়া"),
    ("💱 কারেন্সি রেট", "🔗 লিংক ছোট"),
    ("📚 শব্দের অর্থ", "🧮 BMI"),
    ("🔲 QR মেকার", "📰 আজকের খবর"),
    ("📈 ক্রিপ্টোর দাম", "🎂 বয়স হিসাব"),
    ("📏 কনভার্টার", "✍️ ফ্যান্সি টেক্সট"),
    ("💘 লাভ ক্যালকুলেটর", "📸 ছবি কমপ্রেস"),
    ("🎵 লিরিক্স", "🔐 পাসওয়ার্ড"),
    ("🕌 আজকের দোয়া", "⏰ রিমাইন্ডার"),
    ("🎮 কুইজ গেম", "🎰 স্পিন"),
    ("⭐ আমার প্রোফাইল", "🏆 লিডারবোর্ড"),
    ("🎁 ডেইলি বোনাস", "🎁 রেফার"),
    ("🛒 দোকান", "📩 Contact Admin"),
    ("ℹ️ About", "❓ সাহায্য"),
    ("👨‍💻 Developer", "🏠 মেনু"),
]

def menu_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(a), KeyboardButton(b)] for a, b in MENU_ROWS],
        resize_keyboard=True,
    )

def voice_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"v:{key}")]
         for key, (label, _) in VOICES.items()])

def translate_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("বাংলা → English", callback_data="mode:tr_bn_en")],
        [InlineKeyboardButton("English → বাংলা", callback_data="mode:tr_en_bn")],
    ])

def pdf_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ PDF বানান", callback_data="pdf:make"),
         InlineKeyboardButton("🗑️ সব মুছুন", callback_data="pdf:clear")],
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="admin:stats"),
         InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast")],
        [InlineKeyboardButton("📢 চ্যানেল (Force Join)", callback_data="admin:channel"),
         InlineKeyboardButton("🔧 Maintenance", callback_data="admin:maint")],
    ])

def force_join_channel():
    return db_setting("force_join") or FORCE_JOIN

WELCOME = (
    "আসসালামু আলাইকুম! 🤖\n"
    "**BIG AI Bot — সব AI টুল এক জায়গায়!**\n\n"
    "নিচের মেনু থেকে টুল বেছে নিন 👇\n"
    "সব টুল সম্পূর্ণ ফ্রি! টুল ব্যবহারে পয়েন্টও পাবেন ⭐"
)
ABOUT = (
    "ℹ️ **BIG AI Bot — সব বাটনের কাজ**\n\n"
    "🤖 AI চ্যাট — যেকোনো প্রশ্নের উত্তর\n"
    "🎙️ Voice বানান — লেখা থেকে ভয়েস\n"
    "🎤 Voice → Text — ভয়েস থেকে লেখা\n"
    "🖼️ AI ছবি — লেখা থেকে ছবি\n"
    "📥 ভিডিও ডাউনলোড — TikTok/YouTube লিংক থেকে ভিডিও\n"
    "🌐 অনুবাদ — বাংলা ↔ English\n"
    "✍️ Caption — বিষয় দিলে ৫টা ক্যাপশন\n"
    "📖 গল্প/কবিতা — বিষয় দিলে গল্প/কবিতা\n"
    "📄 ছবি → PDF — ছবি থেকে PDF\n"
    "📝 PDF সারাংশ — PDF-এর সারাংশ\n"
    "🕌 নামাজের সময় — শহর অনুযায়ী ওয়াক্ত\n"
    "🌦️ আবহাওয়া — শহরের আবহাওয়া\n"
    "💱 কারেন্সি রেট — টাকাসহ যেকোনো মুদ্রা\n"
    "🔗 লিংক ছোট — লম্বা লিংক ছোট করা\n"
    "📚 শব্দের অর্থ — অভিধান\n"
    "😂 জোকস — জোকস ও মোটিভেশন\n"
    "🧮 BMI — ওজন-উচ্চতার হিসাব\n"
    "🔲 QR মেকার — লিংক/লেখার QR কোড\n"
    "📰 আজকের খবর — প্রধান শিরোনাম\n"
    "📈 ক্রিপ্টোর দাম — Bitcoin ইত্যাদির দাম\n"
    "🎂 বয়স হিসাব — জন্মতারিখ থেকে বয়স\n"
    "📏 কনভার্টার — একক বদলানো\n"
    "✍️ ফ্যান্সি টেক্সট — স্টাইলিশ লেখা\n"
    "💘 লাভ ক্যালকুলেটর — দুই নামের %\n"
    "📸 ছবি কমপ্রেস — ছবির সাইজ কমানো\n"
    "🎵 লিরিক্স — গানের লিরিক্স খোঁজা\n"
    "🔐 পাসওয়ার্ড — শক্তিশালী পাসওয়ার্ড বানানো\n"
    "🕌 আজকের দোয়া — প্রতিদিনের দোয়া\n"
    "⏰ রিমাইন্ডার — সময়মতো মনে করিয়ে দেওয়া\n"
    "🎮 কুইজ গেম — প্রশ্নের উত্তরে পয়েন্ট\n"
    "⭐ প্রোফাইল • 🏆 লিডারবোর্ড • 🎁 বোনাস/রেফার/স্পিন — পয়েন্ট সিস্টেম\n"
    "🛒 দোকান — পণ্য কিনুন\n"
    "📩 Contact Admin — অ্যাডমিনকে মেসেজ\n\n"
    f"👨‍💻 Developer: {DEVELOPER_TAG}"
)
HELP = (
    "❓ **কীভাবে ব্যবহার করবেন**\n\n"
    "১. নিচের মেনু থেকে টুলের বাটন চাপুন\n"
    "২. যা চায় (লেখা/ছবি/ভয়েস/লিংক) পাঠান\n"
    "৩. ফলাফল পেয়ে যাবেন ✅\n\n"
    "⭐ টুল ব্যবহারে, কুইজে, রেফারে পয়েন্ট পাবেন — পয়েন্টে লেভেল আর লিডারবোর্ড!\n"
    "কমান্ড: /start /myid"
)

MODE_PROMPTS = {
    "chat": "🤖 **AI চ্যাট** — যেকোনো প্রশ্ন লিখে পাঠান 👇",
    "voice": "🎙️ **Voice Maker** — কণ্ঠ বেছে নিয়ে লেখা পাঠান 👇",
    "stt": "🎤 **Voice → Text** — একটা ভয়েস মেসেজ পাঠান 👇",
    "image": "🖼️ **AI ছবি** — ছবির বর্ণনা পাঠান (English-এ ভালো হয়) 👇",
    "download": "📥 **ভিডিও ডাউনলোড** — TikTok/YouTube/Facebook লিংক পাঠান 👇",
    "tr_bn_en": "🌐 **বাংলা → English** — বাংলা লেখা পাঠান 👇",
    "tr_en_bn": "🌐 **English → বাংলা** — English লেখা পাঠান 👇",
    "caption": "✍️ **Caption মেকার** — বিষয় পাঠান 👇",
    "story": "📖 **গল্প/কবিতা** — বিষয় পাঠান 👇",
    "imgpdf": "📄 **ছবি → PDF** — ছবিগুলো পাঠান, শেষে ✅ PDF বানান চাপুন 👇",
    "prayer": "🕌 **নামাজের সময়** — শহরের নাম (English) পাঠান, যেমন: Dhaka 👇",
    "weather": "🌦️ **আবহাওয়া** — শহরের নাম (English) পাঠান, যেমন: Khulna 👇",
    "currency": "💱 **কারেন্সি রেট** — এভাবে পাঠান: 100 USD 👇",
    "shorten": "🔗 **লিংক ছোট** — লম্বা লিংক পাঠান 👇",
    "dict": "📚 **শব্দের অর্থ** — যেকোনো শব্দ পাঠান 👇",
    "fun": "😂 **জোকস** — 'hi' লিখলেই জোকস + মোটিভেশন 👇",
    "bmi": "🧮 **BMI** — এভাবে পাঠান: 70 5.7 (ওজন kg, উচ্চতা feet) 👇",
    "pdfsum": "📝 **PDF সারাংশ** — একটা PDF ফাইল পাঠান 👇",
    "qr": "🔲 **QR মেকার** — লিংক বা লেখা পাঠান, QR ছবি বানিয়ে দেব 👇",
    "news": "📰 **আজকের খবর** — 'খবর' লিখলেই আজকের প্রধান শিরোনাম 👇",
    "crypto": "📈 **ক্রিপ্টোর দাম** — কয়েনের নাম পাঠান: bitcoin / ethereum 👇",
    "age": "🎂 **বয়স হিসাব** — জন্মতারিখ পাঠান এভাবে: 15/08/2009 👇",
    "unit": "📏 **কনভার্টার** — এভাবে পাঠান: 10 kg to pound / 5 km to mile / 37 c to f 👇",
    "fancy": "✍️ **ফ্যান্সি টেক্সট** — আপনার নাম/লেখা পাঠান, স্টাইলিশ বানিয়ে দেব 👇",
    "love": "💘 **লাভ ক্যালকুলেটর** — দুটো নাম পাঠান এভাবে: Rahim + Karima 👇",
    "compress": "📸 **ছবি কমপ্রেস** — একটা ছবি পাঠান, সাইজ কমিয়ে ফেরত দেব 👇",
    "lyrics": "🎵 **লিরিক্স** — গানের নাম পাঠান 👇",
    "password": "🔐 **পাসওয়ার্ড** — 'password' লিখলেই শক্তিশালী পাসওয়ার্ড বানিয়ে দেব 👇",
    "dua": "🕌 **আজকের দোয়া** — 'দোয়া' লিখলেই আজকের দোয়া পাবেন 👇",
    "reminder": "⏰ **রিমাইন্ডার** — এভাবে পাঠান: 10 মিনিট পর পানি খাব / 1 ঘণ্টা পর পড়তে বসব 👇",
    "quiz": "🎮 **কুইজ গেম** — 'start' লিখলেই প্রশ্ন আসবে। সঠিক উত্তরে +৫ পয়েন্ট! 👇",
    "shop": "🛒 **দোকান** — পণ্যের তালিকা দেখতে 'list' লিখুন 👇",
    "contact": "📩 **Contact Admin** — আপনার মেসেজটা লিখে পাঠান, অ্যাডমিনের কাছে পৌঁছে যাবে 👇",
}

DUAS = [
    ("رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ",
     "হে আমাদের রব! আমাদের দুনিয়াতে কল্যাণ দিন, আখিরাতেও কল্যাণ দিন এবং জাহান্নামের আযাব থেকে রক্ষা করুন। (বাকারা: ২০১)"),
    ("رَبِّ اشْرَحْ لِي صَدْرِي وَيَسِّرْ لِي أَمْرِي",
     "হে আমার রব! আমার বুক প্রশস্ত করে দিন এবং আমার কাজ সহজ করে দিন। (ত্বহা: ২৫-২৬)"),
    ("حَسْبُنَا اللَّهُ وَنِعْمَ الْوَكِيلُ",
     "আল্লাহই আমাদের জন্য যথেষ্ট এবং তিনি উত্তম কর্মবিধায়ক। (আলে ইমরান: ১৭৩)"),
    ("رَبِّ زِدْنِي عِلْمًا",
     "হে আমার রব! আমার জ্ঞান বাড়িয়ে দিন। (ত্বহা: ১১৪)"),
    ("اللَّهُمَّ إِنِّي أَسْأَلُكَ عِلْمًا نَافِعًا وَرِزْقًا طَيِّبًا وَعَمَلًا مُتَقَبَّلًا",
     "হে আল্লাহ! আমি আপনার কাছে উপকারী জ্ঞান, পবিত্র রিযিক ও কবুলযোগ্য আমল চাই। (ইবনে মাজাহ)"),
    ("رَبَّنَا اغْفِرْ لَنَا ذُنُوبَنَا وَإِسْرَافَنَا فِي أَمْرِنَا",
     "হে আমাদের রব! আমাদের গুনাহ ও বাড়াবাড়ি মাফ করে দিন। (আলে ইমরান: ১৪৭)"),
    ("اللَّهُمَّ أَعِنِّي عَلَى ذِكْرِكَ وَشُكْرِكَ وَحُسْنِ عِبَادَتِكَ",
     "হে আল্লাহ! আপনার যিকির, শুকরিয়া ও সুন্দর ইবাদতে আমাকে সাহায্য করুন। (আবু দাউদ)"),
]

# ---------------- engines ----------------
def groq_chat(messages, temperature=0.7):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "temperature": temperature},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

def groq_one(system, user, temperature=0.7):
    return groq_chat([{"role": "system", "content": system},
                      {"role": "user", "content": user}], temperature)

def ai_reply(chat_id, text):
    hist = HISTORY.setdefault(chat_id, [])
    msgs = [{"role": "system", "content": (
        "You are a friendly AI assistant on Telegram. Answer any question clearly. "
        "Reply in the same language the user wrote in. Keep answers reasonably short "
        "unless asked for details. If unsure, say so honestly."
    )}] + hist[-16:] + [{"role": "user", "content": text}]
    reply = groq_chat(msgs)
    hist += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    HISTORY[chat_id] = hist[-16:]
    return reply

def stt_transcribe(file_path):
    with open(file_path, "rb") as fh:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("voice.ogg", fh, "audio/ogg")},
            data={"model": "whisper-large-v3"},
            timeout=120,
        )
    r.raise_for_status()
    return r.json().get("text", "").strip()

def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")

def _to_ogg(mp3_path, out_ogg):
    ff = _ffmpeg()
    if ff:
        subprocess.run([ff, "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "32k", out_ogg],
                       check=True, capture_output=True)
        return out_ogg
    return mp3_path

async def make_voice(text, voice, out_ogg):
    last_err = None
    for _ in range(3):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            mp3_path = f.name
        try:
            await edge_tts.Communicate(text, voice).save(mp3_path)
            if os.path.getsize(mp3_path) == 0:
                raise RuntimeError("empty audio")
            return _to_ogg(mp3_path, out_ogg)
        except Exception as e:
            last_err = e
            try: os.unlink(mp3_path)
            except OSError: pass
            await asyncio.sleep(1.5)
    from gtts import gTTS
    lang = "bn" if voice.startswith("bn") else "en"
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    await asyncio.to_thread(gTTS(text, lang=lang).save, mp3_path)
    return _to_ogg(mp3_path, out_ogg)

def make_image(prompt):
    q = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{q}?width=1024&height=1024&nologo=true"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content

def download_video(url):
    import yt_dlp
    tmpdir = tempfile.mkdtemp()
    opts = {
        "outtmpl": os.path.join(tmpdir, "v.%(ext)s"),
        "format": "bv*[filesize<46M]+ba/b[filesize<46M]/bv*+ba/b",
        "merge_output_format": "mp4",
        "quiet": True, "no_warnings": True, "socket_timeout": 30,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    for name in os.listdir(tmpdir):
        p = os.path.join(tmpdir, name)
        if os.path.isfile(p):
            return p
    raise RuntimeError("no file")

def prayer_times(city):
    r = requests.get("https://api.aladhan.com/v1/timingsByCity",
                     params={"city": city, "country": "Bangladesh", "method": 1}, timeout=30)
    r.raise_for_status()
    t = r.json()["data"]["timings"]
    keys = [("Fajr", "ফজর"), ("Sunrise", "সূর্যোদয়"), ("Dhuhr", "যোহর"),
            ("Asr", "আসর"), ("Maghrib", "মাগরিব"), ("Isha", "এশা")]
    lines = [f"🕌 **{city} — আজকের নামাজের সময়**\n"]
    for k, bn in keys:
        lines.append(f"{bn}: {t[k][:5]}")
    return "\n".join(lines)

WEATHER_CODES = {
    0: "পরিষ্কার আকাশ ☀️", 1: "প্রায় পরিষ্কার 🌤️", 2: "আংশিক মেঘলা ⛅",
    3: "মেঘলা ☁️", 45: "কুয়াশা 🌫️", 48: "কুয়াশা 🌫️",
    51: "হালকা বৃষ্টি 🌦️", 53: "বৃষ্টি 🌧️", 55: "বৃষ্টি 🌧️", 61: "হালকা বৃষ্টি 🌦️",
    63: "বৃষ্টি 🌧️", 65: "ভারী বৃষ্টি 🌧️", 80: "বৃষ্টি 🌦️", 81: "বৃষ্টি 🌧️",
    82: "ভারী বৃষ্টি 🌧️", 95: "বজ্রসহ বৃষ্টি ⛈️",
}

def weather_now(city):
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": city, "count": 1}, timeout=30)
    g.raise_for_status()
    res = g.json().get("results")
    if not res: raise RuntimeError("city not found")
    lat, lon, name = res[0]["latitude"], res[0]["longitude"], res[0]["name"]
    w = requests.get("https://api.open-meteo.com/v1/forecast",
                     params={"latitude": lat, "longitude": lon,
                             "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"},
                     timeout=30)
    w.raise_for_status()
    c = w.json()["current"]
    return (f"🌦️ **{name} — এখনকার আবহাওয়া**\n\n"
            f"🌡️ তাপমাত্রা: {c['temperature_2m']}°C\n"
            f"🌤️ অবস্থা: {WEATHER_CODES.get(c['weather_code'], '—')}\n"
            f"💧 আর্দ্রতা: {c['relative_humidity_2m']}%\n"
            f"💨 বাতাস: {c['wind_speed_10m']} km/h")

def currency_convert(text):
    m = re.match(r"\s*([\d.,]+)\s*([A-Za-z]{3})(?:\s*(?:to|in|=)?\s*([A-Za-z]{3}))?\s*$", text, re.I)
    if not m: raise RuntimeError("format")
    amount = float(m.group(1).replace(",", ""))
    src = m.group(2).upper()
    dst = (m.group(3) or "BDT").upper()
    r = requests.get(f"https://open.er-api.com/v6/latest/{src}", timeout=30)
    r.raise_for_status()
    rate = r.json()["rates"][dst]
    return f"💱 **{amount:,.2f} {src} = {amount * rate:,.2f} {dst}**\n(রেট: 1 {src} = {rate:,.4f} {dst})"

def shorten_url(url):
    r = requests.get("https://is.gd/create.php", params={"format": "simple", "url": url}, timeout=30)
    r.raise_for_status()
    return r.text.strip()

def dictionary_lookup(word):
    if word.isascii():
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}", timeout=30)
        if r.ok:
            data = r.json()[0]
            out = [f"📚 **{data['word']}**"]
            for meaning in data.get("meanings", [])[:2]:
                for d in meaning.get("definitions", [])[:2]:
                    out.append(f"• ({meaning['partOfSpeech']}) {d['definition']}")
            return "\n".join(out)
    return groq_one("Give a short, clear meaning of the user's word. If English, explain in "
                    "simple Bangla with an example. If Bangla, give meaning + English word.", word, 0.4)

def make_qr(data):
    import qrcode
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def top_news():
    r = requests.get("https://news.google.com/rss?hl=bn&gl=BD&ceid=BD:bn", timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = root.findall(".//item")[:8]
    out = ["📰 **আজকের প্রধান খবর**\n"]
    for i, it in enumerate(items, 1):
        title = it.findtext("title") or ""
        link = it.findtext("link") or ""
        out.append(f"{i}. [{title}]({link})")
    return "\n".join(out)

def crypto_price(coin):
    ids = {"bitcoin": "bitcoin", "btc": "bitcoin", "ethereum": "ethereum", "eth": "ethereum",
           "bnb": "binancecoin", "doge": "dogecoin", "dogecoin": "dogecoin",
           "xrp": "ripple", "sol": "solana", "solana": "solana"}
    cid = ids.get(coin.strip().lower())
    if not cid: return "এই কয়েনটা পাইনি। চেষ্টা করুন: bitcoin, ethereum, bnb, doge, xrp, solana"
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": cid, "vs_currencies": "usd"}, timeout=30)
    r.raise_for_status()
    usd = r.json()[cid]["usd"]
    bdt = ""
    try:
        rr = requests.get("https://open.er-api.com/v6/latest/USD", timeout=20)
        bdt = f"\n💵 টাকায়: ৳{usd * rr.json()['rates']['BDT']:,.0f}"
    except Exception: pass
    return f"📈 **{cid.title()}**\n💲 দাম: ${usd:,.2f}{bdt}"

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

def to_en_digits(s):
    return s.translate(BN_DIGITS)

def age_calc(text):
    t = to_en_digits(text.strip())
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            born = datetime.strptime(t, fmt).date()
            break
        except ValueError: continue
    else: raise RuntimeError("format")
    today = date.today()
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    months = (today.year - born.year) * 12 + today.month - born.month - (1 if today.day < born.day else 0)
    days = (today - born).days
    return (f"🎂 আপনার বয়স: **{years} বছর**\n"
            f"📅 মোট: {months} মাস / {days} দিন\n"
            f"🎉 জন্মদিন: {born.strftime('%d %B %Y')}")

UNIT_RULES = [
    (r"kg", "pound", 2.20462, "kg", "পাউন্ড"), (r"pound|lb", "kg", 0.453592, "পাউন্ড", "kg"),
    (r"km", "mile", 0.621371, "km", "মাইল"), (r"mile", "km", 1.60934, "মাইল", "km"),
    (r"c", "f", None, "°C", "°F"), (r"f", "c", None, "°F", "°C"),
    (r"inch|inchi", "cm", 2.54, "ইঞ্চি", "cm"), (r"cm", "inch", 0.393701, "cm", "ইঞ্চি"),
    (r"liter|litre|l", "gallon", 0.264172, "লিটার", "গ্যালন"),
    (r"gallon", "liter", 3.78541, "গ্যালন", "লিটার"),
]

def unit_convert(text):
    t = to_en_digits(text.lower())
    m = re.match(r"\s*([\d.]+)\s*([a-z]+)\s*(?:to|→|=)?\s*([a-z]+)\s*$", t)
    if not m: raise RuntimeError("format")
    val, src, dst = float(m.group(1)), m.group(2), m.group(3)
    for sp, dp, factor, sn, dn in UNIT_RULES:
        if re.fullmatch(sp, src) and re.fullmatch(dp, dst):
            if factor is None:
                res = val * 9 / 5 + 32 if src == "c" else (val - 32) * 5 / 9
            else:
                res = val * factor
            return f"📏 **{val:g} {sn} = {res:,.3f} {dn}**"
    raise RuntimeError("pair not supported")

_FANCY_BASE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_FANCY_STYLES = [
    dict(zip(_FANCY_BASE, "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗")),
    dict(zip(_FANCY_BASE, "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵")),
    dict(zip(_FANCY_BASE, "𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵0123456789")),
]

def fancy_text(text):
    out = ["✍️ **ফ্যান্সি টেক্সট:**\n"]
    for i, style in enumerate(_FANCY_STYLES, 1):
        out.append(f"{i}. " + "".join(style.get(ch, ch) for ch in text))
    return "\n".join(out)

def love_calc(text):
    parts = re.split(r"\+|&|,| এবং ", text)
    if len(parts) < 2: raise RuntimeError("format")
    a, b = parts[0].strip().lower(), parts[1].strip().lower()
    h = int(hashlib.md5((a + "❤" + b).encode()).hexdigest(), 16)
    pct = 40 + h % 61
    line = ("অসাধারণ জুটি! 💞" if pct >= 85 else "খুব ভালো মিল! 💕" if pct >= 70
            else "মোটামুটি মিল 💛" if pct >= 55 else "চেষ্টা করলে হবে! 🌱")
    return f"💘 **{parts[0].strip()} + {parts[1].strip()}**\n\n❤️ মিল: **{pct}%**\n{line}"

def gen_password():
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(chars) for _ in range(14))

def gen_quiz():
    import json
    raw = groq_one(
        "Create ONE general-knowledge quiz question in Bangla for Bangladeshi users. "
        "Reply ONLY with JSON: {\"q\": \"...\", \"options\": [\"..\",\"..\",\"..\",\"..\"], \"answer\": 0} "
        "where answer is the index (0-3) of the correct option. No other text.",
        "new question", 0.8)
    raw = raw.strip().strip("`")
    if raw.startswith("json"): raw = raw[4:]
    data = json.loads(raw)
    assert len(data["options"]) == 4 and 0 <= data["answer"] <= 3
    return data

def parse_reminder(text):
    t = to_en_digits(text)
    m = re.search(r"(\d+)\s*(মিনিট|minute|min|ঘণ্টা|ঘন্টা|hour|hr|সেকেন্ড|second|sec)", t, re.I)
    if not m: return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit in ("ঘণ্টা", "ঘন্টা", "hour", "hr"): secs = n * 3600
    elif unit in ("সেকেন্ড", "second", "sec"): secs = n
    else: secs = n * 60
    note = (t[:m.start()] + t[m.end():]).replace("পর", "").strip(" :-") or "সময় হয়েছে!"
    return secs, note

# ---------------- guards / helpers ----------------
def blocked(update) -> bool:
    uid = update.effective_user.id if update.effective_user else 0
    cid = update.effective_chat.id if update.effective_chat else 0
    if uid in ADMIN_IDS: return False
    if db_flag(cid, "banned"): return True
    if db_setting("maintenance") == "on": return True
    return False

async def guard_reply(update):
    uid = update.effective_user.id if update.effective_user else 0
    if uid in ADMIN_IDS: return False
    cid = update.effective_chat.id
    if db_flag(cid, "banned"): return True
    if db_setting("maintenance") == "on":
        await update.message.reply_text("🔧 বট এখন আপডেট হচ্ছে — একটু পরে আবার চেষ্টা করুন।")
        return True
    fj = force_join_channel()
    if fj:
        try:
            member = await update.get_bot().get_chat_member(fj, uid)
            if member.status in ("left", "kicked"):
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 চ্যানেলে জয়েন করুন", url=f"https://t.me/{fj.lstrip('@')}")],
                    [InlineKeyboardButton("✅ জয়েন করেছি", callback_data="fj:check")],
                ])
                await update.message.reply_text(
                    "বট ব্যবহার করতে আগে আমাদের চ্যানেলে জয়েন করুন 👇", reply_markup=kb)
                return True
        except Exception as e:
            log.warning("force join check failed: %s", e)
    return False

def ref_link(chat_id):
    return f"https://t.me/{BOT_USERNAME['name']}?start=ref_{chat_id}"

async def send_long(update, text):
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i + 4000])

# ---------------- command handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = update.effective_user.first_name or ""
    ref_by = None
    if context.args and context.args[0].startswith("ref_"):
        try: ref_by = int(context.args[0][4:])
        except ValueError: ref_by = None
    referrer = db_add_user(chat_id, name, referred_by=ref_by)
    if await guard_reply(update): return
    if referrer:
        try:
            await context.bot.send_message(referrer, f"🎉 আপনার রেফার লিংকে নতুন ব্যবহারকারী এসেছে! +{REF_POINTS} পয়েন্ট পেয়েছেন ⭐")
        except Exception: pass
    await update.message.reply_text(WELCOME, reply_markup=menu_keyboard(), parse_mode="Markdown")

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"আপনার Telegram ID: `{update.effective_user.id}`", parse_mode="Markdown")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_text("🛠️ **Admin Panel**", reply_markup=admin_keyboard(), parse_mode="Markdown")

async def admin_text_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return False
    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=2)
    cmd = parts[0].lower()
    if cmd == "/premium" and len(parts) == 3 and parts[1].isdigit() and parts[2] in ("on", "off"):
        db_add_user(int(parts[1]))
        db_set(int(parts[1]), "premium", 1 if parts[2] == "on" else 0)
        await update.message.reply_text(f"✅ {parts[1]}-এর প্রিমিয়াম {parts[2]} হলো।")
        return True
    if cmd == "/ban" and len(parts) >= 2 and parts[1].isdigit():
        db_add_user(int(parts[1]))
        db_set(int(parts[1]), "banned", 1)
        await update.message.reply_text(f"🚫 {parts[1]} ব্যান হয়েছে।")
        return True
    if cmd == "/unban" and len(parts) >= 2 and parts[1].isdigit():
        db_set(int(parts[1]), "banned", 0)
        await update.message.reply_text(f"✅ {parts[1]}-এর ব্যান উঠল।")
        return True
    if cmd == "/setchannel":
        val = text.split(None, 1)[1].strip() if len(text.split(None, 1)) > 1 else ""
        if val.lower() == "off" or not val:
            db_set_setting("force_join", "")
            await update.message.reply_text("📢 Force Join বন্ধ হলো।")
        else:
            if not val.startswith("@"): val = "@" + val
            db_set_setting("force_join", val)
            await update.message.reply_text(f"📢 Force Join চ্যানেল সেট হলো: {val}\n⚠️ বটকে ওই চ্যানেলের **Admin** বানাতে ভুলবেন না — নইলে জয়েন যাচাই হবে না।", parse_mode="Markdown")
        return True
    if cmd == "/channel":
        cur = force_join_channel()
        await update.message.reply_text(f"📢 বর্তমান Force Join চ্যানেল: {cur or 'বন্ধ (off)'}")
        return True
    if cmd == "/maintenance" and len(parts) >= 2 and parts[1] in ("on", "off"):
        db_set_setting("maintenance", parts[1])
        await update.message.reply_text(f"🔧 Maintenance {parts[1]} হলো।")
        return True
    if cmd == "/addproduct" and len(parts) == 3:
        seg = text.split(None, 1)[1] if len(parts) > 1 else ""
        bits = [b.strip() for b in seg.split("|")]
        if len(bits) >= 2:
            con = db()
            con.execute("INSERT INTO products (name, price, desc) VALUES (?, ?, ?)", (bits[0], bits[1], bits[2] if len(bits) > 2 else ""))
            con.commit(); con.close()
            await update.message.reply_text(f"🛒 পণ্য যোগ হলো: {bits[0]} — {bits[1]}")
            return True
    if cmd == "/delproduct" and len(parts) >= 2 and parts[1].isdigit():
        con = db()
        con.execute("DELETE FROM products WHERE id = ?", (int(parts[1]),))
        con.commit(); con.close()
        await update.message.reply_text("🗑️ পণ্য মোছা হলো।")
        return True
    return False

# ---------------- callbacks ----------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    chat_id = q.message.chat_id
    if data == "fj:check":
        await q.edit_message_text("✅ ধন্যবাদ! এখন নিচের মেনু থেকে টুল বেছে নিন 👇")
        await context.bot.send_message(chat_id, WELCOME, reply_markup=menu_keyboard(), parse_mode="Markdown")
        return
    if data.startswith("mode:"):
        MODE[chat_id] = data.split(":", 1)[1]
        await q.edit_message_text(MODE_PROMPTS[MODE[chat_id]], parse_mode="Markdown")
    elif data.startswith("v:"):
        key = data.split(":", 1)[1]
        if key in VOICES:
            USER_VOICE[chat_id] = key
            await q.edit_message_text(f"✅ কণ্ঠ: {VOICES[key][0]}\nএবার লেখা পাঠান!")
    elif data.startswith("quiz:"):
        st = QUIZ.get(chat_id)
        if not st:
            await q.edit_message_text("কুইজ শেষ। আবার খেলতে 🎮 কুইজ গেম চাপুন!")
            return
        pick = int(data.split(":", 1)[1])
        if pick == st["answer"]:
            streak = st.get("streak", 0) + 1
            pts = 5 + (2 if streak % 3 == 0 else 0)
            QUIZ[chat_id] = {"answer": -1, "streak": streak}
            add_points(chat_id, pts)
            db_bump("quiz")
            await q.edit_message_text(f"✅ সঠিক উত্তর! +{pts} পয়েন্ট ⭐ (স্ট্রিক: {streak})\nপরের প্রশ্নের জন্য 'next' লিখুন!")
        else:
            QUIZ[chat_id] = {"answer": -1, "streak": 0}
            await q.edit_message_text("❌ ভুল উত্তর! স্ট্রিক শেষ। আবার খেলতে 'start' লিখুন!")
    elif data == "pdf:make":
        paths = PENDING_PHOTOS.get(chat_id) or []
        if not paths:
            await q.edit_message_text("আগে ছবি পাঠান!")
            return
        await make_pdf_and_send(q, chat_id, paths)
    elif data == "pdf:clear":
        for p in PENDING_PHOTOS.pop(chat_id, []):
            try: os.unlink(p)
            except OSError: pass
        await q.edit_message_text("🗑️ ছবি মোছা হলো। আবার ছবি পাঠান!")
    elif data.startswith("buy:"):
        pid = int(data.split(":", 1)[1])
        con = db()
        row = con.execute("SELECT name, price FROM products WHERE id = ?", (pid,)).fetchone()
        con.close()
        if row:
            ORDER_STATE[chat_id] = f"{row[0]} — {row[1]}"
            await q.edit_message_text(f"🛒 অর্ডার: **{row[0]}** ({row[1]})\n\nআপনার **নাম, ফোন নম্বর আর ঠিকানা** এক মেসেজে পাঠান 👇", parse_mode="Markdown")
    elif data == "admin:stats":
        if q.from_user.id not in ADMIN_IDS: return
        keys = ["chat", "voices", "stt", "images", "download", "quiz", "pdf", "orders"]
        lines = [f"👥 ব্যবহারকারী: {len(db_users())}", f"⭐ প্রিমিয়াম মোড: {'ON' if PREMIUM_MODE else 'OFF'}"]
        lines += [f"{k}: {db_get(k)}" for k in keys]
        await q.edit_message_text("📊 **Bot Stats**\n\n" + "\n".join(lines), reply_markup=admin_keyboard(), parse_mode="Markdown")
    elif data == "admin:broadcast":
        if q.from_user.id not in ADMIN_IDS: return
        WAITING_BROADCAST.add(chat_id)
        await q.edit_message_text("📢 ব্রডকাস্টের মেসেজটা লিখে পাঠান:")
    elif data == "admin:channel":
        if q.from_user.id not in ADMIN_IDS: return
        cur = force_join_channel()
        await q.edit_message_text(f"📢 **Force Join চ্যানেল**\n\nবর্তমান: {cur or 'বন্ধ (off)'}\n\nবদলাতে পাঠান: `/setchannel @YourChannel`\nবন্ধ করতে: `/setchannel off`\n\n⚠️ বটকে ওই চ্যানেলের Admin বানাতে হবে।", reply_markup=admin_keyboard(), parse_mode="Markdown")
    elif data == "admin:maint":
        if q.from_user.id not in ADMIN_IDS: return
        cur = db_setting("maintenance") or "off"
        new = "off" if cur == "on" else "on"
        db_set_setting("maintenance", new)
        await q.edit_message_text(f"🔧 Maintenance এখন: **{new}**", reply_markup=admin_keyboard(), parse_mode="Markdown")

async def make_pdf_and_send(src, chat_id, paths):
    from PIL import Image
    def build():
        imgs = [Image.open(p).convert("RGB") for p in paths]
        buf = io.BytesIO()
        imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:])
        buf.seek(0)
        return buf
    buf = await asyncio.to_thread(build)
    await src.message.reply_document(document=buf, filename="images.pdf", caption="📄 আপনার PDF!")
    for p in paths:
        try: os.unlink(p)
        except OSError: pass
    PENDING_PHOTOS[chat_id] = []
    bump(chat_id, "pdf")

# ---------------- media handlers ----------------
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db_add_user(chat_id, update.effective_user.first_name or "")
    if blocked(update): return
    mode = MODE.get(chat_id)
    photo = update.message.photo[-1]
    f = await context.bot.get_file(photo.file_id)
    if mode == "imgpdf":
        path = os.path.join(tempfile.gettempdir(), f"img_{chat_id}_{photo.file_unique_id}.jpg")
        await f.download_to_drive(path)
        PENDING_PHOTOS.setdefault(chat_id, []).append(path)
        await update.message.reply_text(f"✅ ছবি যোগ হয়েছে ({len(PENDING_PHOTOS[chat_id])}টা)। আরও পাঠান, নাহলে:", reply_markup=pdf_keyboard())
    elif mode == "compress":
        path = os.path.join(tempfile.gettempdir(), f"cmp_{chat_id}.jpg")
        await f.download_to_drive(path)
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        def shrink():
            from PIL import Image
            im = Image.open(path).convert("RGB")
            out = os.path.join(tempfile.gettempdir(), f"cmp_{chat_id}_small.jpg")
            im.save(out, format="JPEG", quality=45, optimize=True)
            return out
        out = await asyncio.to_thread(shrink)
        with open(out, "rb") as fh:
            await update.message.reply_document(document=fh, filename="compressed.jpg", caption="📸 কমপ্রেস করা ছবি!")
        bump(chat_id, "compress")
        for p in (path, out):
            try: os.unlink(p)
            except OSError: pass
    else:
        await update.message.reply_text("ছবি পেয়েছি! কাজের জন্য আগে মেনু থেকে টুল বাছুন 👇", reply_markup=menu_keyboard())

async def on_voice_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db_add_user(chat_id, update.effective_user.first_name or "")
    if blocked(update): return
    if MODE.get(chat_id) != "stt":
        await update.message.reply_text("ভয়েস পেয়েছি! লেখা বানাতে 🎤 Voice → Text বাটন চাপুন।", reply_markup=menu_keyboard())
        return
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    f = await context.bot.get_file(update.message.voice.file_id)
    path = os.path.join(tempfile.gettempdir(), f"stt_{chat_id}.ogg")
    await f.download_to_drive(path)
    try:
        text = await asyncio.to_thread(stt_transcribe, path)
        await update.message.reply_text(f"📝 **আপনার ভয়েসের লেখা:**\n\n{text or '(কিছু শোনা যায়নি)'}", parse_mode="Markdown")
        bump(chat_id, "stt")
    except Exception as e:
        log.error("STT error: %s", e)
        await update.message.reply_text("দুঃখিত, ভয়েসটা লেখায় বদলাতে পারলাম না। 🙏")
    finally:
        try: os.unlink(path)
        except OSError: pass

async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db_add_user(chat_id, update.effective_user.first_name or "")
    if blocked(update): return
    doc = update.message.document
    if MODE.get(chat_id) == "imgpdf" and doc.mime_type and doc.mime_type.startswith("image/"):
        f = await context.bot.get_file(doc.file_id)
        path = os.path.join(tempfile.gettempdir(), f"img_{chat_id}_{doc.file_unique_id}.bin")
        await f.download_to_drive(path)
        PENDING_PHOTOS.setdefault(chat_id, []).append(path)
        await update.message.reply_text(f"✅ ছবি যোগ হয়েছে ({len(PENDING_PHOTOS[chat_id])}টা)।", reply_markup=pdf_keyboard())
        return
    if not (doc.file_name or "").lower().endswith(".pdf"): return
    if MODE.get(chat_id) != "pdfsum":
        await update.message.reply_text("PDF পেয়েছি! সারাংশ পেতে 📝 PDF সারাংশ বাটন চাপুন।", reply_markup=menu_keyboard())
        return
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    f = await context.bot.get_file(doc.file_id)
    path = os.path.join(tempfile.gettempdir(), f"doc_{chat_id}.pdf")
    await f.download_to_drive(path)
    try:
        def extract():
            from pypdf import PdfReader
            r = PdfReader(path)
            return "\n".join((p.extract_text() or "") for p in r.pages)[:12000]
        text = await asyncio.to_thread(extract)
        if not text.strip():
            await update.message.reply_text("এই PDF থেকে লেখা পাওয়া যায়নি।")
            return
        summary = await asyncio.to_thread(groq_one, "Summarize the user's PDF text in clear Bangla: 3-4 line summary, then main points as bullets.", text, 0.4)
        await send_long(update, summary)
        bump(chat_id, "pdf")
    except Exception as e:
        log.error("PDF error: %s", e)
        await update.message.reply_text("দুঃখিত, PDF-টা পড়তে সমস্যা হয়েছে। 🙏")
    finally:
        try: os.unlink(path)
        except OSError: pass

def profile_text(chat_id, name):
    pts = db_points(chat_id)
    con = db()
    row = con.execute("SELECT week_points FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    con.close()
    wk = row[0] if row else 0
    return (f"⭐ **আপনার প্রোফাইল**\n\n"
            f"👤 নাম: {name}\n"
            f"⭐ পয়েন্ট: {pts} (এই সপ্তাহে: {wk})\n"
            f"🏅 লেভেল: {level_of(pts)}\n"
            f"🏆 র‍্যাংক: {db_rank(chat_id)}\n"
            f"🎁 রেফার: {db_ref_count(chat_id)} জন\n"
            f"🔗 রেফার লিংক:\n{ref_link(chat_id)}\n\n"
            f"বন্ধুদের লিংক পাঠান — প্রতি রেফারে +{REF_POINTS} পয়েন্ট!")

def leaderboard_text(chat_id):
    medals = ["🥇", "🥈", "🥉"]
    out = ["🏆 **লিডারবোর্ড — সেরা ১০ (সর্বকাল)**\n"]
    for i, (_, name, pts) in enumerate(db_top()):
        out.append(f"{medals[i] if i < 3 else f'{i + 1}.'} {name or 'User'} — {pts} ⭐")
    out.append("\n📅 **এই সপ্তাহের সেরা:**")
    for i, (_, name, pts) in enumerate(db_top(weekly=True)):
        out.append(f"{medals[i] if i < 3 else f'{i + 1}.'} {name or 'User'} — {pts} ⭐")
    out.append(f"\n⭐ আপনার পয়েন্ট: {db_points(chat_id)} (র‍্যাংক: {db_rank(chat_id)})")
    return "\n".join(out)

async def shop_list(update):
    con = db()
    rows = con.execute("SELECT id, name, price, desc FROM products ORDER BY id").fetchall()
    con.close()
    if not rows:
        await update.message.reply_text("🛒 দোকানে এখনো পণ্য যোগ হয়নি। শীঘ্রই আসছে!")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"{n} — {p}", callback_data=f"buy:{i}")] for i, n, p, _ in rows])
    txt = "🛒 **পণ্যের তালিকা**\n\n" + "\n".join(f"• {n} — {p}" + (f"\n  {d}" if d else "") for _, n, p, d in rows)
    await update.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(job.chat_id, f"⏰ **রিমাইন্ডার:** {job.data}", parse_mode="Markdown")

async def start_quiz(update, chat_id):
    await update.message.reply_text("🎮 প্রশ্ন আসছে...")
    try:
        data = await asyncio.to_thread(gen_quiz)
    except Exception as e:
        log.error("quiz gen failed: %s", e)
        await update.message.reply_text("এখন কুইজ লোড হচ্ছে না, একটু পরে চেষ্টা করুন। 🙏")
        return
    prev = QUIZ.get(chat_id, {})
    QUIZ[chat_id] = {"answer": data["answer"], "streak": prev.get("streak", 0)}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(opt[:60], callback_data=f"quiz:{i}")] for i, opt in enumerate(data["options"])])
    await update.message.reply_text(f"🎮 **কুইজ:**\n\n{data['q']}", reply_markup=kb, parse_mode="Markdown")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    name = update.effective_user.first_name or ""
    text = update.message.text.strip()
    db_add_user(chat_id, name)

    if user_id in ADMIN_IDS and update.message.reply_to_message:
        key = (chat_id, update.message.reply_to_message.message_id)
        if key in FORWARD_MAP:
            target = FORWARD_MAP.pop(key)
            await context.bot.send_message(target, f"📩 **Admin-এর উত্তর:**\n\n{text}", parse_mode="Markdown")
            await update.message.reply_text("✅ উত্তর পাঠানো হয়েছে।")
            return

    if user_id in ADMIN_IDS and text.startswith("/"):
        if await admin_text_cmd(update, context): return

    if blocked(update):
        await guard_reply(update)
        return

    if user_id in ADMIN_IDS and chat_id in WAITING_BROADCAST:
        WAITING_BROADCAST.discard(chat_id)
        sent = failed = 0
        for uid in db_users():
            try:
                await context.bot.send_message(uid, text)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
        await update.message.reply_text(f"📢 ব্রডকাস্ট শেষ!\n✅ {sent} ❌ {failed}")
        return

    if chat_id in ORDER_STATE:
        product = ORDER_STATE.pop(chat_id)
        con = db()
        con.execute("INSERT INTO orders (chat_id, product, details, ts) VALUES (?, ?, ?, ?)", (chat_id, product, text, datetime.now().isoformat(timespec="seconds")))
        con.commit(); con.close()
        db_bump("orders")
        await update.message.reply_text("✅ **অর্ডার পেয়েছি!** শীঘ্রই যোগাযোগ করা হবে। ধন্যবাদ! 🛒", parse_mode="Markdown")
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(aid, f"🛒 **নতুন অর্ডার!**\nপণ্য: {product}\nক্রেতা: {name} ({chat_id})\nতথ্য: {text}")
            except Exception: pass
        return

    if MODE.get(chat_id) == "contact":
        MODE[chat_id] = None
        for aid in ADMIN_IDS:
            try:
                hdr = await context.bot.send_message(aid, f"📩 **নতুন মেসেজ** — {name} ({chat_id}):")
                fwd = await context.bot.forward_message(aid, chat_id, update.message.message_id)
                FORWARD_MAP[(aid, fwd.message_id)] = chat_id
                FORWARD_MAP[(aid, hdr.message_id)] = chat_id
            except Exception: pass
        await update.message.reply_text("✅ মেসেজ পাঠানো হয়েছে! Admin উত্তর দিলে এখানেই পাবেন।")
        return

    if text in MENU or text == "🏠 মেনু":
        if text == "🏠 মেনু":
            await update.message.reply_text(WELCOME, reply_markup=menu_keyboard(), parse_mode="Markdown")
            return
        mode = MENU[text]
        if await guard_reply(update): return
        if mode == "about": await update.message.reply_text(ABOUT, parse_mode="Markdown")
        elif mode == "help": await update.message.reply_text(HELP, parse_mode="Markdown")
        elif mode == "developer": await update.message.reply_text(f"👨‍💻 **Developer**\n\nযোগাযোগ: {DEVELOPER_TAG}\n{DEVELOPER_URL}", parse_mode="Markdown")
        elif mode == "profile": await update.message.reply_text(profile_text(chat_id, name), parse_mode="Markdown")
        elif mode == "leaderboard": await update.message.reply_text(leaderboard_text(chat_id), parse_mode="Markdown")
        elif mode == "daily":
            con = db()
            row = con.execute("SELECT last_daily FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
            con.close()
            today = date.today().isoformat()
            if row and row[0] == today:
                await update.message.reply_text("🎁 আজকের বোনাস ইতিমধ্যে নিয়েছেন! কাল আবার আসুন।")
            else:
                db_set(chat_id, "last_daily", today)
                add_points(chat_id, 5)
                await update.message.reply_text("🎁 **ডেইলি বোনাস +৫ পয়েন্ট!** ⭐ কাল আবার নিন।")
        elif mode == "spin":
            con = db()
            row = con.execute("SELECT last_spin FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
            con.close()
            today = date.today().isoformat()
            if row and row[0] == today:
                await update.message.reply_text("🎰 আজকের স্পিন শেষ! কাল আবার চেষ্টা করুন।")
            else:
                prize = random.choice([1, 2, 3, 5, 5, 5, 10, 10, 20, 50])
                db_set(chat_id, "last_spin", today)
                add_points(chat_id, prize)
                await update.message.reply_text(f"🎰 স্পিন! আপনি পেয়েছেন **+{prize} পয়েন্ট!** ⭐", parse_mode="Markdown")
        elif mode == "refer":
            await update.message.reply_text(f"🎁 **আপনার রেফার লিংক:**\n{ref_link(chat_id)}\n\nবন্ধুরা এই লিংকে বট চালু করলেই আপনি পাবেন +{REF_POINTS} পয়েন্ট করে! মোট রেফার: {db_ref_count(chat_id)} জন", parse_mode="Markdown")
        elif mode == "shop":
            MODE[chat_id] = "shop"
            await shop_list(update)
        elif mode == "quiz":
            MODE[chat_id] = "quiz"
            await start_quiz(update, chat_id)
        elif mode == "password":
            await update.message.reply_text(f"🔐 আপনার শক্তিশালী পাসওয়ার্ড:\n`{gen_password()}`", parse_mode="Markdown")
            bump(chat_id, "password")
        elif mode == "dua":
            ar, bn = DUAS[date.today().toordinal() % len(DUAS)]
            await update.message.reply_text(f"🕌 **আজকের দোয়া**\n\n{ar}\n\n{bn}")
            bump(chat_id, "dua")
        elif mode == "news":
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            try:
                await update.message.reply_text(await asyncio.to_thread(top_news), parse_mode="Markdown", disable_web_page_preview=True)
                bump(chat_id, "news")
            except Exception:
                await update.message.reply_text("এখন খবর লোড হচ্ছে না, পরে চেষ্টা করুন। 🙏")
        elif mode == "translate_pick":
            await update.message.reply_text("🌐 কোন অনুবাদ চান?", reply_markup=translate_keyboard())
        elif mode == "voice":
            MODE[chat_id] = "voice"
            await update.message.reply_text(MODE_PROMPTS["voice"], reply_markup=voice_keyboard(), parse_mode="Markdown")
        else:
            MODE[chat_id] = mode
            await update.message.reply_text(MODE_PROMPTS[mode], parse_mode="Markdown")
        return

    mode = MODE.get(chat_id)
    if not mode:
        await update.message.reply_text("আগে নিচের মেনু থেকে একটা টুল বেছে নিন 👇", reply_markup=menu_keyboard())
        return

    if PREMIUM_MODE and mode in PREMIUM_TOOLS and user_id not in ADMIN_IDS and not db_flag(chat_id, "premium"):
        await update.message.reply_text(f"⭐ এই টুলটা প্রিমিয়ামদের জন্য। প্রিমিয়াম নিতে: {DEVELOPER_TAG}")
        return

    try:
        if mode == "chat":
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await send_long(update, await asyncio.to_thread(ai_reply, chat_id, text))
            bump(chat_id, "chat")
        elif mode in ("tr_bn_en", "tr_en_bn"):
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            sys = ("Translate the user's Bangla text into natural English. Output ONLY the translation."
                   if mode == "tr_bn_en" else
                   "Translate the user's English text into natural Bangla. Output ONLY the translation.")
            await send_long(update, await asyncio.to_thread(groq_one, sys, text, 0.3))
            bump(chat_id, "tr")
        elif mode == "caption":
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            out = await asyncio.to_thread(groq_one, "You write short, emotional Bangla captions/status lines for social media. Give 5 different options, numbered, one line each, ready to copy.", text, 0.9)
            await send_long(update, out)
            bump(chat_id, "caption")
        elif mode == "story":
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            out = await asyncio.to_thread(groq_one, "Write in Bangla based on the user's topic: a short story (200-300 words) or a short poem if they ask for a poem. Emotional and beautiful.", text, 0.9)
            await send_long(update, out)
            bump(chat_id, "story")
        elif mode == "lyrics":
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            out = await asyncio.to_thread(groq_one, "The user asks for song lyrics. If you know the song, provide the lyrics; if not sure, honestly say you are not sure and give what you know.", text, 0.5)
            await send_long(update, out)
            bump(chat_id, "lyrics")
        elif mode == "voice":
            if len(text) > MAX_VOICE_CHARS:
                await update.message.reply_text(f"⚠️ ভয়েসের লেখা বড় ({len(text)} অক্ষর)। সর্বোচ্চ {MAX_VOICE_CHARS}।")
                return
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
            voice = VOICES[USER_VOICE.get(chat_id, "bn_f")][1]
            out = os.path.join(tempfile.gettempdir(), f"tts_{chat_id}.ogg")
            try:
                path = await make_voice(text, voice, out)
                with open(path, "rb") as fh:
                    if path.endswith(".ogg"):
                        await update.message.reply_voice(voice=fh)
                    else:
                        await update.message.reply_audio(audio=fh, title="Voice Maker")
                bump(chat_id, "voices")
            finally:
                try: os.unlink(out)
                except OSError: pass
        elif mode == "stt":
            await update.message.reply_text("🎤 এই টুলে **ভয়েস মেসেজ** পাঠান।", parse_mode="Markdown")
        elif mode == "image":
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
            img = await asyncio.to_thread(make_image, text)
            await update.message.reply_photo(photo=img, caption="🖼️ আপনার AI ছবি!")
            bump(chat_id, "images")
        elif mode == "download":
            if "http" not in text:
                await update.message.reply_text("সঠিক লিংক পাঠান (http দিয়ে শুরু)।")
                return
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
            path = await asyncio.to_thread(download_video, text.strip())
            try:
                if os.path.getsize(path) > 49 * 1024 * 1024:
                    await update.message.reply_text("⚠️ ভিডিও ৫০MB-এর বেশি — বটে পাঠানো যায় না।")
                else:
                    with open(path, "rb") as fh:
                        await update.message.reply_video(video=fh, caption="📥 আপনার ভিডিও!")
                    bump(chat_id, "download")
            finally:
                shutil.rmtree(os.path.dirname(path), ignore_errors=True)
        elif mode == "prayer":
            await update.message.reply_text(await asyncio.to_thread(prayer_times, text.title()), parse_mode="Markdown")
            bump(chat_id, "prayer")
        elif mode == "weather":
            await update.message.reply_text(await asyncio.to_thread(weather_now, text), parse_mode="Markdown")
            bump(chat_id, "weather")
        elif mode == "currency":
            await update.message.reply_text(await asyncio.to_thread(currency_convert, text), parse_mode="Markdown")
            bump(chat_id, "currency")
        elif mode == "shorten":
            if "http" not in text:
                await update.message.reply_text("সঠিক লিংক পাঠান (http দিয়ে শুরু)।")
                return
            out = await asyncio.to_thread(shorten_url, text.strip())
            await update.message.reply_text(f"🔗 ছোট লিংক: {out}")
            bump(chat_id, "shorten")
        elif mode == "dict":
            await send_long(update, await asyncio.to_thread(dictionary_lookup, text))
            bump(chat_id, "dict")
        elif mode == "fun":
            out = await asyncio.to_thread(groq_one, "Give ONE funny Bangla joke and ONE short motivational line in Bangla, with emojis.", text, 0.9)
            await send_long(update, out)
            bump(chat_id, "fun")
        elif mode == "bmi":
            parts = text.replace(",", " ").split()
            w, h = float(parts[0]), float(parts[1])
            feet = int(h)
            inches = round((h - feet) * 10)
            meters = (feet * 12 + inches) * 0.0254
            bmi = w / (meters * meters)
            cat = ("ওজন কম" if bmi < 18.5 else "স্বাভাবিক ✅" if bmi < 25
                   else "ওজন বেশি" if bmi < 30 else "স্থূলতা")
            await update.message.reply_text(f"🧮 BMI: **{bmi:.1f}**\nঅবস্থা: {cat}", parse_mode="Markdown")
            bump(chat_id, "bmi")
        elif mode == "qr":
            buf = await asyncio.to_thread(make_qr, text)
            await update.message.reply_photo(photo=buf, caption="🔲 আপনার QR কোড!")
            bump(chat_id, "qr")
        elif mode == "news":
            await update.message.reply_text(await asyncio.to_thread(top_news), parse_mode="Markdown", disable_web_page_preview=True)
            bump(chat_id, "news")
        elif mode == "crypto":
            await update.message.reply_text(await asyncio.to_thread(crypto_price, text), parse_mode="Markdown")
            bump(chat_id, "crypto")
        elif mode == "age":
            await update.message.reply_text(await asyncio.to_thread(age_calc, text), parse_mode="Markdown")
            bump(chat_id, "age")
        elif mode == "unit":
            await update.message.reply_text(await asyncio.to_thread(unit_convert, text), parse_mode="Markdown")
            bump(chat_id, "unit")
        elif mode == "fancy":
            await update.message.reply_text(fancy_text(text), parse_mode="Markdown")
            bump(chat_id, "fancy")
        elif mode == "love":
            await update.message.reply_text(love_calc(text), parse_mode="Markdown")
            bump(chat_id, "love")
        elif mode == "password":
            await update.message.reply_text(f"🔐 `{gen_password()}`", parse_mode="Markdown")
            bump(chat_id, "password")
        elif mode == "dua":
            ar, bn = DUAS[date.today().toordinal() % len(DUAS)]
            await update.message.reply_text(f"🕌 **আজকের দোয়া**\n\n{ar}\n\n{bn}")
            bump(chat_id, "dua")
        elif mode == "reminder":
            parsed = parse_reminder(text)
            if not parsed:
                await update.message.reply_text("এভাবে লিখুন: **10 মিনিট পর পানি খাব** / **1 ঘণ্টা পর পড়ব**", parse_mode="Markdown")
                return
            secs, note = parsed
            context.job_queue.run_once(send_reminder, when=secs, chat_id=chat_id, data=note)
            mins = secs // 60
            await update.message.reply_text(f"⏰ ঠিক আছে! {mins} মিনিট পর মনে করিয়ে দেব: {note}")
            bump(chat_id, "reminder")
        elif mode == "quiz":
            st = QUIZ.get(chat_id)
            if text.lower() in ("start", "next", "hi", "হাই", "শুরু"):
                await start_quiz(update, chat_id)
            elif st and st.get("answer", -1) < 0:
                await start_quiz(update, chat_id)
            else:
                await update.message.reply_text("উত্তর দিতে উপরের বাটনগুলো চাপুন! নতুন প্রশ্নের জন্য 'start' লিখুন।")
        elif mode == "shop":
            if text.lower() in ("list", "লিস্ট", "পণ্য"):
                await shop_list(update)
            else:
                await update.message.reply_text("পণ্য কিনতে তালিকার বাটনে চাপুন। তালিকা দেখতে 'list' লিখুন।")
        elif mode == "contact":
            pass
        elif mode == "imgpdf":
            await update.message.reply_text("📄 এই টুলে **ছবি** পাঠান।", parse_mode="Markdown")
        elif mode == "compress":
            await update.message.reply_text("📸 এই টুলে **ছবি** পাঠান।", parse_mode="Markdown")
        elif mode == "pdfsum":
            await update.message.reply_text("📝 এই টুলে **PDF ফাইল** পাঠান।", parse_mode="Markdown")
    except Exception as e:
        log.error("tool %s error: %s", mode, e)
        await update.message.reply_text("দুঃখিত, একটু সমস্যা হয়েছে। লেখাটা ঠিক ফরম্যাটে দিয়ে আবার চেষ্টা করুন। 🙏")

# ---------------- web + main ----------------
web = Flask(__name__)

@web.route("/")
def home():
    return "BIG AI bot v2 is running."

def run_web():
    web.run(host="0.0.0.0", port=PORT)

async def post_init(app):
    me = await app.bot.get_me()
    BOT_USERNAME["name"] = me.username or ""

def main():
    if not TOKEN or not GROQ_KEY:
        raise SystemExit("TELEGRAM_BOT_TOKEN and GROQ_API_KEY must be set.")
    db_init()
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler(
        ["premium", "ban", "unban", "maintenance", "addproduct", "delproduct",
         "setchannel", "channel"], admin_text_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.VOICE, on_voice_msg))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    Thread(target=run_web, daemon=True).start()
    log.info("Starting polling (premium=%s, force_join=%s, admins=%s)",
             PREMIUM_MODE, FORCE_JOIN or "off", ADMIN_IDS or "none")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()