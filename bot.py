#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete Multi-Tool Bangla Telegram Bot (bot.py)
Tech stack:
- python-telegram-bot v21+ (with job-queue, long polling, Python 3.10–3.14+ compatible)
- Flask background keep-alive server on PORT (default 10000)
- SQLite database (bigbot.db)
- Groq API (dynamic model discovery & fallback, Whisper STT)
- 36+ Tools, Multi-Engine Video Downloader (TikWM + Cobalt + yt-dlp),
  Points/Levels, Referral, Daily Bonus, Spin, Quiz, Shop, Force Join, Full Interactive Admin Panel
"""

import asyncio
import datetime
import hashlib
import html
import io
import json
import logging
import os
import random
import re
import secrets
import sqlite3
import string
import subprocess
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import edge_tts
import imageio_ffmpeg
import qrcode
import requests
import yt_dlp
from flask import Flask
from gtts import gTTS
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
try:
    import speech_recognition as sr
except ImportError:
    sr = None
from pypdf import PdfReader
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ChatMemberStatus, ParseMode
from telegram.error import BadRequest, Conflict, Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# LOGGING & CONFIGURATION
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("BigBot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
ADMIN_CHAT_ID_RAW = os.environ.get("ADMIN_CHAT_ID", "").strip()
GROQ_MODEL_ENV = os.environ.get("GROQ_MODEL", "").strip()
PREMIUM_MODE_ENV = os.environ.get("PREMIUM_MODE", "off").strip().lower()
FORCE_JOIN_ENV = os.environ.get("FORCE_JOIN", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

DB_FILE = "bigbot.db"
ERROR_MSG_BN = "দুঃখিত, একটু সমস্যা হয়েছে। আবার চেষ্টা করুন 🙏"
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def get_admin_ids() -> List[int]:
    ids: List[int] = []
    if not ADMIN_CHAT_ID_RAW:
        return ids
    for part in ADMIN_CHAT_ID_RAW.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.append(int(part))
    return ids


ADMIN_IDS: List[int] = get_admin_ids()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ---------------------------------------------------------------------------
# TINY FLASK KEEP-ALIVE SERVER (FOR RENDER FREE TIER)
# ---------------------------------------------------------------------------
flask_app = Flask(__name__)


@flask_app.route("/")
def index() -> str:
    return "BigBot Telegram Bot is alive and running!"


@flask_app.route("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def run_flask() -> None:
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


# ---------------------------------------------------------------------------
# BANGLA DIGIT & TEXT NORMALIZATION HELPERS
# ---------------------------------------------------------------------------
BN_TO_EN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
EN_TO_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def bn_to_en_digits(text: str) -> str:
    if not text:
        return ""
    return text.translate(BN_TO_EN_DIGITS)


def en_to_bn_digits(text: str) -> str:
    if not text:
        return ""
    return str(text).translate(EN_TO_BN_DIGITS)


def normalize_btn_text(text: str) -> str:
    """
    Normalizes button text by removing zero-width joiners (\u200d) and variation selectors (\ufe0f)
    so buttons work 100% reliably across Android, iOS, and Desktop Telegram clients!
    """
    if not text:
        return ""
    cleaned = text.replace("\u200d", "").replace("\ufe0f", "").replace("\u200c", "")
    return " ".join(cleaned.split())


# ---------------------------------------------------------------------------
# PERSISTENT MENU KEYBOARD (PREMIUM LOOK + EXTRA USEFUL TOOLS + ADMIN PANEL)
# ---------------------------------------------------------------------------
BTN_AI_CHAT = "🤖 AI চ্যাট"
BTN_TTS = "🎙️ Voice বানান"
BTN_STT = "🎤 Voice → Text"
BTN_AI_IMG = "🖼️ AI ছবি"
BTN_VID_DL = "📥 ভিডিও ডাউনলোড"
BTN_TRANSLATE = "🌐 অনুবাদ"
BTN_CAPTION = "✍️ Caption বানান"
BTN_STORY = "📖 গল্প / কবিতা"
BTN_IMG_PDF = "🖼️ ছবি → PDF"
BTN_PDF_SUM = "📄 PDF Summary"
BTN_PRAYER = "🕐 নামাজের সময়"
BTN_WEATHER = "🌦️ আবহাওয়া"
BTN_CURRENCY = "💱 কারেন্সি"
BTN_SHORTURL = "🔗 লিংক ছোট করুন"
BTN_DICT = "📚 ডিকশনারি"
BTN_JOKES = "😂 জোকস"
BTN_BMI = "⚖️ BMI হিসাব"
BTN_QR = "🔳 QR বানান"
BTN_NEWS = "📰 আজকের খবর"
BTN_CRYPTO = "🪙 ক্রিপ্টো দাম"
BTN_AGE = "🎂 বয়স হিসাব"
BTN_UNIT = "🔄 ইউনিট কনভার্ট"
BTN_FANCY = "✨ ফ্যান্সি টেক্সট"
BTN_LOVE = "❤️ Love ক্যালকুলেটর"
BTN_COMPRESS = "🗜️ ছবি কমপ্রেস"
BTN_LYRICS = "🎵 গানের লিরিক্স"
BTN_PASSWORD = "🔐 পাসওয়ার্ড"
BTN_DUA = "🤲 আজকের দোয়া"
BTN_REMINDER = "⏰ রিমাইন্ডার"
BTN_QUIZ = "🧠 কুইজ খেলুন"
# 6 New High-Utility Tools
BTN_GRAMMAR = "📝 বানান ও Grammar"
BTN_EMAIL_CV = "📧 ইমেইল / আবেদনপত্র"
BTN_CODE_HELP = "💻 কোড জেনারেটর"
BTN_BIO_GEN = "🪪 স্টাইলিশ বায়ো"
BTN_DREAM_ISLAM = "🌙 স্বপ্ন ও ইসলামিক প্রশ্ন"
BTN_MATH_SOLVE = "🧮 অংক ও বিজ্ঞান সমাধান"
BTN_BLOOD_INFO = "🩸 রক্তের গ্রুপ গাইড"
BTN_DIET_PLAN = "🥗 ডায়েট ও স্বাস্থ্য চার্ট"
BTN_BIZ_IDEA = "💼 বিজনেস আইডিয়া"
BTN_MOVIE_REC = "🎬 মুভি রিকমেন্ডেশন"
# Shop, Engagement & System Buttons
BTN_SHOP = "🛍️ শপ"
BTN_CONTACT = "📩 Contact Admin"
BTN_PROFILE = "👤 প্রোফাইল"
BTN_LEADERBOARD = "🏆 লিডারবোর্ড"
BTN_DAILY = "🎁 ডেইলি বোনাস"
BTN_SPIN = "🎰 স্পিন"
BTN_REFER = "👥 রেফার করুন"
BTN_ABOUT = "ℹ️ About"
BTN_HELP = "❓ Help"
BTN_DEV = "👨💻 Developer"
BTN_ADMIN_PANEL = "🛠️ Admin Panel"
BTN_MENU = "🏠 মেনু"
BTN_MAKE_PDF_DONE = "✅ PDF বানান"

BASE_MENU_LAYOUT = [
    [KeyboardButton(BTN_AI_CHAT), KeyboardButton(BTN_TTS)],
    [KeyboardButton(BTN_STT), KeyboardButton(BTN_AI_IMG)],
    [KeyboardButton(BTN_VID_DL), KeyboardButton(BTN_TRANSLATE)],
    [KeyboardButton(BTN_CAPTION), KeyboardButton(BTN_STORY)],
    [KeyboardButton(BTN_IMG_PDF), KeyboardButton(BTN_PDF_SUM)],
    [KeyboardButton(BTN_PRAYER), KeyboardButton(BTN_WEATHER)],
    [KeyboardButton(BTN_CURRENCY), KeyboardButton(BTN_SHORTURL)],
    [KeyboardButton(BTN_DICT), KeyboardButton(BTN_JOKES)],
    [KeyboardButton(BTN_BMI), KeyboardButton(BTN_QR)],
    [KeyboardButton(BTN_NEWS), KeyboardButton(BTN_CRYPTO)],
    [KeyboardButton(BTN_AGE), KeyboardButton(BTN_UNIT)],
    [KeyboardButton(BTN_FANCY), KeyboardButton(BTN_LOVE)],
    [KeyboardButton(BTN_COMPRESS), KeyboardButton(BTN_LYRICS)],
    [KeyboardButton(BTN_PASSWORD), KeyboardButton(BTN_DUA)],
    [KeyboardButton(BTN_REMINDER), KeyboardButton(BTN_QUIZ)],
    [KeyboardButton(BTN_GRAMMAR), KeyboardButton(BTN_EMAIL_CV)],
    [KeyboardButton(BTN_CODE_HELP), KeyboardButton(BTN_BIO_GEN)],
    [KeyboardButton(BTN_DREAM_ISLAM), KeyboardButton(BTN_MATH_SOLVE)],
    [KeyboardButton(BTN_BLOOD_INFO), KeyboardButton(BTN_DIET_PLAN)],
    [KeyboardButton(BTN_BIZ_IDEA), KeyboardButton(BTN_MOVIE_REC)],
    [KeyboardButton(BTN_SHOP), KeyboardButton(BTN_CONTACT)],
    [KeyboardButton(BTN_PROFILE), KeyboardButton(BTN_LEADERBOARD)],
    [KeyboardButton(BTN_DAILY), KeyboardButton(BTN_SPIN)],
    [KeyboardButton(BTN_REFER), KeyboardButton(BTN_ABOUT)],
    [KeyboardButton(BTN_HELP), KeyboardButton(BTN_DEV)],
]


def get_main_menu_markup(user_id: Optional[int] = None) -> ReplyKeyboardMarkup:
    rows = [list(r) for r in BASE_MENU_LAYOUT]
    if user_id and is_admin(user_id):
        rows.append([KeyboardButton(BTN_ADMIN_PANEL), KeyboardButton(BTN_MENU)])
    else:
        rows.append([KeyboardButton(BTN_MENU)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


MAIN_MENU_MARKUP = get_main_menu_markup()

PDF_COLLECT_MARKUP = ReplyKeyboardMarkup(
    [[KeyboardButton(BTN_MAKE_PDF_DONE)], [KeyboardButton(BTN_MENU)]],
    resize_keyboard=True,
)

ALL_BUTTON_CONSTANTS = [
    BTN_AI_CHAT, BTN_TTS, BTN_STT, BTN_AI_IMG,
    BTN_VID_DL, BTN_TRANSLATE, BTN_CAPTION, BTN_STORY,
    BTN_IMG_PDF, BTN_PDF_SUM, BTN_PRAYER, BTN_WEATHER,
    BTN_CURRENCY, BTN_SHORTURL, BTN_DICT, BTN_JOKES,
    BTN_BMI, BTN_QR, BTN_NEWS, BTN_CRYPTO,
    BTN_AGE, BTN_UNIT, BTN_FANCY, BTN_LOVE,
    BTN_COMPRESS, BTN_LYRICS, BTN_PASSWORD, BTN_DUA,
    BTN_REMINDER, BTN_QUIZ,
    BTN_GRAMMAR, BTN_EMAIL_CV, BTN_CODE_HELP, BTN_BIO_GEN,
    BTN_DREAM_ISLAM, BTN_MATH_SOLVE,
    BTN_BLOOD_INFO, BTN_DIET_PLAN, BTN_BIZ_IDEA, BTN_MOVIE_REC,
    BTN_SHOP, BTN_CONTACT, BTN_PROFILE, BTN_LEADERBOARD,
    BTN_DAILY, BTN_SPIN, BTN_REFER, BTN_ABOUT,
    BTN_HELP, BTN_DEV, BTN_ADMIN_PANEL, BTN_MENU, BTN_MAKE_PDF_DONE,
]

NORMALIZED_BUTTON_MAP: Dict[str, str] = {
    normalize_btn_text(b): b for b in ALL_BUTTON_CONSTANTS
}
# Additional fallback aliases for Developer / Admin buttons
NORMALIZED_BUTTON_MAP[normalize_btn_text("👨‍💻 Developer")] = BTN_DEV
NORMALIZED_BUTTON_MAP[normalize_btn_text("👨💻 Developer")] = BTN_DEV
NORMALIZED_BUTTON_MAP[normalize_btn_text("🛠 Admin Panel")] = BTN_ADMIN_PANEL


def match_menu_button(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None
    norm = normalize_btn_text(raw_text)
    if norm in NORMALIZED_BUTTON_MAP:
        return NORMALIZED_BUTTON_MAP[norm]
    return None


# ---------------------------------------------------------------------------
# SQLITE DATABASE MANAGEMENT (bigbot.db)
# ---------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                points INTEGER DEFAULT 0,
                week_points INTEGER DEFAULT 0,
                referred_by INTEGER DEFAULT NULL,
                last_daily TEXT DEFAULT '',
                last_spin TEXT DEFAULT '',
                daily_streak INTEGER DEFAULT 0,
                quiz_streak INTEGER DEFAULT 0,
                premium INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price TEXT NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                customer_details TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS forwarded_messages (
                admin_msg_id INTEGER,
                admin_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (admin_msg_id, admin_id)
            )
            """
        )
        conn.commit()


def get_setting(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row and row["value"] is not None:
            return str(row["value"])
        return default


def set_setting(key: str, value: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def ensure_user(user_id: int, name: str, referred_by: Optional[int] = None) -> Tuple[bool, Optional[int]]:
    """
    Ensures user exists in DB. Returns (is_new_user, valid_referrer_id).
    """
    with get_db() as conn:
        row = conn.execute("SELECT user_id, name FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            if name and row["name"] != name:
                conn.execute("UPDATE users SET name = ? WHERE user_id = ?", (name, user_id))
                conn.commit()
            return False, None

        valid_ref: Optional[int] = None
        if referred_by and referred_by != user_id:
            ref_row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (referred_by,)).fetchone()
            if ref_row:
                valid_ref = referred_by

        conn.execute(
            "INSERT INTO users (user_id, name, points, week_points, referred_by) VALUES (?, ?, 0, 0, ?)",
            (user_id, name or "User", valid_ref),
        )
        if valid_ref:
            conn.execute(
                "UPDATE users SET points = points + 10, week_points = week_points + 10 WHERE user_id = ?",
                (valid_ref,),
            )
        conn.commit()
        return True, valid_ref


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def is_user_banned(user_id: int) -> bool:
    u = get_user(user_id)
    return bool(u and u["banned"] == 1)


def is_user_premium(user_id: int) -> bool:
    if is_admin(user_id):
        return True
    u = get_user(user_id)
    return bool(u and u["premium"] == 1)


def add_points(user_id: int, pts: int) -> None:
    actual_pts = pts * 2 if (pts == 1 and is_user_premium(user_id)) else pts
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET points = points + ?, week_points = week_points + ? WHERE user_id = ?",
            (actual_pts, actual_pts, user_id),
        )
        conn.commit()


def clean_ai_text(text: str) -> str:
    """
    Removes ugly raw markdown (**bold**, ### headers, LaTeX math symbols, and Markdown tables)
    from AI output so every message looks clean, readable, and natural inside Telegram cards.
    """
    if not text:
        return ""
    t = text.replace("**", "").replace("__", "")
    t = re.sub(r"^#{1,6}\s*", "📌 ", t, flags=re.MULTILINE)
    t = t.replace("\times", "×").replace("\div", "÷").replace("\pm", "±")
    t = t.replace("\therefore", "∴").replace("\Rightarrow", "⇒").replace("\approx", "≈")
    t = t.replace("$$", "").replace("$", "")

    # Strip Markdown table separator rows (e.g. |---|---|) and convert table rows into clean text lines
    cleaned_lines = []
    for line in t.splitlines():
        s = line.strip()
        if re.match(r"^[|\s:\-]+$", s) and "|" in s and "-" in s:
            continue
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|") if c.strip()]
            if cells:
                cleaned_lines.append("• " + " — ".join(cells))
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def get_total_users() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
        return int(row["cnt"]) if row else 0


def get_total_orders() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM orders").fetchone()
        return int(row["cnt"]) if row else 0


def get_total_banned() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE banned = 1").fetchone()
        return int(row["cnt"]) if row else 0


def get_total_premium() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE premium = 1").fetchone()
        return int(row["cnt"]) if row else 0


def get_level_name(points: int) -> str:
    if points >= 400:
        return "💎 Diamond"
    if points >= 150:
        return "🥇 Gold"
    if points >= 50:
        return "🥈 Silver"
    return "🥉 Bronze"


def get_user_rank(user_id: int) -> int:
    with get_db() as conn:
        row = conn.execute("SELECT points FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return 0
        pts = row["points"]
        higher = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE points > ?", (pts,)).fetchone()
        return (int(higher["cnt"]) if higher else 0) + 1


def get_referral_count(user_id: int) -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE referred_by = ?", (user_id,)).fetchone()
        return int(row["cnt"]) if row else 0


# ---------------------------------------------------------------------------
# FORCE JOIN & MAINTENANCE SETTINGS
# ---------------------------------------------------------------------------
def get_force_join_channel() -> str:
    """
    Returns active force-join channel (@ChannelName) or '' if disabled.
    DB setting overrides FORCE_JOIN env.
    """
    db_val = get_setting("force_join", "__UNSET__")
    if db_val != "__UNSET__":
        if db_val.lower() in ("off", "none", ""):
            return ""
        return db_val
    if FORCE_JOIN_ENV and FORCE_JOIN_ENV.lower() not in ("off", "none"):
        return FORCE_JOIN_ENV if FORCE_JOIN_ENV.startswith("@") else f"@{FORCE_JOIN_ENV}"
    return ""


def is_maintenance_on() -> bool:
    return get_setting("maintenance", "off").lower() == "on"


def is_premium_mode_on() -> bool:
    db_val = get_setting("premium_mode", "")
    if db_val:
        return db_val.lower() == "on"
    return PREMIUM_MODE_ENV == "on"


async def check_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Checks if the caller is a member of the force-join channel.
    Returns True if allowed to proceed, False if blocked (and sends join prompt).
    """
    user = update.effective_user
    if not user:
        return False
    if is_admin(user.id):
        return True

    channel = get_force_join_channel()
    if not channel:
        return True

    if not channel.startswith("@") and not channel.startswith("-100"):
        channel = f"@{channel}"

    try:
        member = await context.bot.get_chat_member(chat_id=channel, user_id=user.id)
        if member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        ):
            return True
        if member.status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False):
            return True
    except TelegramError as e:
        logger.warning(f"Force join check error for {channel}: {e}")
        return True

    clean_username = channel.lstrip("@")
    join_url = f"https://t.me/{clean_username}"
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 চ্যানেলে জয়েন করুন", url=join_url)],
            [InlineKeyboardButton("✅ জয়েন করেছি", callback_data="recheck_join")],
        ]
    )
    msg_text = (
        f"🔐 <b>অ্যাক্সেস লক করা আছে!</b>\n"
        f"{DIVIDER}\n"
        f"বটের সকল প্রিমিয়াম টুলস ফ্রি ব্যবহার করতে আমাদের অফিসিয়াল চ্যানেলে ({html.escape(channel)}) জয়েন করুন।\n\n"
        f"<blockquote>👇 নিচের বাটনে ক্লিক করে জয়েন করার পর <b>‘✅ জয়েন করেছি’</b> বাটনে চাপুন।</blockquote>"
    )
    if update.callback_query:
        await update.callback_query.message.reply_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif update.effective_message:
        await update.effective_message.reply_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return False


# ---------------------------------------------------------------------------
# GROQ API: DYNAMIC MODEL SELECTION & CHAT / WHISPER
# ---------------------------------------------------------------------------
GROQ_PREFERRED_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
]

GROQ_WHISPER_MODELS = [
    "whisper-large-v3",
    "whisper-large-v3-turbo",
    "distil-whisper-large-v3-en",
]

_cached_groq_models: List[str] = []
_cached_groq_selected: Optional[str] = None
_cached_groq_ts: float = 0.0


def fetch_groq_models(force_refresh: bool = False) -> List[str]:
    global _cached_groq_models, _cached_groq_selected, _cached_groq_ts
    now = time.time()
    if not force_refresh and _cached_groq_models and (now - _cached_groq_ts < 3600):
        return _cached_groq_models

    if not GROQ_API_KEY:
        return []

    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            models = [m.get("id", "") for m in data if m.get("id")]
            if models:
                _cached_groq_models = models
                _cached_groq_ts = now
                _cached_groq_selected = None
                return models
    except Exception as e:
        logger.error(f"Error fetching Groq models: {e}")

    return _cached_groq_models


def select_groq_chat_model(force_refresh: bool = False) -> str:
    global _cached_groq_selected
    if not force_refresh and _cached_groq_selected:
        return _cached_groq_selected

    available = fetch_groq_models(force_refresh=force_refresh)
    available_set = set(available)

    if GROQ_MODEL_ENV and (not available_set or GROQ_MODEL_ENV in available_set):
        _cached_groq_selected = GROQ_MODEL_ENV
        return _cached_groq_selected

    for candidate in GROQ_PREFERRED_MODELS:
        if candidate in available_set:
            _cached_groq_selected = candidate
            return _cached_groq_selected

    for m in available:
        lower_m = m.lower()
        if "whisper" not in lower_m and "guard" not in lower_m and "tts" not in lower_m:
            _cached_groq_selected = m
            return _cached_groq_selected

    _cached_groq_selected = GROQ_MODEL_ENV or GROQ_PREFERRED_MODELS[0]
    return _cached_groq_selected


def call_groq_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 1500,
    json_mode: bool = False,
) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    model = select_groq_chat_model(force_refresh=False)
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(2):
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        resp = requests.post(url, headers=headers, json=payload, timeout=45)
        if resp.status_code == 404 and attempt == 0:
            logger.warning(f"Groq model {model} returned 404. Refreshing model list and retrying...")
            model = select_groq_chat_model(force_refresh=True)
            continue

        if resp.status_code == 400 and json_mode and attempt == 0:
            json_mode = False
            continue

        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content

    raise RuntimeError("Groq chat completion failed after retry.")


def preprocess_voice_for_stt(input_path: str) -> Tuple[str, Optional[str]]:
    """
    Converts Telegram OGG/Opus voice clips into:
    1) Clean 16kHz mono 16-bit PCM WAV (for Google Speech Recognition bn-BD / en-US)
    2) Clean 16kHz mono MP3 (for Groq Whisper)
    with speech-band filtering and volume normalization.
    """
    out_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    out_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    wav_ok = False
    try:
        subprocess.run(
            [
                ffmpeg_exe, "-y", "-i", input_path,
                "-vn", "-ac", "1", "-ar", "16000",
                "-af", "highpass=f=70,lowpass=f=7800,volume=1.5",
                "-acodec", "pcm_s16le", out_wav,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25,
            check=True,
        )
        if os.path.exists(out_wav) and os.path.getsize(out_wav) > 400:
            wav_ok = True
    except Exception as e:
        logger.warning(f"WAV conversion error: {e}")

    mp3_ok = False
    try:
        subprocess.run(
            [
                ffmpeg_exe, "-y", "-i", input_path,
                "-vn", "-ac", "1", "-ar", "16000",
                "-af", "highpass=f=70,lowpass=f=7800,volume=1.5",
                "-b:a", "64k", out_mp3,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25,
            check=True,
        )
        if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 200:
            mp3_ok = True
    except Exception as e:
        logger.warning(f"MP3 conversion error: {e}")

    if not wav_ok and os.path.exists(out_wav):
        try:
            os.remove(out_wav)
        except OSError:
            pass
    if not mp3_ok and os.path.exists(out_mp3):
        try:
            os.remove(out_mp3)
        except OSError:
            pass

    return (out_mp3 if mp3_ok else input_path), (out_wav if wav_ok else None)


def recognize_with_google_web_speech(wav_path: Optional[str], lang_mode: str = "bn") -> str:
    """
    Uses Google's official Web Speech API (the same engine used by Gboard Bangla Voice Typing!)
    which has 99% accuracy on Bangladeshi Bangla (bn-BD) and English (en-US).
    """
    if not wav_path or not os.path.exists(wav_path) or sr is None:
        return ""
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    primary_lang = "en-US" if lang_mode == "en" else "bn-BD"
    secondary_lang = "bn-BD" if primary_lang == "en-US" else "en-US"

    try:
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source, duration=58)
        try:
            text = recognizer.recognize_google(audio_data, language=primary_lang)
            if text and text.strip():
                return text.strip()
        except Exception:
            if lang_mode == "auto":
                text = recognizer.recognize_google(audio_data, language=secondary_lang)
                if text and text.strip():
                    return text.strip()
    except Exception as e:
        logger.warning(f"Google Speech Recognition fallback: {e}")
    return ""


def refine_stt_transcript(google_text: str, whisper_text: str, lang_mode: str = "bn") -> str:
    """
    Combines Google Speech Recognition (bn-BD) and Whisper output using Groq LLM
    to fix any spelling mistake, broken conjunct (যুক্তবর্ণ), or punctuation error.
    """
    g_clean = (google_text or "").strip()
    w_clean = (whisper_text or "").strip()

    # If Google Speech Recognition succeeded in Bangla mode, it already has native Bangladeshi spelling;
    # we pass both to Groq with strict instructions to preserve Google's exact words and only add punctuation/fix obvious typos.
    if g_clean and not w_clean:
        base_text = g_clean
    elif w_clean and not g_clean:
        base_text = w_clean
    elif g_clean and w_clean:
        base_text = f"Primary (Google bn-BD): {g_clean}\nSecondary (Whisper): {w_clean}"
    else:
        return ""

    try:
        sys_prompt = (
            "You are an expert Bangladeshi Bangla & English speech-to-text spelling corrector. "
            "You are given raw speech recognition output. "
            "If 'Primary (Google bn-BD)' is present, trust its words and meaning strongly, and only add proper punctuation (দাঁড়ি, কমা, প্রশ্নবোধক চিহ্ন) and fix any minor spelling typo. "
            "If only Whisper output is present and it contains broken Bangla spelling, Assamese/Hindi characters, or phonetic errors, reconstruct the exact intended standard বাংলা (or English) sentence naturally. "
            "Output ONLY the final corrected text—no labels, no quotes, no explanations."
        )
        fixed = call_groq_chat(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": base_text},
            ],
            temperature=0.1,
            max_tokens=800,
        )
        if fixed and len(fixed.strip()) > 0:
            res = fixed.strip().strip('"').strip("'")
            res = re.sub(r"^(?:Primary|Secondary|Corrected).*?:\s*", "", res, flags=re.IGNORECASE).strip()
            return res
    except Exception as e:
        logger.warning(f"STT post-processing fallback: {e}")

    return g_clean or w_clean


def call_groq_whisper(file_path: str, lang_mode: str = "bn") -> str:
    processed_mp3, processed_wav = preprocess_voice_for_stt(file_path)

    google_transcript = ""
    whisper_transcript = ""
    last_err: Optional[Exception] = None

    try:
        # Engine 1: Google Web Speech API (bn-BD / en-US) — best for Bangla voice spelling!
        google_transcript = recognize_with_google_web_speech(processed_wav, lang_mode=lang_mode)

        # Engine 2: Groq Whisper API
        if GROQ_API_KEY:
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
            mime_type = "audio/mpeg" if processed_mp3.endswith(".mp3") else "audio/ogg"
            models_to_try = (
                ["whisper-large-v3", "whisper-large-v3-turbo", "distil-whisper-large-v3-en"]
                if lang_mode == "en"
                else ["whisper-large-v3", "whisper-large-v3-turbo"]
            )
            for model in models_to_try:
                try:
                    with open(processed_mp3, "rb") as f:
                        files = {"file": (os.path.basename(processed_mp3), f, mime_type)}
                        data: Dict[str, str] = {"model": model, "temperature": "0"}
                        if lang_mode == "bn":
                            data["language"] = "bn"
                            data["prompt"] = "আসসালামু আলাইকুম, এটি স্পষ্ট ও শুদ্ধ বাংলা ভাষার ভয়েস মেসেজ।"
                        elif lang_mode == "en":
                            data["language"] = "en"
                            data["prompt"] = "Clear English voice message."
                        else:
                            data["prompt"] = "বাংলা এবং English ভয়েস মেসেজ।"

                        resp = requests.post(url, headers=headers, files=files, data=data, timeout=45)
                    if resp.status_code == 404:
                        continue
                    resp.raise_for_status()
                    w_txt = resp.json().get("text", "").strip()
                    if w_txt:
                        whisper_transcript = w_txt
                        break
                except Exception as e:
                    last_err = e
                    logger.warning(f"Whisper error with {model}: {e}")

        final_text = refine_stt_transcript(google_transcript, whisper_transcript, lang_mode=lang_mode)
        if final_text:
            return final_text
    finally:
        for p in (processed_mp3, processed_wav):
            if p and p != file_path and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    if last_err:
        raise last_err
    raise RuntimeError("Could not transcribe audio from either Google Speech or Whisper.")


# ---------------------------------------------------------------------------
# 5-ENGINE ULTRA-HD AI IMAGE GENERATOR & WATERMARK-FREE POLISHER
# ---------------------------------------------------------------------------
def enhance_image_prompt_with_groq(user_prompt: str) -> str:
    """
    Translates Bangla/short prompts into a rich, cinematic English Flux prompt
    so the generated image is ultra-detailed, photorealistic, and accurate.
    """
    try:
        sys_msg = (
            "You are an expert AI image prompt engineer for the Flux image model. "
            "Convert the user's input (which may be in Bangla, Banglish, or English) into a single, vivid, "
            "masterpiece English image generation prompt (max 45 words). "
            "Include subject details, natural lighting, cinematic composition, ultra-detailed 8k photorealistic quality, "
            "and sharp focus. Output ONLY the raw English prompt text, no quotes or explanations."
        )
        enhanced = call_groq_chat(
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=140,
        )
        cleaned = enhanced.strip().strip('"').strip("'")
        if cleaned and len(cleaned) > 5:
            return cleaned
    except Exception as e:
        logger.warning(f"Prompt enhancement fallback to raw prompt: {e}")
    return f"{user_prompt}, masterpiece, ultra detailed, 8k photorealistic, cinematic lighting, sharp focus"


def _has_corner_watermark(im: Image.Image) -> bool:
    """
    Detects if an image has a synthetic white/bright watermark box or text badge
    in the bottom-right, bottom-left, or bottom-center strip.
    """
    rgb = im.convert("RGB")
    w, h = rgb.size
    for x1_r, x2_r in ((0.55, 1.0), (0.0, 0.45), (0.25, 0.75)):
        strip = rgb.crop((int(w * x1_r), int(h * 0.91), int(w * x2_r), h))
        pixels = list(strip.getdata())
        if not pixels:
            continue
        very_bright = sum(1 for r, g, b in pixels if r > 240 and g > 240 and b > 240)
        very_dark = sum(1 for r, g, b in pixels if r < 20 and g < 20 and b < 20)
        total = len(pixels)
        if very_bright / total > 0.06 and very_dark / total > 0.06:
            return True
    return False


def remove_bottom_watermark_and_polish(img_bytes: bytes, aggressive_crop: bool = False) -> bytes:
    """
    Guarantees 100% watermark-free, razor-sharp 1024x1024 AI images.
    - Cuts bottom 16%, top 5%, and 7% on left/right whenever aggressive_crop is True or
      a watermark signature is detected, then verifies the final image is 100% clean.
    """
    with Image.open(io.BytesIO(img_bytes)) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size

        if aggressive_crop or _has_corner_watermark(rgb) or h >= 1100:
            # Slice off top 5%, bottom 16%, and 7% left/right so NO watermark at the bottom or corners can survive
            crop_top = int(h * 0.05)
            crop_bottom = int(h * 0.84)
            margin_x = int(w * 0.07)
            cropped = rgb.crop((margin_x, crop_top, w - margin_x, crop_bottom))
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            final_im = cropped.resize((1024, 1024), resample_filter)
        else:
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            final_im = rgb.resize((1024, 1024), resample_filter) if (w != 1024 or h != 1024) else rgb

        # If a watermark signature still somehow survived, do one extra inner trim
        if _has_corner_watermark(final_im):
            cw, ch = final_im.size
            final_im = final_im.crop((int(cw * 0.05), int(ch * 0.03), int(cw * 0.95), int(ch * 0.88))).resize(
                (1024, 1024), getattr(Image, "Resampling", Image).LANCZOS
            )
            if _has_corner_watermark(final_im):
                raise ValueError("Watermark still detected on image; rejecting engine.")

        final_im = ImageEnhance.Sharpness(final_im).enhance(1.16)
        final_im = ImageEnhance.Contrast(final_im).enhance(1.04)

        out_bio = io.BytesIO()
        final_im.save(out_bio, format="JPEG", quality=98, subsampling=0, optimize=True)
        return out_bio.getvalue()


def _is_valid_image_bytes(raw: bytes) -> bool:
    if not raw or len(raw) < 3500:
        return False
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.verify()
        return True
    except Exception:
        return False


def generate_ai_image_multi_engine(raw_prompt: str, enhanced_prompt: str) -> bytes:
    """
    100% Watermark-Free Multi-Engine AI Image Generator:
    Tries 6 independent free AI image engines in order. If any engine fails or has a watermark,
    it automatically moves to the next engine and NEVER sends a watermarked image.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    rand_seed = random.randint(1000, 999999)
    enc_enh = urllib.parse.quote(enhanced_prompt)
    enc_raw = urllib.parse.quote(raw_prompt)

    # Engine 1: HuggingFace Official Gradio Spaces (100% Native Watermark-Free Raw Model Output)
    hf_spaces = [
        ("https://black-forest-labs-flux-1-schnell.hf.space", "/call/infer", [enhanced_prompt, rand_seed, False, 1024, 1024, 4]),
        ("https://multimodalart-flux-1-merged.hf.space", "/call/infer", [enhanced_prompt, rand_seed, False, 1024, 1024, 4]),
        ("https://bytedance-sdxl-lightning.hf.space", "/call/generate_image", [enhanced_prompt, "4-Step"]),
    ]
    for space_url, endpoint, payload_data in hf_spaces:
        try:
            post_r = requests.post(
                f"{space_url}{endpoint}",
                json={"data": payload_data},
                headers={"Content-Type": "application/json", "User-Agent": headers["User-Agent"]},
                timeout=14,
            )
            if post_r.status_code == 200 and "event_id" in post_r.json():
                ev_id = post_r.json()["event_id"]
                sse_r = requests.get(f"{space_url}{endpoint}/{ev_id}", headers=headers, timeout=22)
                if sse_r.status_code == 200:
                    m_url = re.search(r'"url":\s*"(https?://[^"]+)"', sse_r.text)
                    if m_url:
                        img_r = requests.get(m_url.group(1), headers=headers, timeout=18)
                        if img_r.status_code == 200 and _is_valid_image_bytes(img_r.content):
                            return remove_bottom_watermark_and_polish(img_r.content, aggressive_crop=False)
        except Exception as e:
            logger.debug(f"HF Space {space_url} skipped: {e}")

    # Engine 2: Subnp Free AI Image Generator API (Flux / Turbo)
    for sub_model in ("flux", "turbo"):
        try:
            sub_r = requests.post(
                "https://subnp.com/api/free/generate",
                json={"prompt": enhanced_prompt, "model": sub_model},
                headers={"Content-Type": "application/json", "User-Agent": headers["User-Agent"]},
                timeout=20,
            )
            if sub_r.status_code == 200:
                m_img = re.search(r'"imageUrl":\s*"(https?://[^"]+)"', sub_r.text)
                if m_img:
                    img_r = requests.get(m_img.group(1), headers=headers, timeout=18)
                    if img_r.status_code == 200 and _is_valid_image_bytes(img_r.content):
                        return remove_bottom_watermark_and_polish(img_r.content, aggressive_crop=True)
        except Exception as e:
            logger.debug(f"Subnp {sub_model} skipped: {e}")

    # Engine 3: Hercai v3 Free AI Image Generator API
    try:
        hc_url = f"https://hercai.onrender.com/v3/text2image?prompt={enc_enh}"
        hc_r = requests.get(hc_url, headers=headers, timeout=20)
        if hc_r.status_code == 200 and hc_r.json().get("url"):
            img_r = requests.get(hc_r.json()["url"], headers=headers, timeout=18)
            if img_r.status_code == 200 and _is_valid_image_bytes(img_r.content):
                return remove_bottom_watermark_and_polish(img_r.content, aggressive_crop=False)
    except Exception as e:
        logger.debug(f"Hercai skipped: {e}")

    # Engine 4: Lexica Art High-Res AI Render Search (100% Native Watermark-Free AI Art)
    for q_str in (enc_enh, enc_raw):
        try:
            lex_url = f"https://lexica.art/api/v1/search?q={q_str}"
            lex_r = requests.get(lex_url, headers=headers, timeout=15)
            if lex_r.status_code == 200:
                imgs = lex_r.json().get("images", [])
                for chosen in imgs[:4]:
                    src_url = chosen.get("src")
                    if src_url:
                        img_r = requests.get(src_url, headers=headers, timeout=15)
                        if img_r.status_code == 200 and _is_valid_image_bytes(img_r.content):
                            return remove_bottom_watermark_and_polish(img_r.content, aggressive_crop=False)
        except Exception as e:
            logger.debug(f"Lexica skipped: {e}")

    # Engine 5: Airforce Free Flux API (with mandatory deep crop + watermark rejection check)
    for af_model in ("flux", "flux-realism", "sdxl"):
        try:
            af_url = (
                f"https://api.airforce/v1/imagine2?prompt={enc_enh}"
                f"&model={af_model}&size=1:1&seed={rand_seed}"
            )
            r = requests.get(af_url, headers=headers, timeout=20)
            if r.status_code == 200 and _is_valid_image_bytes(r.content):
                return remove_bottom_watermark_and_polish(r.content, aggressive_crop=True)
        except Exception as e:
            logger.debug(f"Airforce {af_model} skipped: {e}")

    # Engine 6: Pollinations 1024x1280 Tall Mode with mandatory 16% bottom + 7% side crop & watermark rejection check
    pollinations_urls = [
        f"https://pollinations.ai/p/{enc_enh}?width=1024&height=1280&seed={rand_seed}&nologo=true&model=flux",
        f"https://image.pollinations.ai/prompt/{enc_enh}?width=1024&height=1280&seed={rand_seed}&nologo=true&model=flux",
        f"https://image.pollinations.ai/prompt/{enc_raw}?width=1024&height=1280&nologo=true&seed=42",
    ]
    for p_url in pollinations_urls:
        try:
            r = requests.get(p_url, headers=headers, timeout=22)
            if r.status_code == 200 and _is_valid_image_bytes(r.content):
                return remove_bottom_watermark_and_polish(r.content, aggressive_crop=True)
        except Exception as e:
            logger.debug(f"Pollinations URL skipped: {e}")

    raise RuntimeError("All AI image generation engines failed.")


# ---------------------------------------------------------------------------
# PREMIUM BRANDED STUDIO QR CODE GENERATOR (CENTERED "SCAN ME" FOOTER ONLY)
# ---------------------------------------------------------------------------
def generate_premium_qr_card(data_text: str) -> io.BytesIO:
    """
    Creates a 1000x1160 Royal Studio Branded QR Poster Card with:
    - Deep Royal Navy background (#0B1120) & glowing cyan/gold frame
    - Rounded white QR container with soft drop shadow
    - High-density ERROR_CORRECT_H navy QR code with a central Royal Gold/Cyan badge
    - Centered "SCAN ME" ONLY in the bottom footer (never prints raw link/text in footer!)
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=14,
        border=2,
    )
    qr.add_data(data_text)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0F172A", back_color="white").convert("RGBA")
    qr_img = qr_img.resize((680, 680), getattr(Image, "Resampling", Image).LANCZOS)

    draw_qr = ImageDraw.Draw(qr_img)
    cx, cy = 340, 340
    r_outer = 64
    draw_qr.rounded_rectangle(
        (cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer),
        radius=20,
        fill="#FFFFFF",
        outline="#0EA5E9",
        width=5,
    )
    draw_qr.rounded_rectangle(
        (cx - r_outer + 10, cy - r_outer + 10, cx + r_outer - 10, cy + r_outer - 10),
        radius=14,
        fill="#0F172A",
        outline="#F59E0B",
        width=3,
    )
    try:
        font_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_scan = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    except Exception:
        font_badge = ImageFont.load_default()
        font_title = ImageFont.load_default()
        font_scan = ImageFont.load_default()

    b_bbox = draw_qr.textbbox((0, 0), "QR", font=font_badge)
    bw_txt, bh_txt = b_bbox[2] - b_bbox[0], b_bbox[3] - b_bbox[1]
    draw_qr.text((cx - bw_txt // 2, cy - bh_txt // 2 - 4), "QR", fill="#F59E0B", font=font_badge)

    canvas_w, canvas_h = 1000, 1160
    canvas = Image.new("RGB", (canvas_w, canvas_h), "#0B1120")
    draw = ImageDraw.Draw(canvas)

    # Outer glowing frame
    draw.rounded_rectangle((28, 28, canvas_w - 28, canvas_h - 28), radius=38, outline="#0EA5E9", width=4)
    draw.rounded_rectangle((40, 40, canvas_w - 40, canvas_h - 40), radius=32, outline="#F59E0B", width=2)

    # Top header pill (centered text)
    draw.rounded_rectangle((180, 75, canvas_w - 180, 155), radius=40, fill="#1E293B", outline="#38BDF8", width=2)
    header_text = "PREMIUM SMART QR CODE"
    h_bbox = draw.textbbox((0, 0), header_text, font=font_title)
    hw_txt, hh_txt = h_bbox[2] - h_bbox[0], h_bbox[3] - h_bbox[1]
    draw.text(((canvas_w - hw_txt) // 2, 115 - hh_txt // 2 - 3), header_text, fill="#F8FAFC", font=font_title)

    # White rounded card behind QR
    card_x1, card_y1, card_x2, card_y2 = 120, 195, 880, 955
    draw.rounded_rectangle((card_x1 - 6, card_y1 - 6, card_x2 + 6, card_y2 + 6), radius=42, fill="#0284C7")
    draw.rounded_rectangle((card_x1, card_y1, card_x2, card_y2), radius=38, fill="#FFFFFF")

    canvas.paste(qr_img.convert("RGB"), (160, 235))

    # Corner scanner brackets inside white card
    b_col = "#0EA5E9"
    bw = 6
    bl = 45
    draw.line([(145, 220), (145 + bl, 220)], fill=b_col, width=bw)
    draw.line([(145, 220), (145, 220 + bl)], fill=b_col, width=bw)
    draw.line([(855 - bl, 220), (855, 220)], fill=b_col, width=bw)
    draw.line([(855, 220), (855, 220 + bl)], fill=b_col, width=bw)
    draw.line([(145, 930 - bl), (145, 930)], fill=b_col, width=bw)
    draw.line([(145, 930), (145 + bl, 930)], fill=b_col, width=bw)
    draw.line([(855 - bl, 930), (855, 930)], fill=b_col, width=bw)
    draw.line([(855, 930 - bl), (855, 930)], fill=b_col, width=bw)

    # Bottom footer bar: ONLY "SCAN ME" centered in the middle!
    draw.rounded_rectangle((220, 995, canvas_w - 220, 1085), radius=45, fill="#1E293B", outline="#F59E0B", width=3)
    footer_text = "SCAN ME"
    f_bbox = draw.textbbox((0, 0), footer_text, font=font_scan)
    fw_txt, fh_txt = f_bbox[2] - f_bbox[0], f_bbox[3] - f_bbox[1]
    draw.text(((canvas_w - fw_txt) // 2, 1040 - fh_txt // 2 - 4), footer_text, fill="#F59E0B", font=font_scan)

    out_bio = io.BytesIO()
    canvas.save(out_bio, format="PNG", optimize=True)
    out_bio.seek(0)
    return out_bio


# ---------------------------------------------------------------------------
# BUILT-IN DATA: JOKES & 7 VERIFIED DUAS
# ---------------------------------------------------------------------------
BANGLA_JOKES = [
    "শিক্ষক: বলো তো, মানুষ পরকালে কেন যাবে?\nছাত্র: স্যার, সবাই যদি দুনিয়ায় থেকে যায় তবে জায়গা হবে কোথায়! 😂",
    "ডাক্তার: আপনার তো দেখছি চশমা লাগবে।\nরোগী: আপনি কীভাবে বুঝলেন ডাক্তার সাব?\nডাক্তার: কারণ আপনি দরজা রেখে জানলা দিয়ে ঢুকেছেন! 🤣",
    "স্ত্রী: বিয়ের আগে তো বলতে আমার জন্য নরকেও যেতে পারো!\nস্বামী: তো এখন আর যাওয়ার দরকার কী? এখন তো সেখানেই আছি! 😅",
    "বল্টু: জানিস, আমি না দেখে লিখতে পারি!\nবন্ধু: বাহ! কী লিখিস?\nবল্টু: কী লিখি সেটা তো নিজেও পড়তে পারি না! 😂",
    "ক্রেতা: ভাই, এই মুরগিটা এত শুকনো কেন?\nবিক্রেতা: ভাই, মুরগিটা বিসিএস পরীক্ষার টেনশনে খাওয়া-দাওয়া ছেড়ে দিয়েছিল! 🤣",
    "বাবা: তোর রেজাল্ট এত খারাপ কেন?\nছেলে: বাবা, অতি লোভে তাঁতি নষ্ট, তাই বেশি নম্বরের লোভ করিনি! 😄",
    "পুলিশ: এত রাতে রাস্তায় কী করছেন?\nবল্টু: স্যার, ঘুমটা রাস্তায় হারিয়ে গেছে, তাই খুঁজছি! 🤣",
    "বিচারক: আপনি চুরি করেছেন কেন?\nচোর: হুজুর, সবাই বলে নিজের পায়ে দাঁড়াতে, তাই অন্যের সাইকেলটা নিয়েছিলাম! 😂",
    "স্ত্রী: শোনো, আমার জন্মদিনে এবার এমন কিছু দেবে যা চালালে ০ থেকে ১০০-তে উঠে যাবে ২ সেকেন্ডে!\nস্বামী: ওকে, আজই ওজন মাপার মেশিন কিনে আনছি! 😅",
    "শিক্ষক: বলো তো, পৃথিবীর সবচেয়ে প্রাচীন প্রাণী কোনটি?\nছাত্র: স্যার, জেব্রা! কারণ ওটা এখনো সাদাকালো (Black & White) যুগেই আছে! 🤣",
    "বন্ধু ১: ভাই, তোর মোবাইলটা এত গরম হয়ে আছে কেন?\nবন্ধু ২: আর বলিস না, গার্লফ্রেন্ডের সাথে একটু কড়া ভাষায় কথা বলেছি তো! 😂",
    "ডাক্তার: প্রতিদিন সকালে ঘুম থেকে উঠে গরম পানি খাবেন।\nবল্টু: ডাক্তার সাব, আমাদের বাসায় তো একেই গ্যাস থাকে না, আবার ঘুম থেকে উঠে পানি গরম করব কীভাবে! 😄",
]

BD_DISTRICT_MAP: Dict[str, Tuple[str, str]] = {
    "ঢাকা": ("Dhaka", "ঢাকা"), "dhaka": ("Dhaka", "ঢাকা"),
    "গাজীপুর": ("Gazipur", "গাজীপুর"), "gazipur": ("Gazipur", "গাজীপুর"),
    "নারায়ণগঞ্জ": ("Narayanganj", "নারায়ণগঞ্জ"), "narayanganj": ("Narayanganj", "নারায়ণগঞ্জ"),
    "নরসিংদী": ("Narsingdi", "নরসিংদী"), "narsingdi": ("Narsingdi", "নরসিংদী"),
    "মানিকগঞ্জ": ("Manikganj", "মানিকগঞ্জ"), "manikganj": ("Manikganj", "মানিকগঞ্জ"),
    "মুন্সিগঞ্জ": ("Munshiganj", "মুন্সিগঞ্জ"), "munshiganj": ("Munshiganj", "মুন্সিগঞ্জ"),
    "টাঙ্গাইল": ("Tangail", "টাঙ্গাইল"), "tangail": ("Tangail", "টাঙ্গাইল"),
    "কিশোরগঞ্জ": ("Kishoreganj", "কিশোরগঞ্জ"), "kishoreganj": ("Kishoreganj", "কিশোরগঞ্জ"),
    "ফরিদপুর": ("Faridpur", "ফরিদপুর"), "faridpur": ("Faridpur", "ফরিদপুর"),
    "গোপালগঞ্জ": ("Gopalganj", "গোপালগঞ্জ"), "gopalganj": ("Gopalganj", "গোপালগঞ্জ"),
    "মাদারীপুর": ("Madaripur", "মাদারীপুর"), "madaripur": ("Madaripur", "মাদারীপুর"),
    "রাজবাড়ী": ("Rajbari", "রাজবাড়ী"), "rajbari": ("Rajbari", "রাজবাড়ী"),
    "শরীয়তপুর": ("Shariatpur", "শরীয়তপুর"), "shariatpur": ("Shariatpur", "শরীয়তপুর"),
    "চট্টগ্রাম": ("Chittagong", "চট্টগ্রাম"), "chittagong": ("Chittagong", "চট্টগ্রাম"), "chattogram": ("Chittagong", "চট্টগ্রাম"),
    "কক্সবাজার": ("Cox's Bazar", "কক্সবাজার"), "coxsbazar": ("Cox's Bazar", "কক্সবাজার"), "cox's bazar": ("Cox's Bazar", "কক্সবাজার"),
    "কুমিল্লা": ("Comilla", "কুমিল্লা"), "comilla": ("Comilla", "কুমিল্লা"), "cumilla": ("Comilla", "কুমিল্লা"),
    "ব্রাহ্মণবাড়িয়া": ("Brahmanbaria", "ব্রাহ্মণবাড়িয়া"), "brahmanbaria": ("Brahmanbaria", "ব্রাহ্মণবাড়িয়া"),
    "চাঁদপুর": ("Chandpur", "চাঁদপুর"), "chandpur": ("Chandpur", "চাঁদপুর"),
    "লক্ষ্মীপুর": ("Lakshmipur", "লক্ষ্মীপুর"), "lakshmipur": ("Lakshmipur", "লক্ষ্মীপুর"),
    "নোয়াখালী": ("Noakhali", "নোয়াখালী"), "noakhali": ("Noakhali", "নোয়াখালী"),
    "ফেনী": ("Feni", "ফেনী"), "feni": ("Feni", "ফেনী"),
    "খাগড়াছড়ি": ("Khagrachhari", "খাগড়াছড়ি"), "khagrachhari": ("Khagrachhari", "খাগড়াছড়ি"),
    "রাঙ্গামাটি": ("Rangamati", "রাঙ্গামাটি"), "rangamati": ("Rangamati", "রাঙ্গামাটি"),
    "বান্দরবান": ("Bandarban", "বান্দরবান"), "bandarban": ("Bandarban", "বান্দরবান"),
    "খুলনা": ("Khulna", "খুলনা"), "khulna": ("Khulna", "খুলনা"),
    "যশোর": ("Jessore", "যশোর"), "jessore": ("Jessore", "যশোর"), "jashore": ("Jessore", "যশোর"),
    "সাতক্ষীরা": ("Satkhira", "সাতক্ষীরা"), "satkhira": ("Satkhira", "সাতক্ষীরা"),
    "বাগেরহাট": ("Bagerhat", "বাগেরহাট"), "bagerhat": ("Bagerhat", "বাগেরহাট"),
    "কুষ্টিয়া": ("Kushtia", "কুষ্টিয়া"), "kushtia": ("Kushtia", "কুষ্টিয়া"),
    "ঝিনাইদহ": ("Jhenaidah", "ঝিনাইদহ"), "jhenaidah": ("Jhenaidah", "ঝিনাইদহ"),
    "চুয়াডাঙ্গা": ("Chuadanga", "চুয়াডাঙ্গা"), "chuadanga": ("Chuadanga", "চুয়াডাঙ্গা"),
    "মেহেরপুর": ("Meherpur", "মেহেরপুর"), "meherpur": ("Meherpur", "মেহেরপুর"),
    "মাগুরা": ("Magura", "মাগুরা"), "magura": ("Magura", "মাগুরা"),
    "নড়াইল": ("Narail", "নড়াইল"), "narail": ("Narail", "নড়াইল"),
    "রাজশাহী": ("Rajshahi", "রাজশাহী"), "rajshahi": ("Rajshahi", "রাজশাহী"),
    "বগুড়া": ("Bogra", "বগুড়া"), "bogra": ("Bogra", "বগুড়া"), "bogura": ("Bogra", "বগুড়া"),
    "পাবনা": ("Pabna", "পাবনা"), "pabna": ("Pabna", "পাবনা"),
    "সিরাজগঞ্জ": ("Sirajganj", "সিরাজগঞ্জ"), "sirajganj": ("Sirajganj", "সিরাজগঞ্জ"),
    "নাটোর": ("Natore", "নাটোর"), "natore": ("Natore", "নাটোর"),
    "নওগাঁ": ("Naogaon", "নওগাঁ"), "naogaon": ("Naogaon", "নওগাঁ"),
    "চাঁপাইনবাবগঞ্জ": ("Chapai Nawabganj", "চাঁপাইনবাবগঞ্জ"), "chapainawabganj": ("Chapai Nawabganj", "চাঁপাইনবাবগঞ্জ"),
    "জয়পুরহাট": ("Joypurhat", "জয়পুরহাট"), "joypurhat": ("Joypurhat", "জয়পুরহাট"),
    "সিলেট": ("Sylhet", "সিলেট"), "sylhet": ("Sylhet", "সিলেট"),
    "মৌলভীবাজার": ("Moulvibazar", "মৌলভীবাজার"), "moulvibazar": ("Moulvibazar", "মৌলভীবাজার"),
    "হবিগঞ্জ": ("Habiganj", "হবিগঞ্জ"), "habiganj": ("Habiganj", "হবিগঞ্জ"),
    "সুনামগঞ্জ": ("Sunamganj", "সুনামগঞ্জ"), "sunamganj": ("Sunamganj", "সুনামগঞ্জ"),
    "বরিশাল": ("Barisal", "বরিশাল"), "barisal": ("Barisal", "বরিশাল"), "barishal": ("Barisal", "বরিশাল"),
    "পটুয়াখালী": ("Patuakhali", "পটুয়াখালী"), "patuakhali": ("Patuakhali", "পটুয়াখালী"),
    "ভোলা": ("Bhola", "ভোলা"), "bhola": ("Bhola", "ভোলা"),
    "পিরোজপুর": ("Pirojpur", "পিরোজপুর"), "pirojpur": ("Pirojpur", "পিরোজপুর"),
    "বরগুনা": ("Barguna", "বরগুনা"), "barguna": ("Barguna", "বরগুনা"),
    "ঝালকাঠি": ("Jhalokati", "ঝালকাঠি"), "jhalokati": ("Jhalokati", "ঝালকাঠি"),
    "রংপুর": ("Rangpur", "রংপুর"), "rangpur": ("Rangpur", "রংপুর"),
    "দিনাজপুর": ("Dinajpur", "দিনাজপুর"), "dinajpur": ("Dinajpur", "দিনাজপুর"),
    "কুড়িগ্রাম": ("Kurigram", "কুড়িগ্রাম"), "kurigram": ("Kurigram", "কুড়িগ্রাম"),
    "গাইবান্ধা": ("Gaibandha", "গাইবান্ধা"), "gaibandha": ("Gaibandha", "গাইবান্ধা"),
    "নীলফামারী": ("Nilphamari", "নীলফামারী"), "nilphamari": ("Nilphamari", "নীলফামারী"),
    "লালমনিরহাট": ("Lalমনিরহাট", "লালমনিরহাট"), "lalmonirhat": ("Lalmonirhat", "লালমনিরহাট"),
    "পঞ্চগড়": ("Panchagarh", "পঞ্চগড়"), "panchagarh": ("Panchagarh", "পঞ্চগড়"),
    "ঠাকুরগাঁও": ("Thakurgaon", "ঠাকুরগাঁও"), "thakurgaon": ("Thakurgaon", "ঠাকুরগাঁও"),
    "ময়মনসিংহ": ("Mymensingh", "ময়মনসিংহ"), "mymensingh": ("Mymensingh", "ময়মনসিংহ"),
    "জামালপুর": ("Jamalpur", "জামালপুর"), "jamalpur": ("Jamalpur", "জামালপুর"),
    "শেরপুর": ("Sherpur", "শেরপুর"), "sherpur": ("Sherpur", "শেরপুর"),
    "নেত্রকোনা": ("Netrokona", "নেত্রকোনা"), "netrokona": ("Netrokona", "নেত্রকোনা"),
}
BD_DISTRICT_MAP["লালমনিরহাট"] = ("Lalmonirhat", "লালমনিরহাট")


def fetch_prayer_times_for_location(query_place: str) -> str:
    """
    Fetches accurate daily prayer, Sehri & Iftar times for ANY of Bangladesh's 64 districts
    or any world city (supports both Bangla and English input).
    """
    raw = (query_place or "").strip()
    key = raw.lower()
    if key in BD_DISTRICT_MAP:
        city_en, city_bn = BD_DISTRICT_MAP[key]
    elif raw in BD_DISTRICT_MAP:
        city_en, city_bn = BD_DISTRICT_MAP[raw]
    else:
        city_en, city_bn = raw, raw

    today_str = datetime.date.today().strftime("%d-%m-%Y")
    timings = None

    # 1. Try Open-Meteo geocoding first for exact latitude/longitude of any district/upazila
    try:
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search?"
            f"name={urllib.parse.quote(city_en)}&count=1&language=en&format=json"
        )
        g_resp = requests.get(geo_url, timeout=10)
        if g_resp.status_code == 200 and g_resp.json().get("results"):
            loc = g_resp.json()["results"][0]
            lat, lon = loc["latitude"], loc["longitude"]
            t_url = f"https://api.aladhan.com/v1/timings/{today_str}?latitude={lat}&longitude={lon}&method=1&school=1"
            t_resp = requests.get(t_url, timeout=12)
            if t_resp.status_code == 200:
                timings = t_resp.json()["data"]["timings"]
    except Exception as e:
        logger.warning(f"Coordinate prayer lookup fallback: {e}")

    # 2. Fallback to Aladhan timingsByCity
    if not timings:
        url = (
            f"https://api.aladhan.com/v1/timingsByCity/{today_str}"
            f"?city={urllib.parse.quote(city_en)}&country=Bangladesh&method=1&school=1"
        )
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        timings = resp.json()["data"]["timings"]

    imsak = format_12h(timings.get("Imsak", timings["Fajr"]))
    fajr = format_12h(timings["Fajr"])
    sunrise = format_12h(timings["Sunrise"])
    dhuhr = format_12h(timings["Dhuhr"])
    asr = format_12h(timings["Asr"])
    maghrib = format_12h(timings["Maghrib"])
    isha = format_12h(timings["Isha"])

    return (
        f"🕌 <b>আজকের নামাজ ও সাহরি-ইফতারের সময়সূচী</b>\n"
        f"{DIVIDER}\n"
        f"📍 <b>জেলা / শহর:</b> {html.escape(city_bn)} ({html.escape(city_en)})\n"
        f"📅 <b>তারিখ:</b> {today_str} (ইসলামিক ফাউন্ডেশন ও হানাফী মেথড)\n\n"
        f"<blockquote>"
        f"🌙 <b>সাহরির শেষ সময়:</b> {imsak}\n"
        f"🌅 <b>ফজর (Fajr):</b> {fajr}\n"
        f"☀️ <b>সূর্যোদয় (Sunrise):</b> {sunrise}\n"
        f"🌞 <b>যোহর (Dhuhr):</b> {dhuhr}\n"
        f"🌤️ <b>আসর (Asr):</b> {asr}\n"
        f"🌇 <b>মাগরিব ও ইফতার:</b> {maghrib}\n"
        f"🌃 <b>ইশা (Isha):</b> {isha}"
        f"</blockquote>\n\n"
        f"💡 <i>অন্য যেকোনো জেলার নাম (বাংলায় বা ইংরেজিতে, যেমন: যশোর, কুমিল্লা, বগুড়া, কক্সবাজার) লিখে পাঠালেই সাথে সাথে সেই জেলার সময়সূচী দেখতে পাবেন!</i>"
    )

SEVEN_DUAS = [
    {
        "title": "১. দুনিয়া ও আখেরাতের কল্যাণের দোয়া",
        "arabic": "رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ",
        "bangla": "হে আমাদের পালনকর্তা! আমাদের দুনিয়াতে কল্যাণ দান করুন এবং আখেরাতেও কল্যাণ দান করুন এবং আমাদের জাহান্নামের আজাব থেকে রক্ষা করুন। (সূরা বাকারা: ২০১)",
    },
    {
        "title": "২. জ্ঞান বৃদ্ধির দোয়া",
        "arabic": "رَّبِّ زِدْنِي عِلْمًا",
        "bangla": "হে আমার প্রতিপালক! আমার জ্ঞান বৃদ্ধি করে দিন। (সূরা ত্বহা: ১১৪)",
    },
    {
        "title": "৩. পিতা-মাতার জন্য দোয়া",
        "arabic": "رَّبِّ ارْحَمْهُمَا كَمَا رَبَّيَانِي صَغِيرًا",
        "bangla": "হে আমার রব! তাদের উভয়ের প্রতি রহম করুন, যেমন তারা শৈশবে আমাকে লালন-পালন করেছেন। (সূরা বনী ইসরাঈল: ২৪)",
    },
    {
        "title": "৪. বিপদ মুক্তির দোয়া (দোয়া ইউনুস)",
        "arabic": "لَا إِلَٰهَ إِلَّا أَنتَ سُبْحَانَكَ إِنِّي كُنتُ مِنَ الظَّالِمِينَ",
        "bangla": "তুমি ছাড়া কোনো উপাস্য নেই; তুমি পবিত্র মহান! নিশ্চয়ই আমি সীমালঙ্ঘনকারীদের অন্তর্ভুক্ত ছিলাম। (সূরা আম্বিয়া: ৮৭)",
    },
    {
        "title": "৫. ক্ষমা প্রার্থনার দোয়া",
        "arabic": "رَبَّنَا ظَلَمْنَا أَنفُسَنَا وَإِن لَّمْ تَغْفِرْ لَنَا وَتَرْحَمْنَا لَنَكُونَنَّ مِنَ الْخَاسِرِينَ",
        "bangla": "হে আমাদের রব! আমরা নিজেদের ওপর জুলুম করেছি। যদি আপনি আমাদের ক্ষমা না করেন ও দয়া না করেন, তবে আমরা অবশ্যই ক্ষতিগ্রস্তদের অন্তর্ভুক্ত হব। (সূরা আরাফ: ২৩)",
    },
    {
        "title": "৬. অন্তর স্থির রাখার দোয়া",
        "arabic": "يَا مُقَلِّبَ الْقُلُوبِ ثَبِّتْ قَلْبِي عَلَى دِينِكَ",
        "bangla": "হে অন্তরসমূহের পরিবর্তনকারী! আমার অন্তরকে আপনার দ্বীনের ওপর অবিচল রাখুন। (তিরমিজি: ২১৪০)",
    },
    {
        "title": "৭. সুস্বাস্থ্য ও নিরাপত্তা লাভের দোয়া",
        "arabic": "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ",
        "bangla": "হে আল্লাহ! আমি আপনার কাছে দুনিয়া ও আখেরাতে ক্ষমা এবং নিরাপত্তা ও সুস্বাস্থ্য প্রার্থনা করছি। (ইবনে মাজাহ: ৩৮৭১)",
    },
]


# ---------------------------------------------------------------------------
# ABOUT & HELP TEXTS (STYLISH & PROFESSIONAL)
# ---------------------------------------------------------------------------
ABOUT_TEXT = (
    "ℹ️ <b>বট পরিচিতি ও সকল বাটনের কাজ (About)</b>\n"
    f"{DIVIDER}\n"
    "✨ <b>AI ও মিডিয়া টুলস:</b>\n"
    "<blockquote>"
    "১. <b>🤖 AI চ্যাট</b> — স্মার্ট বাংলা AI-এর সাথে কথোপকথন (৮টি মেসেজ হিস্ট্রি মনে রাখে)\n"
    "২. <b>🎙️ Voice বানান</b> — যেকোনো লেখা থেকে বাংলা (নারী/পুরুষ) ও ইংরেজি ভয়েস তৈরি\n"
    "৩. <b>🎤 Voice → Text</b> — ভয়েস মেসেজ থেকে অটোমেটিক বাংলা/ইংরেজি টেক্সট রূপান্তর\n"
    "৪. <b>🖼️ AI ছবি</b> — ১০০% লোগো ও ওয়াটারমার্ক-মুক্ত HD ছবি তৈরি\n"
    "৫. <b>📥 ভিডিও ডাউনলোড</b> — TikTok ও Instagram ভিডিও দ্রুত ডাউনলোড\n"
    "৬. <b>🌐 অনুবাদ</b> — বাংলা ↔ English নিখুঁত অনুবাদ\n"
    "৭. <b>✍️ Caption বানান</b> — ইমোজি ও হ্যাশট্যাগসহ ৫টি ভাইরাল বাংলা ক্যাপশন\n"
    "৮. <b>📖 গল্প / কবিতা</b> — যেকোনো টপিকে বাংলা গল্প বা কবিতা রচনা"
    "</blockquote>\n\n"
    "📂 <b>ডকুমেন্ট ও প্রোডাক্টিভিটি টুলস:</b>\n"
    "<blockquote>"
    "৯. <b>🖼️ ছবি → PDF</b> — একাধিক ছবি একত্র করে PDF ফাইল তৈরি\n"
    "১০. <b>📄 PDF Summary</b> — যেকোনো PDF ফাইলের বাংলা মূল সারাংশ\n"
    "১১. <b>🕐 নামাজের সময়</b> — ৬টি বিভাগের আজকের নামাজের সঠিক সময়সূচী\n"
    "১২. <b>🌦️ আবহাওয়া</b> — যেকোনো শহরের লাইভ তাপমাত্রা ও আবহাওয়ার খবর\n"
    "১৩. <b>💱 কারেন্সি</b> — ডলার, টাকা, রুপি, ইউরো, রিয়াল ইত্যাদির লাইভ রেট\n"
    "১৪. <b>🔗 লিংক ছোট করুন</b> — বড় লিংক মুহূর্তেই ছোট (Short URL) করা\n"
    "১৫. <b>📚 ডিকশনারি</b> — ইংরেজি শব্দের বাংলা অর্থ, উচ্চারণ ও উদাহরণ\n"
    "১৬. <b>😂 জোকস</b> — মজার বাংলা ও ইংরেজি জোকস\n"
    "১৭. <b>⚖️ BMI হিসাব</b> — ওজন ও উচ্চতা দিয়ে স্বাস্থ্য ও BMI রিপোর্ট\n"
    "১৮. <b>🔳 QR বানান</b> — যেকোনো টেক্সট বা লিংকের হাই-কোয়ালিটি QR Code\n"
    "১৯. <b>📰 আজকের খবর</b> — Google News থেকে শীর্ষ ৫টি তাজা বাংলা খবর\n"
    "২০. <b>🪙 ক্রিপ্টো দাম</b> — BTC, ETH, BNB, SOL ইত্যাদির লাইভ USD ও BDT দাম\n"
    "২১. <b>🎂 বয়স হিসাব</b> — জন্ম তারিখ থেকে বছর, মাস ও দিনের নিখুঁত হিসাব\n"
    "২২. <b>🔄 ইউনিট কনভার্ট</b> — কেজি-পাউন্ড, কিমি-মাইল, ফুট-মিটার ইত্যাদি রূপান্তর\n"
    "২৩. <b>✨ ফ্যান্সি টেক্সট</b> — নাম বা লেখাকে স্টাইলিশ ইউনিকোড ফন্টে রূপান্তর\n"
    "২৪. <b>❤️ Love ক্যালকুলেটর</b> — দুটি নাম দিয়ে মজার ভালোবাসার পার্সেন্টেজ\n"
    "২৫. <b>🗜️ ছবি কমপ্রেস</b> — ছবির মান ঠিক রেখে ফাইল সাইজ কমানো\n"
    "২৬. <b>🎵 গানের লিরিক্স</b> — গানের তথ্য, সারমর্ম ও সংক্ষিপ্ত অংশ\n"
    "২৭. <b>🔐 পাসওয়ার্ড</b> — ৮, ১২ বা ১৬ অক্ষরের শক্তিশালী পাসওয়ার্ড তৈরি\n"
    "২৮. <b>🤲 আজকের দোয়া</b> — আরবি ও বাংলা অর্থসহ প্রতিদিন একটি মাসনুন দোয়া\n"
    "২৯. <b>⏰ রিমাইন্ডার</b> — নির্দিষ্ট সময় পর কাজের কথা মনে করিয়ে দেওয়ার অ্যালার্ম\n"
    "৩০. <b>🧠 কুইজ খেলুন</b> — ৫টি বাংলা সাধারণ জ্ঞানের কুইজ খেলে পয়েন্ট অর্জন\n"
    "৩১. <b>📝 বানান ও Grammar</b> — বাংলা বা ইংরেজি বাক্যের বানান ও গ্রামার সংশোধন\n"
    "৩২. <b>📧 ইমেইল / আবেদনপত্র</b> — প্রফেশনাল ইমেইল, দরখাস্ত ও CV কভার লেটার তৈরি\n"
    "৩৩. <b>💻 কোড জেনারেটর</b> — যেকোনো প্রোগ্রামিং কোড লেখা ও বাগ ফিক্স করা\n"
    "৩৪. <b>🪪 স্টাইলিশ বায়ো</b> — FB, Insta ও Telegram প্রোফাইলের জন্য ভিআইপি বায়ো\n"
    "৩৫. <b>🌙 স্বপ্ন ও ইসলামিক প্রশ্ন</b> — কুরআন ও হাদিসের আলোকে ইসলামিক প্রশ্নোত্তর\n"
    "৩৬. <b>🧮 অংক ও বিজ্ঞান সমাধান</b> — যেকোনো গাণিতিক বা বিজ্ঞানের প্রশ্নের ধাপে ধাপে সমাধান\n"
    "৩৭. <b>🩸 রক্তের গ্রুপ গাইড</b> — কোন রক্তের গ্রুপ কাকে রক্ত দিতে ও নিতে পারে তার পূর্ণাঙ্গ চার্ট\n"
    "৩৮. <b>🥗 ডায়েট ও স্বাস্থ্য চার্ট</b> — ওজন কমানো বা বাড়ানোর দেশি খাবারের পূর্ণাঙ্গ ডায়েট প্ল্যান\n"
    "৩৯. <b>💼 বিজনেস আইডিয়া</b> — কম পুঁজিতে ব্যবসা, স্টার্টআপ ও পেজের ইউনিক নাম আইডিয়া\n"
    "৪০. <b>🎬 মুভি রিকমেন্ডেশন</b> — আপনার পছন্দের জনরা অনুযায়ী সেরা মুভি ও সিরিজের তালিকা"
    "</blockquote>\n\n"
    "🎁 <b>শপ, প্রোফাইল ও কন্ট্রোল:</b>\n"
    "<blockquote>"
    "৩৭. <b>🛍️ শপ</b> — বট স্টোর থেকে পণ্য দেখা ও অর্ডার করা\n"
    "৩৮. <b>📩 Contact Admin</b> — সরাসরি অ্যাডমিনের সাথে মেসেজে কথা বলা\n"
    "৩৯. <b>👤 প্রোফাইল</b> — নিজের পয়েন্ট, লেভেল, র‍্যাংক ও রেফারেল লিংক\n"
    "৪০. <b>🏆 লিডারবোর্ড</b> — সর্বকালের সেরা ১০ ও সাপ্তাহিক সেরা ৫ জনের তালিকা\n"
    "৪১. <b>🎁 ডেইলি বোনাস</b> — প্রতিদিন ফ্রি +৫ পয়েন্ট বোনাস\n"
    "৪২. <b>🎰 স্পিন</b> — প্রতিদিন লাকি স্পিনে ১–৫০ পয়েন্ট জয়ের সুযোগ\n"
    "৪৩. <b>👥 রেফার করুন</b> — বন্ধু আমন্ত্রণ জানিয়ে প্রতি রেফারে +১০ পয়েন্ট\n"
    "৪৪. <b>ℹ️ About</b> — বটের সকল বাটনের বিস্তারিত তালিকা\n"
    "৪৫. <b>❓ Help</b> — বট ব্যবহারের গাইডলাইন ও নিয়মাবলী\n"
    "৪৬. <b>👨💻 Developer</b> — বট নির্মাতার পরিচিতি\n"
    "৪৭. <b>🛠️ Admin Panel</b> — অ্যাডমিনদের জন্য সরাসরি কন্ট্রোল প্যানেল বাটন\n"
    "৪৮. <b>🏠 মেনু</b> — যেকোনো টুল থেকে মূল মেনুতে ফিরে আসা"
    "</blockquote>"
)

HELP_TEXT = (
    "❓ <b>সাহায্য ও ব্যবহারের নিয়মাবলী (Help Guide)</b>\n"
    f"{DIVIDER}\n"
    "🧭 <b>কীভাবে ব্যবহার করবেন?</b>\n"
    "<blockquote>নিচের মেনু কিবোর্ড থেকে আপনার পছন্দের যেকোনো বাটনে ট্যাপ করুন। বট আপনাকে কী পাঠাতে হবে তা বলে দেবে—আপনি টেক্সট, লিংক, ভয়েস বা ছবি পাঠালেই সাথে সাথে সুন্দর ফলাফল পেয়ে যাবেন!</blockquote>\n\n"
    "💎 <b>পয়েন্ট ও রিওয়ার্ড সিস্টেম:</b>\n"
    "<blockquote>"
    "• 🛠️ প্রতিবার টুল ব্যবহারে: <b>+১ পয়েন্ট</b>\n"
    "• 🎁 ডেইলি বোনাস: <b>+৫ পয়েন্ট</b> (প্রতিদিন ১ বার)\n"
    "• 🎰 ডেইলি লাকি স্পিন: <b>১ থেকে ৫০ পয়েন্ট</b>\n"
    "• 👥 প্রতি সফল রেফারে: <b>+১০ পয়েন্ট</b>\n"
    "• 🧠 কুইজে সঠিক উত্তরে: <b>+৫ পয়েন্ট</b> (টানা ৩টি সঠিক হলে +২ বোনাস)"
    "</blockquote>\n\n"
    "🏅 <b>ইউজার লেভেলসমূহ:</b>\n"
    "<blockquote>"
    "• 🥉 <b>Bronze:</b> ০ – ৪৯ পয়েন্ট\n"
    "• 🥈 <b>Silver:</b> ৫০ – ১৪৯ পয়েন্ট\n"
    "• 🥇 <b>Gold:</b> ১৫০ – ৩৯৯ পয়েন্ট\n"
    "• 💎 <b>Diamond:</b> ৪০০+ পয়েন্ট"
    "</blockquote>\n\n"
    "⌨️ <b>শর্টকাট কমান্ড:</b>\n"
    "• <code>/start</code> — বট রিস্টার্ট ও মূল মেনু\n"
    "• <code>/help</code> — ব্যবহারের নির্দেশিকা\n"
    "• <code>/myid</code> — আপনার টেলিগ্রাম আইডি দেখুন\n"
    "• <code>/admin</code> — অ্যাডমিন প্যানেল (শুধুমাত্র অ্যাডমিন)\n\n"
    "💡 <i>যেকোনো চলমান কাজ বাতিল করতে নিচের <b>🏠 মেনু</b> বাটনে চাপুন।</i>"
)


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS FOR TOOLS
# ---------------------------------------------------------------------------
URL_REGEX = re.compile(r"(https?://[^\s<>\"']+)", re.IGNORECASE)


def extract_first_url(text: str) -> Optional[str]:
    m = URL_REGEX.search(text or "")
    return m.group(1) if m else None


def format_12h(time_24: str) -> str:
    clean = time_24.split(" ")[0].strip()
    try:
        dt = datetime.datetime.strptime(clean, "%H:%M")
        return dt.strftime("%I:%M %p")
    except Exception:
        return clean


WEATHER_CODE_MAP = {
    0: "☀️ পরিষ্কার আকাশ (Clear Sky)",
    1: "🌤️ মূলত পরিষ্কার (Mainly Clear)",
    2: "⛅ আংশিক মেঘলা (Partly Cloudy)",
    3: "☁️ মেঘলা (Overcast)",
    45: "🌫️ কুয়াশা (Fog)",
    48: "🌫️ ঘন কুয়াশা (Rime Fog)",
    51: "🌦️ হালকা গুঁড়ি গুঁড়ি বৃষ্টি (Light Drizzle)",
    53: "🌦️ মাঝারি গুঁড়ি গুঁড়ি বৃষ্টি (Moderate Drizzle)",
    55: "🌧️ ঘন গুঁড়ি গুঁড়ি বৃষ্টি (Dense Drizzle)",
    61: "🌧️ হালকা বৃষ্টি (Slight Rain)",
    63: "🌧️ মাঝারি বৃষ্টি (Moderate Rain)",
    65: "🌧️ ভারী বৃষ্টি (Heavy Rain)",
    71: "❄️ হালকা তুষারপাত (Slight Snow)",
    73: "❄️ মাঝারি তুষারপাত (Moderate Snow)",
    75: "❄️ ভারী তুষারপাত (Heavy Snow)",
    80: "🌦️ হালকা দমকা বৃষ্টি (Rain Showers)",
    81: "🌧️ মাঝারি দমকা বৃষ্টি (Moderate Showers)",
    82: "⛈️ প্রবল বর্ষণ (Violent Showers)",
    95: "⛈️ বজ্রসহ বৃষ্টি (Thunderstorm)",
    96: "⛈️ শিলাবৃষ্টিসহ ঝড় (Thunderstorm with Hail)",
    99: "⛈️ তীব্র শিলাবৃষ্টিসহ ঝড় (Heavy Hail Storm)",
}


def fetch_weather_info(city: str) -> str:
    city_clean = city.strip()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BigBot/1.0)"}

    for attempt in range(3):
        try:
            geo_url = (
                f"https://geocoding-api.open-meteo.com/v1/search?"
                f"name={urllib.parse.quote(city_clean)}&count=1&language=en&format=json"
            )
            g_resp = requests.get(geo_url, headers=headers, timeout=10)
            if g_resp.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            g_resp.raise_for_status()
            g_data = g_resp.json()
            results = g_data.get("results")
            if not results:
                break

            loc = results[0]
            lat = loc["latitude"]
            lon = loc["longitude"]
            resolved_name = loc.get("name", city_clean)
            country = loc.get("country", "")

            fc_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            )
            f_resp = requests.get(fc_url, headers=headers, timeout=10)
            if f_resp.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            f_resp.raise_for_status()
            cur = f_resp.json().get("current", {})
            temp = cur.get("temperature_2m", "N/A")
            hum = cur.get("relative_humidity_2m", "N/A")
            wcode = int(cur.get("weather_code", 0))
            wind = cur.get("wind_speed_10m", "N/A")
            cond = WEATHER_CODE_MAP.get(wcode, "🌤️ স্বাভাবিক আবহাওয়া")

            return (
                f"🌦️ <b>আবহাওয়ার লাইভ রিপোর্ট</b>\n"
                f"{DIVIDER}\n"
                f"📍 <b>শহর:</b> {html.escape(resolved_name)}, {html.escape(country)}\n\n"
                f"<blockquote>"
                f"🌡️ <b>তাপমাত্রা:</b> {temp}°C\n"
                f"💧 <b>আর্দ্রতা:</b> {hum}%\n"
                f"🌬️ <b>বাতাসের গতি:</b> {wind} km/h\n"
                f"☁️ <b>অবস্থা:</b> {cond}"
                f"</blockquote>"
            )
        except Exception as e:
            logger.warning(f"Open-Meteo attempt {attempt + 1} failed: {e}")
            time.sleep(1.2 * (attempt + 1))

    wttr_url = f"https://wttr.in/{urllib.parse.quote(city_clean)}?format=j1"
    w_resp = requests.get(wttr_url, headers=headers, timeout=15)
    w_resp.raise_for_status()
    w_data = w_resp.json()
    cur_list = w_data.get("current_condition", [])
    if not cur_list:
        raise ValueError("No weather data returned.")
    cur = cur_list[0]
    temp_c = cur.get("temp_C", "N/A")
    humidity = cur.get("humidity", "N/A")
    wind_kmph = cur.get("windspeedKmph", "N/A")
    desc_list = cur.get("weatherDesc", [{"value": "Clear"}])
    desc = desc_list[0].get("value", "Clear") if desc_list else "Clear"

    return (
        f"🌦️ <b>আবহাওয়ার লাইভ রিপোর্ট</b>\n"
        f"{DIVIDER}\n"
        f"📍 <b>শহর:</b> {html.escape(city_clean)}\n\n"
        f"<blockquote>"
        f"🌡️ <b>তাপমাত্রা:</b> {temp_c}°C\n"
        f"💧 <b>আর্দ্রতা:</b> {humidity}%\n"
        f"🌬️ <b>বাতাসের গতি:</b> {wind_kmph} km/h\n"
        f"☁️ <b>অবস্থা:</b> 🌤️ {html.escape(desc)}"
        f"</blockquote>"
    )


CURRENCY_WORD_MAP = {
    "dollar": "USD",
    "usd": "USD",
    "ডলার": "USD",
    "taka": "BDT",
    "bdt": "BDT",
    "tk": "BDT",
    "টাকা": "BDT",
    "rupee": "INR",
    "inr": "INR",
    "রুপি": "INR",
    "pound": "GBP",
    "gbp": "GBP",
    "পাউন্ড": "GBP",
    "euro": "EUR",
    "eur": "EUR",
    "ইউরো": "EUR",
    "riyal": "SAR",
    "sar": "SAR",
    "রিয়াল": "SAR",
    "dirham": "AED",
    "aed": "AED",
    "দিরহাম": "AED",
}


def convert_currency_input(raw_text: str) -> str:
    text = bn_to_en_digits(raw_text.strip().lower())
    num_match = re.search(r"(\d+(?:\.\d+)?)", text)
    amount = float(num_match.group(1)) if num_match else 1.0

    tokens = re.findall(r"[a-zA-Z\u0980-\u09FF]+", text)
    codes: List[str] = []
    for t in tokens:
        if t in ("to", "in", "into", "থেকে", "তে"):
            continue
        if t in CURRENCY_WORD_MAP:
            codes.append(CURRENCY_WORD_MAP[t])
        elif len(t) == 3 and t.isalpha():
            codes.append(t.upper())

    src = codes[0] if len(codes) >= 1 else "USD"
    dst = codes[1] if len(codes) >= 2 else ("USD" if src == "BDT" else "BDT")

    url = f"https://open.er-api.com/v6/latest/{src}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    rates = data.get("rates", {})
    if dst not in rates:
        raise ValueError(f"Unsupported currency code: {dst}")

    rate = float(rates[dst])
    converted = amount * rate
    extra_lines = []
    if "BDT" in rates and dst != "BDT":
        bdt_val = amount * float(rates["BDT"])
        extra_lines.append(f"🇧🇩 <b>বাংলাদেশী টাকায়:</b> {bdt_val:,.2f} BDT")
    elif src == "BDT" and len(codes) == 1 and "USD" in rates:
        extra_lines.append(f"🇪🇺 <b>EUR:</b> {amount * float(rates.get('EUR', 0)):,.2f} EUR")
        extra_lines.append(f"🇮🇳 <b>INR:</b> {amount * float(rates.get('INR', 0)):,.2f} INR")

    extra_block = ("\n" + "\n".join(extra_lines)) if extra_lines else ""
    return (
        f"💱 <b>কারেন্সি কনভার্টার (Live Rate)</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>"
        f"💵 <b>{amount:,.2f} {src} = {converted:,.2f} {dst}</b>\n"
        f"📊 <b>বিনিময় হার:</b> 1 {src} = {rate:,.4f} {dst}"
        f"{extra_block}"
        f"</blockquote>"
    )


def calculate_bmi_response(raw_text: str) -> str:
    text = bn_to_en_digits(raw_text)
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if len(nums) < 2:
        return (
            "⚠️ <b>সঠিক ফরম্যাটে ওজন এবং উচ্চতা পাঠান!</b>\n\n"
            "<blockquote>উদাহরণ: <code>70 5.7</code> অথবা <code>70 kg 5.7</code></blockquote>"
        )

    weight_kg = float(nums[0])
    height_raw = nums[1]

    if "." in height_raw:
        parts = height_raw.split(".", 1)
        feet = int(parts[0])
        inches_str = parts[1]
        inches = int(inches_str) if inches_str else 0
    else:
        val = float(height_raw)
        if val > 10:
            total_inches = val / 2.54
            feet = int(total_inches // 12)
            inches = int(round(total_inches % 12))
        else:
            feet = int(val)
            inches = 0

    total_inches = (feet * 12) + inches
    if total_inches <= 0 or weight_kg <= 0:
        return "⚠️ ওজন এবং উচ্চতা অবশ্যই শূন্যের বেশি হতে হবে।"

    height_m = total_inches * 0.0254
    bmi = weight_kg / (height_m ** 2)

    if bmi < 18.5:
        cat = "কম ওজন (Underweight) 🟡"
        advice = "পুষ্টিকর খাবার গ্রহণ করুন এবং সুষম খাদ্যতালিকা মেনে ওজন বাড়ানোর চেষ্টা করুন।"
    elif bmi < 25.0:
        cat = "স্বাভাবিক ওজন (Normal) 🟢"
        advice = "অভিনন্দন! আপনার ওজন ও উচ্চতার অনুপাত একদম সঠিক আছে।"
    elif bmi < 30.0:
        cat = "অতিরিক্ত ওজন (Overweight) 🟠"
        advice = "নিয়মিত হাঁটাহাঁটি ও ব্যায়াম করুন এবং অতিরিক্ত চর্বিযুক্ত খাবার এড়িয়ে চলুন।"
    else:
        cat = "স্থূলতা (Obese) 🔴"
        advice = "স্বাস্থ্যঝুঁকি এড়াতে ডায়েট নিয়ন্ত্রণ করুন এবং প্রয়োজনে চিকিৎসকের পরামর্শ নিন।"

    return (
        f"⚖️ <b>আপনার BMI ও স্বাস্থ্য রিপোর্ট</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>"
        f"• <b>ওজন:</b> {weight_kg:g} কেজি\n"
        f"• <b>উচ্চতা:</b> {feet} ফুট {inches} ইঞ্চি ({height_m:.2f} মিটার)\n"
        f"• <b>আপনার BMI:</b> {bmi:.2f}\n"
        f"• <b>শারীরিক অবস্থা:</b> {cat}"
        f"</blockquote>\n\n"
        f"💡 <b>পরামর্শ:</b> <i>{advice}</i>"
    )


def convert_unit_input(raw_text: str) -> str:
    text = bn_to_en_digits(raw_text.strip().lower())
    m = re.search(
        r"(-?\d+(?:\.\d+)?)\s*([a-zA-Z°\u0980-\u09FF]+)\s*(?:to|in|into|থেকে|=)\s*([a-zA-Z°\u0980-\u09FF]+)",
        text,
    )
    if not m:
        return (
            "⚠️ <b>সঠিক ফরম্যাটে লিখুন!</b>\n\n"
            "<blockquote>"
            "• <code>10 kg to pound</code>\n"
            "• <code>5 km to mile</code>\n"
            "• <code>37 C to F</code>\n"
            "• <code>5.5 feet to cm</code>"
            "</blockquote>"
        )

    val = float(m.group(1))
    u1_raw = m.group(2).strip("°")
    u2_raw = m.group(3).strip("°")

    alias = {
        "kg": "kg", "kilogram": "kg", "kilo": "kg", "কেজি": "kg",
        "pound": "pound", "pounds": "pound", "lb": "pound", "lbs": "pound", "পাউন্ড": "pound",
        "km": "km", "kilometer": "km", "kilometre": "km", "কিমি": "km",
        "mile": "mile", "miles": "mile", "মাইল": "mile",
        "c": "c", "celsius": "c", "সেলসিয়াস": "c",
        "f": "f", "fahrenheit": "f", "ফারেনহাইট": "f",
        "inch": "inch", "inches": "inch", "in": "inch", "ইঞ্চি": "inch",
        "cm": "cm", "centimeter": "cm", "সেমি": "cm",
        "liter": "liter", "litre": "liter", "l": "liter", "লিটার": "liter",
        "gallon": "gallon", "gal": "gallon", "গ্যালন": "gallon",
        "feet": "feet", "foot": "feet", "ft": "feet", "ফুট": "feet",
        "meter": "meter", "metre": "meter", "m": "meter", "মিটার": "meter",
        "gram": "gram", "gm": "gram", "g": "gram", "গ্রাম": "gram",
        "hour": "hour", "hr": "hour", "hrs": "hour", "ঘণ্টা": "hour", "ঘন্টা": "hour",
        "minute": "minute", "min": "minute", "mins": "minute", "মিনিট": "minute",
    }

    u1 = alias.get(u1_raw, u1_raw)
    u2 = alias.get(u2_raw, u2_raw)

    res: Optional[float] = None
    pair = (u1, u2)
    if pair == ("kg", "pound"):
        res = val * 2.20462262
    elif pair == ("pound", "kg"):
        res = val / 2.20462262
    elif pair == ("km", "mile"):
        res = val * 0.621371
    elif pair == ("mile", "km"):
        res = val / 0.621371
    elif pair == ("c", "f"):
        res = (val * 9.0 / 5.0) + 32.0
    elif pair == ("f", "c"):
        res = (val - 32.0) * 5.0 / 9.0
    elif pair == ("inch", "cm"):
        res = val * 2.54
    elif pair == ("cm", "inch"):
        res = val / 2.54
    elif pair == ("liter", "gallon"):
        res = val * 0.264172
    elif pair == ("gallon", "liter"):
        res = val / 0.264172
    elif pair == ("feet", "cm"):
        res = val * 30.48
    elif pair == ("cm", "feet"):
        res = val / 30.48
    elif pair == ("feet", "meter"):
        res = val * 0.3048
    elif pair == ("meter", "feet"):
        res = val / 0.3048
    elif pair == ("kg", "gram"):
        res = val * 1000.0
    elif pair == ("gram", "kg"):
        res = val / 1000.0
    elif pair == ("hour", "minute"):
        res = val * 60.0
    elif pair == ("minute", "hour"):
        res = val / 60.0

    if res is None:
        return (
            "⚠️ <b>এই এককটি সাপোর্ট করে না।</b>\n"
            "<blockquote>সাপোর্টেড একক: kg↔pound, km↔mile, C↔F, inch↔cm, liter↔gallon, "
            "feet↔cm, feet↔meter, meter↔feet, kg↔gram, hour↔minute.</blockquote>"
        )

    return (
        f"🔄 <b>ইউনিট কনভার্টার ফলাফল</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>✅ <b>{val:g} {u1.upper()} = {res:.4g} {u2.upper()}</b></blockquote>"
    )


def generate_fancy_text(text: str) -> str:
    """
    Generates 100% easily readable, clean, modern stylish text variations (no weird unreadable symbols!).
    Also includes stylish frames that work for both Bangla and English names/texts.
    """
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    styles = [
        ("Modern Bold", "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
        ("Classic Bold", "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
        ("Clean Italic", "𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡0123456789"),
        ("Bold Italic", "𝙖𝙗𝙘𝙙𝙚𝙛𝙜𝙝𝙞𝙟𝙠𝙡𝙢𝙣𝙤𝙥𝙦𝙧𝙨𝙩𝙪𝙫𝙬𝙭𝙮𝙯𝘼𝘽𝘾𝘿𝙀𝙁𝙂𝙃𝙄𝙅𝙆𝙇𝙈𝙉𝙊𝙋𝚀𝙍𝙎𝙏𝙐𝙑𝙒𝙓𝙔𝙕0123456789"),
        ("Small Caps", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        ("Monospace", "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"),
    ]

    out = [f"✨ <b>আপনার স্টাইলিশ লেখা (সহজে পড়া যায় এমন ফন্ট)</b>\n{DIVIDER}"]
    lines = []
    for idx, (label, target) in enumerate(styles, 1):
        if len(target) == len(normal):
            table = str.maketrans(normal, target)
            converted = text.translate(table)
        else:
            converted = text
        lines.append(f"{en_to_bn_digits(str(idx))}. <code>{html.escape(converted)}</code>")

    # Readable aesthetic frames (work great for both Bangla & English!)
    lines.append(f"৭. <code>★彡 {html.escape(text)} 彡★</code>")
    lines.append(f"৮. <code>༺👑 {html.escape(text)} 👑༻</code>")
    lines.append(f"৯. <code>❖ ─ {html.escape(text)} ─ ❖</code>")
    lines.append(f"১০. <code>❝ {html.escape(text)} ❞</code>")

    out.append("<blockquote>" + "\n\n".join(lines) + "</blockquote>")
    out.append("👆 <i>যেকোনো লেখার ওপর ট্যাপ করলেই সাথে সাথে কপি হয়ে যাবে!</i>")
    return "\n".join(out)


def calculate_age_response(raw_text: str) -> str:
    text = bn_to_en_digits(raw_text.strip())
    m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text)
    if not m:
        return "⚠️ <b>সঠিক ফরম্যাটে জন্ম তারিখ লিখুন (DD-MM-YYYY)!</b>\n<blockquote>উদাহরণ: <code>15-08-2002</code></blockquote>"

    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        dob = datetime.date(year, month, day)
    except ValueError:
        return "⚠️ অবৈধ তারিখ! অনুগ্রহ করে সঠিক দিন, মাস ও বছর দিন (DD-MM-YYYY)।"

    today = datetime.date.today()
    if dob > today:
        return "⚠️ জন্ম তারিখ ভবিষ্যতের হতে পারে না!"

    years = today.year - dob.year
    months = today.month - dob.month
    days = today.day - dob.day

    if days < 0:
        months -= 1
        prev_month = today.month - 1 or 12
        prev_year = today.year if today.month > 1 else today.year - 1
        days_in_prev_month = (datetime.date(prev_year, prev_month % 12 + 1, 1) - datetime.timedelta(days=1)).day if prev_month != 12 else 31
        days += days_in_prev_month

    if months < 0:
        years -= 1
        months += 12

    total_days = (today - dob).days
    return (
        f"🎂 <b>আপনার নিখুঁত বয়স রিপোর্ট</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>"
        f"📅 <b>জন্ম তারিখ:</b> {dob.strftime('%d-%m-%Y')}\n"
        f"✨ <b>বর্তমান বয়স:</b> <b>{years} বছর, {months} মাস, {days} দিন</b>\n"
        f"⏳ <b>মোট অতিবাহিত দিন:</b> {total_days:,} দিন"
        f"</blockquote>"
    )


def parse_reminder_input(raw_text: str) -> Optional[Tuple[int, str]]:
    text = bn_to_en_digits(raw_text.strip())
    pattern = re.compile(
        r"^\s*(\d+)\s*"
        r"(সেকেন্ড|সেকেন্ডে|sec|second|seconds|"
        r"মিনিট|মিনিটে|min|mins|minute|minutes|"
        r"ঘণ্টা|ঘন্টা|ঘণ্টায়|ঘন্টায়|ghonta|hour|hours|hr|hrs)"
        r"(?:\s+(?:পরে|পর|por|pore|after|later))?\s+(.+)$",
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.match(text)
    if not m:
        return None

    amount = int(m.group(1))
    unit = m.group(2).lower()
    note = m.group(3).strip()

    if amount <= 0 or not note:
        return None

    if unit in ("সেকেন্ড", "সেকেন্ডে", "sec", "second", "seconds"):
        seconds = amount
    elif unit in ("মিনিট", "মিনিটে", "min", "mins", "minute", "minutes"):
        seconds = amount * 60
    else:
        seconds = amount * 3600

    return seconds, note


def fetch_crypto_prices(custom_symbol: Optional[str] = None) -> str:
    """
    5-Engine US/Render-Cloud-Safe Live Crypto Price Fetcher:
    1. Binance Vision Official Public Data Mirror (data-api.binance.vision - NOT blocked on US/Render IPs!)
    2. CryptoCompare Public API
    3. CoinCap Public API
    4. Coinbase Spot Price API
    5. CoinGecko with browser headers
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"}
    usd_to_bdt = 121.5
    try:
        r_fx = requests.get("https://open.er-api.com/v6/latest/USD", headers=headers, timeout=8)
        if r_fx.status_code == 200:
            usd_to_bdt = float(r_fx.json().get("rates", {}).get("BDT", 121.5))
    except Exception:
        pass

    if custom_symbol:
        sym = re.sub(r"[^A-Za-z0-9]", "", custom_symbol.strip()).upper()
        if sym.endswith("USDT") and len(sym) > 4:
            sym = sym[:-4]
        price_usd: Optional[float] = None
        # Try Binance Vision Mirror
        try:
            r = requests.get(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={sym}USDT", headers=headers, timeout=8)
            if r.status_code == 200 and "price" in r.json():
                price_usd = float(r.json()["price"])
        except Exception:
            pass
        # Try CryptoCompare
        if price_usd is None:
            try:
                r = requests.get(f"https://min-api.cryptocompare.com/data/price?fsym={sym}&tsyms=USD", headers=headers, timeout=8)
                if r.status_code == 200 and "USD" in r.json():
                    price_usd = float(r.json()["USD"])
            except Exception:
                pass
        # Try Coinbase
        if price_usd is None:
            try:
                r = requests.get(f"https://api.coinbase.com/v2/prices/{sym}-USD/spot", headers=headers, timeout=8)
                if r.status_code == 200 and "data" in r.json():
                    price_usd = float(r.json()["data"]["amount"])
            except Exception:
                pass
        if price_usd is None:
            return (
                f"⚠️ <b>{html.escape(sym)}</b> কয়েনটির দাম খুঁজে পাওয়া যায়নি।\n"
                "<blockquote>অনুগ্রহ করে সঠিক কয়েন সিম্বল লিখুন (যেমন: <code>BTC</code>, <code>TON</code>, <code>TRX</code>, <code>PEPE</code>, <code>SHIB</code>)।</blockquote>"
            )
        bdt = price_usd * usd_to_bdt
        usd_fmt = f"${price_usd:,.2f}" if price_usd >= 1 else f"${price_usd:.6f}"
        bdt_fmt = f"৳{bdt:,.2f}" if bdt >= 1 else f"৳{bdt:.4f}"
        return (
            f"🪙 <b>{html.escape(sym)}/USD লাইভ বাজারমূল্য</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>"
            f"💵 <b>USD দাম:</b> <code>{usd_fmt}</code>\n"
            f"🇧🇩 <b>বাংলাদেশী টাকায়:</b> <code>{bdt_fmt}</code>\n"
            f"📊 <b>রেট:</b> $1 USD = ৳{usd_to_bdt:,.2f} BDT"
            f"</blockquote>"
        )

    coins = [
        ("bitcoin", "BTC", "BTCUSDT", "Bitcoin (BTC)"),
        ("ethereum", "ETH", "ETHUSDT", "Ethereum (ETH)"),
        ("binance-coin", "BNB", "BNBUSDT", "BNB (BNB)"),
        ("solana", "SOL", "SOLUSDT", "Solana (SOL)"),
        ("the-open-network", "TON", "TONUSDT", "Toncoin (TON)"),
        ("xrp", "XRP", "XRPUSDT", "XRP (XRP)"),
        ("dogecoin", "DOGE", "DOGEUSDT", "Dogecoin (DOGE)"),
        ("tron", "TRX", "TRXUSDT", "TRON (TRX)"),
    ]

    prices_usd: Dict[str, float] = {}

    # Engine 1: CryptoCompare Multi-Price API (Fastest single call, works globally on all cloud IPs)
    try:
        syms = ",".join(c[1] for c in coins)
        cc_url = f"https://min-api.cryptocompare.com/data/pricemulti?fsyms={syms}&tsyms=USD"
        cc_resp = requests.get(cc_url, headers=headers, timeout=8)
        if cc_resp.status_code == 200:
            cc_data = cc_resp.json()
            for _, sym, _, _ in coins:
                if sym in cc_data and "USD" in cc_data[sym]:
                    prices_usd[sym] = float(cc_data[sym]["USD"])
    except Exception as e:
        logger.warning(f"CryptoCompare fallback: {e}")

    # Engine 2: Binance Vision Official Data Mirror (never geo-blocked on Render!)
    if len(prices_usd) < len(coins):
        for _, sym, bin_pair, _ in coins:
            if sym not in prices_usd:
                try:
                    bv_url = f"https://data-api.binance.vision/api/v3/ticker/price?symbol={bin_pair}"
                    bv_resp = requests.get(bv_url, headers=headers, timeout=6)
                    if bv_resp.status_code == 200 and "price" in bv_resp.json():
                        prices_usd[sym] = float(bv_resp.json()["price"])
                except Exception:
                    pass

    # Engine 3: Coinbase Spot API
    if len(prices_usd) < len(coins):
        for _, sym, _, _ in coins:
            if sym not in prices_usd:
                try:
                    cb_url = f"https://api.coinbase.com/v2/prices/{sym}-USD/spot"
                    cb_resp = requests.get(cb_url, headers=headers, timeout=6)
                    if cb_resp.status_code == 200 and "data" in cb_resp.json():
                        prices_usd[sym] = float(cb_resp.json()["data"]["amount"])
                except Exception:
                    pass

    # Engine 4: CoinGecko API with browser headers
    if len(prices_usd) < 4:
        try:
            cg_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,binancecoin,solana,the-open-network,ripple,dogecoin,tron&vs_currencies=usd"
            cg_resp = requests.get(cg_url, headers=headers, timeout=8)
            if cg_resp.status_code == 200:
                cg_data = cg_resp.json()
                cg_map = {
                    "bitcoin": "BTC", "ethereum": "ETH", "binancecoin": "BNB",
                    "solana": "SOL", "the-open-network": "TON", "ripple": "XRP",
                    "dogecoin": "DOGE", "tron": "TRX"
                }
                for cid, sym in cg_map.items():
                    if cid in cg_data and "usd" in cg_data[cid]:
                        prices_usd[sym] = float(cg_data[cid]["usd"])
        except Exception:
            pass

    if not prices_usd:
        raise RuntimeError("Could not fetch crypto prices from any provider.")

    body = []
    for _, sym, _, label in coins:
        if sym in prices_usd:
            usd = prices_usd[sym]
            bdt = usd * usd_to_bdt
            if usd >= 1:
                body.append(f"🪙 <b>{label}</b>\n   💵 <code>${usd:,.2f}</code>  |  🇧🇩 <code>৳{bdt:,.0f}</code>")
            else:
                body.append(f"🪙 <b>{label}</b>\n   💵 <code>${usd:.4f}</code>  |  🇧🇩 <code>৳{bdt:,.2f}</code>")

    now_bd = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=6)).strftime("%I:%M %p, %d-%m-%Y")
    return (
        f"📈 <b>ক্রিপ্টোকারেন্সির লাইভ বাজারমূল্য (Live Market)</b>\n"
        f"{DIVIDER}\n"
        f"🕒 <b>আপডেট সময়:</b> {now_bd} (BDT Time)\n\n"
        f"<blockquote>" + "\n\n".join(body) + "</blockquote>\n\n"
        f"💡 <i>যেকোনো কয়েনের নাম (যেমন: <code>TON</code>, <code>PEPE</code>, <code>SHIB</code>, <code>NOT</code>) লিখে পাঠালে সেটিরও লাইভ দাম দেখতে পাবেন!</i>"
    )


def fetch_google_news_bn(topic: str = "top") -> str:
    """
    Fetches live auto-updating Bangla news from Google News RSS.
    Updates automatically every few minutes, 24 hours a day!
    """
    topic_queries = {
        "top": ("https://news.google.com/rss?hl=bn&gl=BD&ceid=BD:bn", "🔥 আজকের শীর্ষ ব্রেকিং খবর"),
        "bd": ("https://news.google.com/rss/search?q=%E0%A6%AC%E0%A6%BE%E0%A6%82%E0%A6%B2%E0%A6%BE%E0%A6%A6%E0%A7%87%E0%A6%B6&hl=bn&gl=BD&ceid=BD:bn", "🇧🇩 বাংলাদেশ ও জাতীয় খবর"),
        "sports": ("https://news.google.com/rss/search?q=%E0%A6%96%E0%A7%87%E0%A6%B2%E0%A6%BE%E0%A6%A7%E0%A7%81%E0%A6%B2%E0%A6%BE+%E0%A6%95%E0%A7%8D%E0%A6%B0%E0%A6%BF%E0%A6%95%E0%A7%87%E0%A6%9F+%E0%A6%AB%E0%A7%81%E0%A6%9F%E0%A6%AC%E0%A6%B2&hl=bn&gl=BD&ceid=BD:bn", "🏏 খেলাধুলা ও ক্রিকেট খবর"),
        "world": ("https://news.google.com/rss/search?q=%E0%A6%86%E0%A6%A8%E0%A7%8D%E0%A6%A4%E0%A6%B0%E0%A7%8D%E0%A6%9C%E0%A6%BE%E0%A6%A4%E0%A6%BF%E0%A6%95+%E0%A6%AC%E0%A6%BF%E0%A6%B6%E0%A7%8D%E0%A6%AC&hl=bn&gl=BD&ceid=BD:bn", "🌍 আন্তর্জাতিক ও বিশ্ব সংবাদ"),
        "tech": ("https://news.google.com/rss/search?q=%E0%A6%AA%E0%A7%8D%E0%A6%B0%E0%A6%AF%E0%A7%81%E0%A6%95%E0%A7%8D%E0%A6%A4%E0%A6%BF+AI+%E0%A6%9F%E0%A7%87%E0%A6%95%E0%A6%A8%E0%A7%8B%E0%A6%B2%E0%A6%9C%E0%A6%BF&hl=bn&gl=BD&ceid=BD:bn", "💻 প্রযুক্তি ও বিজ্ঞান খবর"),
    }
    url, heading = topic_queries.get(topic, topic_queries["top"])
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = root.findall(".//item")[:7]
    if not items:
        return "📰 বর্তমানে কোনো খবর পাওয়া যায়নি।"

    now_bd = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=6)).strftime("%d-%m-%Y, %I:%M %p")
    lines = [
        f"📰 <b>{heading} (লাইভ আপডেট)</b>\n"
        f"{DIVIDER}\n"
        f"🕒 <b>লাইভ ফিড সময়:</b> {en_to_bn_digits(now_bd)} (প্রতিদিন ২৪ ঘণ্টা অটো-আপডেট)"
    ]
    for idx, item in enumerate(items, 1):
        raw_title = item.findtext("title") or "শিরোনাম নেই"
        link = item.findtext("link") or ""
        source_el = item.find("source")
        source_name = source_el.text if (source_el is not None and source_el.text) else ""
        if " - " in raw_title and not source_name:
            parts = raw_title.rsplit(" - ", 1)
            raw_title, source_name = parts[0], parts[1]
        elif " - " in raw_title and source_name:
            raw_title = raw_title.rsplit(" - ", 1)[0]

        src_badge = f" — <i>🗞️ {html.escape(source_name)}</i>" if source_name else ""
        lines.append(
            f"<blockquote><b>{en_to_bn_digits(str(idx))}.</b> "
            f"<a href=\"{html.escape(link)}\">{html.escape(raw_title)}</a>{src_badge}</blockquote>"
        )
    return "\n".join(lines)


def fetch_song_lyrics_and_info(query_song: str) -> str:
    """
    Searches LRCLIB free lyrics database first for real full lyrics, and combines with
    Groq AI musical insights/Bangla lyrics so users always get a complete, satisfying result.
    """
    clean_q = query_song.strip()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BigBot/2.0)"}
    found_lyrics = ""
    track_header = ""

    # 1. Try LRCLIB API (Free, no key, huge database of Bangla, Hindi & English songs)
    try:
        lrc_url = f"https://lrclib.net/api/search?q={urllib.parse.quote(clean_q)}"
        r = requests.get(lrc_url, headers=headers, timeout=10)
        if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0:
            best = r.json()[0]
            plain = (best.get("plainLyrics") or "").strip()
            t_name = best.get("trackName") or clean_q
            a_name = best.get("artistName") or "Unknown Artist"
            alb_name = best.get("albumName") or ""
            if plain and len(plain) > 40:
                found_lyrics = plain[:2200]
                track_header = f"🎶 <b>গান:</b> {html.escape(t_name)}\n🎤 <b>শিল্পী:</b> {html.escape(a_name)}"
                if alb_name:
                    track_header += f"\n💿 <b>অ্যালবাম:</b> {html.escape(alb_name)}"
    except Exception as e:
        logger.warning(f"LRCLIB search fallback: {e}")

    if found_lyrics:
        return (
            f"🎵 <b>গানের সম্পূর্ণ লিরিক্স ও তথ্য</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{track_header}</blockquote>\n\n"
            f"🎼 <b>লিরিক্স (Lyrics):</b>\n"
            f"<blockquote>{html.escape(found_lyrics)}</blockquote>"
        )

    # 2. Fallback to Groq AI comprehensive song & chorus/lyrics presenter
    ai_out = call_groq_chat(
        [
            {
                "role": "system",
                "content": (
                    "You are an expert Bangla, Hindi, and English music encyclopedia. "
                    "When the user asks for a song, provide clearly in Bangla without raw asterisks (**):\n"
                    "🎶 গানের নাম:\n"
                    "🎤 শিল্পী ও অ্যালবাম/সিনেমা:\n"
                    "🎼 গানের বিখ্যাত লাইন / লিরিক্স:\n"
                    "💡 গানের মূল ভাবার্থ ও আকর্ষণীয় তথ্য:"
                ),
            },
            {"role": "user", "content": f"গান: {clean_q}"},
        ],
        temperature=0.5,
        max_tokens=1200,
    )
    return (
        f"🎵 <b>গানের লিরিক্স ও বিস্তারিত তথ্য</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>{html.escape(clean_ai_text(ai_out))}</blockquote>"
    )


VOICE_CHARACTER_LABELS: Dict[str, str] = {
    "bn-BD-NabanitaNeural": "🇧🇩 বাংলা নারী — নবনীতা (মিষ্টি কণ্ঠ)",
    "bn-BD-PradeepNeural": "🇧🇩 বাংলা পুরুষ — প্রদীপ (ভরাট কণ্ঠ)",
    "bn-IN-TanishaaNeural": "🇮🇳 বাংলা নারী — তানিশা (স্টুডিও কণ্ঠ)",
    "bn-IN-BashkarNeural": "🇮🇳 বাংলা পুরুষ — ভাস্কর (আবৃত্তি কণ্ঠ)",
    "en-US-AriaNeural": "🇺🇸 English Female — Aria (Natural)",
    "en-US-ChristopherNeural": "🇺🇸 English Male — Christopher (Cinema)",
    "en-GB-SoniaNeural": "🇬🇧 British Female — Sonia (Royal)",
    "hi-IN-SwaraNeural": "🇮🇳 Hindi/Urdu — Swara (Melodic)",
}


async def generate_tts_voice(text: str, voice: str) -> str:
    """
    Generates studio-quality voice up to 2,500+ characters (2K+ lines) using edge-tts
    with automatic fallback to gTTS and Opus voice conversion via imageio-ffmpeg.
    """
    tmp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    edge_ok = False

    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice)
            await communicate.save(tmp_mp3)
            if os.path.exists(tmp_mp3) and os.path.getsize(tmp_mp3) > 100:
                edge_ok = True
                break
        except Exception as e:
            logger.warning(f"edge-tts attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(1)

    if not edge_ok:
        lang = "bn" if voice.startswith("bn") else ("hi" if voice.startswith("hi") else "en")
        tts = gTTS(text=text, lang=lang)
        tts.save(tmp_mp3)

    tmp_ogg = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg").name
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", tmp_mp3, "-c:a", "libopus", "-b:a", "48k", tmp_ogg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=True,
        )
        if os.path.exists(tmp_ogg) and os.path.getsize(tmp_ogg) > 100:
            os.remove(tmp_mp3)
            return tmp_ogg
    except Exception as e:
        logger.warning(f"ffmpeg opus conversion fallback to mp3: {e}")
        if os.path.exists(tmp_ogg):
            try:
                os.remove(tmp_ogg)
            except OSError:
                pass

    return tmp_mp3


# ---------------------------------------------------------------------------
# MULTI-ENGINE VIDEO DOWNLOADER (TIKTOK + YOUTUBE + FACEBOOK + INSTAGRAM)
# ---------------------------------------------------------------------------
def _stream_download_file(stream_url: str, out_path: str) -> bool:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
    }
    with requests.get(stream_url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        total_bytes = 0
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    total_bytes += len(chunk)
                    if total_bytes > 50 * 1024 * 1024:
                        raise ValueError("FILE_TOO_LARGE")
                    f.write(chunk)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


def _extract_video_url_from_json(obj: Any) -> Optional[str]:
    """
    Recursively finds the best direct mp4/video download URL inside API JSON responses.
    """
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("http") and any(k in s.lower() for k in (".mp4", "video", "fbcdn", "cdninstagram", "googlevideo", "tikwm", "download", "media")):
            if not s.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".mp3", ".m4a")):
                return s
        return None
    if isinstance(obj, dict):
        # Prioritize HD / high quality keys first
        for k in ("hd", "hdplay", "url", "download_url", "video_url", "sd", "play", "link", "data", "result", "downloads", "medias", "formats"):
            if k in obj:
                found = _extract_video_url_from_json(obj[k])
                if found:
                    return found
        for v in obj.values():
            found = _extract_video_url_from_json(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _extract_video_url_from_json(item)
            if found:
                return found
    return None


def download_video_from_url(url: str) -> Tuple[str, str]:
    """
    6-Stage Universal Video Downloader for Render Cloud IPs:
    Supports TikTok, YouTube (Videos & Shorts), Facebook (Reels, Watch, share/r, share/v), Instagram (Reels/Posts), X/Twitter:
    Stage 1: Resolve short/share redirects (fb.watch, facebook.com/share/r/..., youtu.be, vm.tiktok.com)
    Stage 2: TikTok -> tikwm API
    Stage 3: Dedicated External Social Downloader APIs (Ryzendesu, Siputzx, Vkrdownloader) for FB, IG, YT
    Stage 4: Updated Cobalt Community APIs
    Stage 5: yt-dlp with android_vr / tv_embedded / ios / mweb client bypass & bundled ffmpeg
    """
    tmp_dir = tempfile.mkdtemp(prefix="vid_")
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

    # Stage 1: Resolve Facebook / TikTok / YouTube short redirects properly
    resolved_url = url.strip()
    try:
        # Use GET with stream=True so Facebook share/r/ and share/v/ redirects resolve to canonical /reel/ or /watch/ URLs
        with requests.get(
            resolved_url,
            allow_redirects=True,
            stream=True,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"},
        ) as r_redir:
            if r_redir.url and r_redir.url.startswith("http") and "login" not in r_redir.url.lower():
                resolved_url = r_redir.url
    except Exception:
        pass

    lower_u = (resolved_url + " " + url).lower()
    enc_orig = urllib.parse.quote(url)
    enc_res = urllib.parse.quote(resolved_url)

    # Stage 2: TikTok via tikwm API
    if "tiktok.com" in lower_u:
        try:
            api_url = f"https://www.tikwm.com/api/?url={enc_orig}&hd=1"
            resp = requests.get(api_url, headers={"User-Agent": ua}, timeout=20)
            if resp.status_code == 200:
                data = (resp.json() or {}).get("data") or {}
                play_url = data.get("hdplay") or data.get("play")
                title = data.get("title") or "TikTok Video"
                if play_url:
                    if play_url.startswith("/"):
                        play_url = "https://www.tikwm.com" + play_url
                    out_path = os.path.join(tmp_dir, "tiktok.mp4")
                    if _stream_download_file(play_url, out_path):
                        return out_path, title
        except ValueError as ve:
            if str(ve) == "FILE_TOO_LARGE":
                raise
        except Exception as e:
            logger.warning(f"tikwm API failed: {e}")

    # Stage 2B: Direct Facebook Raw HTML Video Extractor (extracts browser_native_hd_url / playable_url / og:video directly!)
    if any(k in lower_u for k in ("facebook.com", "fb.watch", "fb.com")):
        for fb_target in (resolved_url, url, resolved_url.replace("www.facebook.com", "m.facebook.com")):
            try:
                fb_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Sec-Fetch-Mode": "navigate",
                }
                fb_r = requests.get(fb_target, headers=fb_headers, timeout=15)
                if fb_r.status_code == 200 and fb_r.text:
                    html_txt = fb_r.text
                    for pat in (
                        r'"browser_native_hd_url":"([^"]+)"',
                        r'"playable_url_quality_hd":"([^"]+)"',
                        r'"hd_src_no_ratelimit":"([^"]+)"',
                        r'"hd_src":"([^"]+)"',
                        r'"browser_native_sd_url":"([^"]+)"',
                        r'"playable_url":"([^"]+)"',
                        r'"sd_src_no_ratelimit":"([^"]+)"',
                        r'"sd_src":"([^"]+)"',
                        r'<meta\s+property="og:video"\s+content="([^"]+)"',
                        r'<meta\s+property="og:video:secure_url"\s+content="([^"]+)"',
                    ):
                        m_fb = re.search(pat, html_txt)
                        if m_fb:
                            raw_v_url = m_fb.group(1).encode("utf-8").decode("unicode_escape").replace("\\/", "/")
                            raw_v_url = html.unescape(raw_v_url)
                            if raw_v_url.startswith("http"):
                                out_path = os.path.join(tmp_dir, "fb_direct.mp4")
                                if _stream_download_file(raw_v_url, out_path):
                                    return out_path, "Facebook Video"
            except ValueError as ve:
                if str(ve) == "FILE_TOO_LARGE":
                    raise
            except Exception as e:
                logger.debug(f"Direct FB HTML extractor skipped: {e}")

    # Stage 2C: Direct YouTube Piped / Invidious Stream Extractor (bypasses Render IP block on YouTube!)
    if any(k in lower_u for k in ("youtube.com", "youtu.be")):
        yt_id_match = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", resolved_url + " " + url)
        if yt_id_match:
            vid_id = yt_id_match.group(1)
            piped_apis = [
                f"https://pipedapi.kavin.rocks/streams/{vid_id}",
                f"https://pipedapi.tokhmi.xyz/streams/{vid_id}",
                f"https://pipedapi.moomoo.me/streams/{vid_id}",
            ]
            for p_api in piped_apis:
                try:
                    pr = requests.get(p_api, headers={"User-Agent": ua}, timeout=12)
                    if pr.status_code == 200:
                        pdata = pr.json()
                        v_streams = pdata.get("videoStreams") or []
                        for vs in v_streams:
                            if not vs.get("videoOnly", True) and vs.get("url"):
                                out_path = os.path.join(tmp_dir, "yt_piped.mp4")
                                if _stream_download_file(vs["url"], out_path):
                                    return out_path, pdata.get("title") or "YouTube Video"
                except ValueError as ve:
                    if str(ve) == "FILE_TOO_LARGE":
                        raise
                except Exception:
                    pass

            invidious_apis = [
                f"https://inv.tux.pizza/api/v1/videos/{vid_id}",
                f"https://invidious.nerdvpn.de/api/v1/videos/{vid_id}",
                f"https://invidious.jing.rocks/api/v1/videos/{vid_id}",
            ]
            for inv_api in invidious_apis:
                try:
                    ir = requests.get(inv_api, headers={"User-Agent": ua}, timeout=12)
                    if ir.status_code == 200:
                        idata = ir.json()
                        f_streams = idata.get("formatStreams") or []
                        for fs in f_streams:
                            if fs.get("url"):
                                out_path = os.path.join(tmp_dir, "yt_inv.mp4")
                                if _stream_download_file(fs["url"], out_path):
                                    return out_path, idata.get("title") or "YouTube Video"
                except ValueError as ve:
                    if str(ve) == "FILE_TOO_LARGE":
                        raise
                except Exception:
                    pass

    # Stage 3: Dedicated External Downloader APIs for Facebook, Instagram & YouTube
    external_apis: List[str] = []
    if any(k in lower_u for k in ("facebook.com", "fb.watch", "fb.com")):
        external_apis.extend([
            f"https://api.ryzendesu.vip/api/downloader/fbdl?url={enc_res}",
            f"https://api.ryzendesu.vip/api/downloader/fbdl?url={enc_orig}",
            f"https://api.siputzx.my.id/api/d/facebook?url={enc_res}",
            f"https://vkrdownloader.vercel.app/server?vkr={enc_res}",
        ])
    elif "instagram.com" in lower_u:
        external_apis.extend([
            f"https://api.ryzendesu.vip/api/downloader/igdl?url={enc_res}",
            f"https://api.siputzx.my.id/api/d/igdl?url={enc_res}",
            f"https://vkrdownloader.vercel.app/server?vkr={enc_res}",
        ])
    elif any(k in lower_u for k in ("youtube.com", "youtu.be")):
        external_apis.extend([
            f"https://api.ryzendesu.vip/api/downloader/ytmp4?url={enc_res}",
            f"https://api.siputzx.my.id/api/d/ytmp4?url={enc_res}",
            f"https://vkrdownloader.vercel.app/server?vkr={enc_res}",
        ])
    else:
        external_apis.append(f"https://vkrdownloader.vercel.app/server?vkr={enc_res}")

    for ext_api in external_apis:
        try:
            r_ext = requests.get(ext_api, headers={"User-Agent": ua}, timeout=20)
            if r_ext.status_code == 200:
                j_ext = r_ext.json()
                dl_link = _extract_video_url_from_json(j_ext)
                if dl_link:
                    out_path = os.path.join(tmp_dir, "ext_video.mp4")
                    if _stream_download_file(dl_link, out_path):
                        return out_path, "Downloaded Social Video"
        except ValueError as ve:
            if str(ve) == "FILE_TOO_LARGE":
                raise
        except Exception as e:
            logger.debug(f"External API {ext_api[:50]} skipped: {e}")

    # Stage 4: Cobalt API instances (both v7 and v10 payloads)
    cobalt_endpoints = [
        "https://co.eepy.today/",
        "https://cobalt.api.timelessnesses.me/",
        "https://api.cobalt.tools/api/json",
        "https://api.cobalt.tools/",
    ]
    for cob_url in cobalt_endpoints:
        for t_url in (resolved_url, url):
            try:
                c_resp = requests.post(
                    cob_url,
                    json={"url": t_url, "videoQuality": "720", "vQuality": "720"},
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": ua,
                    },
                    timeout=15,
                )
                if c_resp.status_code == 200:
                    c_data = c_resp.json()
                    dl_link = c_data.get("url")
                    if dl_link:
                        out_path = os.path.join(tmp_dir, "cobalt_video.mp4")
                        if _stream_download_file(dl_link, out_path):
                            return out_path, c_data.get("filename") or "Downloaded Video"
            except ValueError as ve:
                if str(ve) == "FILE_TOO_LARGE":
                    raise
            except Exception:
                pass

    # Stage 5: yt-dlp with android_vr / tv_embedded / ios / mweb clients & bundled imageio-ffmpeg
    out_tmpl = os.path.join(tmp_dir, "video.%(ext)s")
    client_profiles = [
        # Profile 1: YouTube android_vr & tv_embedded (bypasses YouTube datacenter bot check without cookies!)
        {
            "format": (
                "best[filesize<46M][ext=mp4]/"
                "best[filesize_approx<46M][ext=mp4]/"
                "bestvideo[filesize<35M][ext=mp4]+bestaudio[filesize<10M][ext=m4a]/"
                "best[height<=720][ext=mp4]/best[ext=mp4]/best"
            ),
            "extractor_args": {
                "youtube": {
                    "player_client": ["android_vr", "tv_embedded", "ios", "mweb", "android"],
                }
            },
            "http_headers": {"User-Agent": ua},
        },
        # Profile 2: Mobile Safari headers (ideal for Facebook Reels/Watch & Instagram Reels)
        {
            "format": "best[height<=720][ext=mp4]/best[ext=mp4]/best",
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        },
    ]

    # Also build mbasic/mobile FB fallback URL if it's a Facebook link
    candidate_targets = [resolved_url]
    if url != resolved_url:
        candidate_targets.append(url)
    if "facebook.com" in resolved_url:
        candidate_targets.append(resolved_url.replace("www.facebook.com", "m.facebook.com"))

    last_err: Optional[Exception] = None
    for profile in client_profiles:
        for target in candidate_targets:
            try:
                ydl_opts: Dict[str, Any] = {
                    "outtmpl": out_tmpl,
                    "noplaylist": True,
                    "quiet": True,
                    "no_warnings": True,
                    "nocheckcertificate": True,
                    "geo_bypass": True,
                    "ffmpeg_location": ffmpeg_exe,
                    "merge_output_format": "mp4",
                    "max_filesize": 50 * 1024 * 1024,
                    "socket_timeout": 25,
                    "retries": 3,
                }
                ydl_opts.update(profile)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(target, download=True)
                    title = info.get("title", "Downloaded Video") if info else "Downloaded Video"
                    downloaded_path = ydl.prepare_filename(info)

                if not os.path.exists(downloaded_path):
                    files = [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)]
                    if files:
                        downloaded_path = files[0]

                if os.path.exists(downloaded_path) and os.path.getsize(downloaded_path) > 1000:
                    if os.path.getsize(downloaded_path) > 50 * 1024 * 1024:
                        raise ValueError("FILE_TOO_LARGE")
                    return downloaded_path, title
            except ValueError as ve:
                if str(ve) == "FILE_TOO_LARGE":
                    raise
                last_err = ve
            except Exception as e:
                last_err = e
                logger.warning(f"yt-dlp attempt failed for {target}: {e}")

    if last_err:
        raise last_err
    raise RuntimeError("Video download failed across all engines.")


# ---------------------------------------------------------------------------
# QUIZ HELPER FUNCTIONS
# ---------------------------------------------------------------------------
def generate_quiz_questions() -> List[Dict[str, Any]]:
    prompt = (
        "Generate 5 multiple-choice general knowledge (GK) questions in Bangla. "
        "Return STRICT JSON ONLY with this structure:\n"
        '{"questions": [{"question": "...", "options": ["...", "...", "...", "..."], "correct": 0}]}\n'
        "Rules: 'correct' must be an integer 0, 1, 2, or 3 indicating the index of the right option."
    )
    raw = call_groq_chat(
        messages=[
            {"role": "system", "content": "You output valid JSON only without markdown fences."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.6,
        max_tokens=1200,
        json_mode=True,
    )
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    json_str = m.group(0) if m else raw
    parsed = json.loads(json_str)
    q_list = parsed.get("questions", [])
    valid_questions: List[Dict[str, Any]] = []
    for q in q_list:
        if (
            isinstance(q, dict)
            and "question" in q
            and isinstance(q.get("options"), list)
            and len(q["options"]) == 4
            and isinstance(q.get("correct"), int)
            and 0 <= q["correct"] <= 3
        ):
            valid_questions.append(q)
    if not valid_questions:
        raise ValueError("Failed to generate valid quiz JSON.")
    return valid_questions[:5]


async def send_quiz_question(message, context: ContextTypes.DEFAULT_TYPE, user_id: Optional[int] = None) -> None:
    quiz_state = context.user_data.get("quiz")
    if not quiz_state:
        return
    idx = quiz_state["index"]
    questions = quiz_state["questions"]
    if idx >= len(questions):
        score = quiz_state["score"]
        total = len(questions)
        earned = quiz_state["earned_points"]
        context.user_data.pop("quiz", None)
        context.user_data["state"] = None
        await message.reply_text(
            f"🏁 <b>কুইজ প্রতিযোগিতা সম্পন্ন!</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>"
            f"✅ <b>সঠিক উত্তর:</b> {score}/{total}\n"
            f"🏆 <b>অর্জিত মোট পয়েন্ট:</b> +{earned} পয়েন্ট"
            f"</blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_markup(user_id),
        )
        return

    q = questions[idx]
    buttons = []
    for opt_i, opt_text in enumerate(q["options"]):
        buttons.append([InlineKeyboardButton(f"{opt_i + 1}. {opt_text}", callback_data=f"quiz_ans:{idx}:{opt_i}")])

    await message.reply_text(
        f"🧠 <b>কুইজ প্রশ্ন ({idx + 1}/{len(questions)})</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>❓ <b>{html.escape(q['question'])}</b></blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ---------------------------------------------------------------------------
# REMINDER JOB CALLBACK
# ---------------------------------------------------------------------------
async def reminder_job_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if not job or not job.data:
        return
    chat_id = job.data.get("chat_id")
    text = job.data.get("text", "")
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ রিমাইন্ডার: {text}",
        )
    except Exception as e:
        logger.error(f"Failed to send reminder to {chat_id}: {e}")


# ---------------------------------------------------------------------------
# COMMAND HANDLERS (/start, /help, /myid, ADMIN COMMANDS)
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message:
        return
    if is_user_banned(user.id):
        return

    ref_id: Optional[int] = None
    if context.args and len(context.args) > 0:
        arg = context.args[0].strip()
        if arg.startswith("ref_"):
            ref_str = arg.replace("ref_", "").strip()
            if ref_str.isdigit():
                ref_id = int(ref_str)

    full_name = user.full_name or user.first_name or "বন্ধু"
    is_new, valid_ref = ensure_user(user.id, full_name, referred_by=ref_id)

    if is_new and valid_ref:
        try:
            await context.bot.send_message(
                chat_id=valid_ref,
                text=(
                    f"🎉 <b>নতুন রেফারেল বোনাস!</b>\n"
                    f"{DIVIDER}\n"
                    f"<blockquote><b>{html.escape(full_name)}</b> আপনার রেফারেল লিংকে জয়েন করেছেন।\n"
                    f"🎁 আপনি পেয়েছেন <b>+১০ পয়েন্ট!</b></blockquote>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    if is_maintenance_on() and not is_admin(user.id):
        await update.effective_message.reply_text(
            "🔧 বট বর্তমানে রক্ষণাবেক্ষণ (Maintenance) কাজের জন্য সাময়িকভাবে বন্ধ আছে। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন 🙏"
        )
        return

    context.user_data["state"] = None
    total_users = get_total_users()
    u_row = get_user(user.id)
    pts = int(u_row["points"]) if u_row else 0
    lvl = get_level_name(pts)

    welcome_msg = (
        f"✨ <b>আসসালামু আলাইকুম, {html.escape(full_name)}!</b>\n"
        f"{DIVIDER}\n"
        f"🚀 <b>অল-ইন-ওয়ান স্মার্ট বাংলা AI বটে স্বাগতম!</b>\n\n"
        f"<blockquote>"
        f"👤 <b>আপনার লেভেল:</b> {lvl} ({en_to_bn_digits(str(pts))} পয়েন্ট)\n"
        f"👥 <b>মোট ব্যবহারকারী:</b> {en_to_bn_digits(str(total_users))} জন\n"
        f"🛠️ <b>মোট সার্ভিস:</b> ৩৬+ প্রিমিয়াম টুলস (সম্পূর্ণ ফ্রি)"
        f"</blockquote>\n\n"
        f"👇 <b>নিচের মেনু থেকে আপনার পছন্দের সেবাটি বেছে নিন:</b>"
    )
    await update.effective_message.reply_text(
        welcome_msg,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_markup(user.id),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message or is_user_banned(user.id):
        return
    await update.effective_message.reply_text(
        HELP_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_markup(user.id),
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message or is_user_banned(user.id):
        return
    await update.effective_message.reply_text(
        f"🆔 <b>আপনার টেলিগ্রাম ইউজার আইডি:</b>\n<blockquote><code>{user.id}</code></blockquote>",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# ADMIN PANEL & ADMIN TEXT COMMANDS (FULL INTERACTIVE BUTTONS)
# ---------------------------------------------------------------------------
def build_admin_panel_markup() -> InlineKeyboardMarkup:
    maint_status = "ON 🟢" if is_maintenance_on() else "OFF 🔴"
    prem_status = "ON 💎" if is_premium_mode_on() else "OFF 🆓"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Live Stats", callback_data="admin:stats"),
                InlineKeyboardButton("📢 Broadcast All", callback_data="admin:broadcast"),
            ],
            [
                InlineKeyboardButton("📢 চ্যানেল (Force Join)", callback_data="admin:channel"),
                InlineKeyboardButton(f"🔧 Maintenance: {maint_status}", callback_data="admin:maint_toggle"),
            ],
            [
                InlineKeyboardButton("👑 VIP প্রিমিয়াম দিন/নিন", callback_data="admin:vip_user"),
                InlineKeyboardButton(f"💎 Premium Mode: {prem_status}", callback_data="admin:prem_toggle"),
            ],
            [
                InlineKeyboardButton("➕ পণ্য যোগ (Add Product)", callback_data="admin:add_prod"),
                InlineKeyboardButton("🗑️ পণ্য ডিলিট (Del Product)", callback_data="admin:del_prod"),
            ],
            [
                InlineKeyboardButton("🚫 Ban / Unban ইউজার", callback_data="admin:ban_user"),
                InlineKeyboardButton("🎁 পয়েন্ট গিফট", callback_data="admin:add_pts"),
            ],
            [
                InlineKeyboardButton("📦 অর্ডার লিস্ট (Orders)", callback_data="admin:orders"),
                InlineKeyboardButton("👑 VIP ইউজার লিস্ট", callback_data="admin:vip_list"),
            ],
        ]
    )


async def send_admin_panel(message, user_id: int) -> None:
    if not is_admin(user_id):
        return
    u_cnt = get_total_users()
    o_cnt = get_total_orders()
    ch = get_force_join_channel() or "OFF"
    await message.reply_text(
        f"🛠️ <b>অ্যাডমিন কন্ট্রোল প্যানেল (Admin Dashboard)</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>"
        f"👥 <b>মোট ইউজার:</b> {u_cnt} জন  |  🛍️ <b>অর্ডার:</b> {o_cnt} টি\n"
        f"📢 <b>Force Join:</b> {html.escape(ch)}\n"
        f"🔧 <b>Maintenance:</b> {'ON 🟢' if is_maintenance_on() else 'OFF 🔴'}"
        f"</blockquote>\n\n"
        "👇 <b>নিচের বাটনগুলোতে ক্লিক করে সরাসরি সব কিছু নিয়ন্ত্রণ করুন:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=build_admin_panel_markup(),
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message:
        return
    if not is_admin(user.id):
        return
    await send_admin_panel(update.effective_message, user.id)


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.effective_message:
        return
    if not context.args:
        await update.effective_message.reply_text("ব্যবহার: /ban <user_id>")
        return
    target = bn_to_en_digits(context.args[0].strip())
    if not target.isdigit():
        await update.effective_message.reply_text("⚠️ সঠিক ইউজার আইডি দিন।")
        return
    uid = int(target)
    ensure_user(uid, "User")
    with get_db() as conn:
        conn.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (uid,))
        conn.commit()
    await update.effective_message.reply_text(f"🚫 ইউজার <code>{uid}</code>-কে ব্যান করা হয়েছে।", parse_mode=ParseMode.HTML)


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.effective_message:
        return
    if not context.args:
        await update.effective_message.reply_text("ব্যবহার: /unban <user_id>")
        return
    target = bn_to_en_digits(context.args[0].strip())
    if not target.isdigit():
        await update.effective_message.reply_text("⚠️ সঠিক ইউজার আইডি দিন।")
        return
    uid = int(target)
    with get_db() as conn:
        conn.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (uid,))
        conn.commit()
    await update.effective_message.reply_text(f"✅ ইউজার <code>{uid}</code>-এর ব্যান তুলে নেওয়া হয়েছে।", parse_mode=ParseMode.HTML)


async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.effective_message:
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.effective_message.reply_text("ব্যবহার: /maintenance on অথবা /maintenance off")
        return
    val = context.args[0].lower()
    set_setting("maintenance", val)
    await update.effective_message.reply_text(f"🔧 Maintenance মোড এখন: <b>{val.upper()}</b>", parse_mode=ParseMode.HTML)


async def cmd_setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.effective_message:
        return
    if not context.args:
        await update.effective_message.reply_text("ব্যবহার: /setchannel @ChannelName অথবা /setchannel off")
        return
    arg = context.args[0].strip()
    if arg.lower() == "off":
        set_setting("force_join", "off")
        await update.effective_message.reply_text("✅ Force Join চ্যানেল বন্ধ (OFF) করা হয়েছে।")
    else:
        if not arg.startswith("@") and not arg.startswith("-100"):
            arg = f"@{arg}"
        set_setting("force_join", arg)
        await update.effective_message.reply_text(f"✅ Force Join চ্যানেল সেট করা হয়েছে: <b>{html.escape(arg)}</b>", parse_mode=ParseMode.HTML)


async def cmd_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.effective_message:
        return
    ch = get_force_join_channel()
    if ch:
        await update.effective_message.reply_text(f"📢 বর্তমান Force Join চ্যানেল: <b>{html.escape(ch)}</b>", parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text("📢 বর্তমানে কোনো Force Join চ্যানেল সেট করা নেই (OFF)।")


async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.effective_message:
        return
    if len(context.args) < 2 or context.args[1].lower() not in ("on", "off"):
        await update.effective_message.reply_text("ব্যবহার: /premium <user_id> on|off")
        return
    target = bn_to_en_digits(context.args[0].strip())
    if not target.isdigit():
        await update.effective_message.reply_text("⚠️ সঠিক ইউজার আইডি দিন।")
        return
    uid = int(target)
    flag = 1 if context.args[1].lower() == "on" else 0
    ensure_user(uid, "User")
    with get_db() as conn:
        conn.execute("UPDATE users SET premium = ? WHERE user_id = ?", (flag, uid))
        conn.commit()
    status_str = "চালু (ON)" if flag else "বন্ধ (OFF)"
    await update.effective_message.reply_text(f"💎 ইউজার <code>{uid}</code>-এর প্রিমিয়াম স্ট্যাটাস: <b>{status_str}</b>", parse_mode=ParseMode.HTML)


async def cmd_addproduct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.effective_message:
        return
    raw_text = update.effective_message.text or ""
    payload = raw_text.partition(" ")[2].strip()
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) < 3 or not all(parts[:3]):
        await update.effective_message.reply_text("ব্যবহার: <code>/addproduct নাম|দাম|বিবরণ</code>", parse_mode=ParseMode.HTML)
        return
    name, price, desc = parts[0], parts[1], parts[2]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO products (name, price, description) VALUES (?, ?, ?)", (name, price, desc))
        pid = cur.lastrowid
        conn.commit()
    await update.effective_message.reply_text(
        f"✅ <b>নতুন পণ্য যোগ করা হয়েছে!</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>🆔 ID: <b>{pid}</b>\n📦 নাম: {html.escape(name)}\n💰 দাম: {html.escape(price)}</blockquote>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_delproduct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.effective_message:
        return
    if not context.args:
        await update.effective_message.reply_text("ব্যবহার: /delproduct <id>")
        return
    pid_str = bn_to_en_digits(context.args[0].strip())
    if not pid_str.isdigit():
        await update.effective_message.reply_text("⚠️ সঠিক প্রোডাক্ট আইডি দিন।")
        return
    pid = int(pid_str)
    with get_db() as conn:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
        deleted = cur.rowcount
    if deleted:
        await update.effective_message.reply_text(f"🗑️ প্রোডাক্ট ID {pid} ডিলিট করা হয়েছে।")
    else:
        await update.effective_message.reply_text(f"⚠️ প্রোডাক্ট ID {pid} খুঁজে পাওয়া যায়নি।")


# ---------------------------------------------------------------------------
# CALLBACK QUERY HANDLER (INLINE BUTTONS)
# ---------------------------------------------------------------------------
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    if is_user_banned(user.id):
        return

    data = query.data or ""

    try:
        # 1. Force Join Recheck
        if data == "recheck_join":
            channel = get_force_join_channel()
            if not channel:
                await query.answer("✅ ধন্যবাদ! এখন আপনি বট ব্যবহার করতে পারেন।", show_alert=True)
                await query.message.reply_text("✅ মূল মেনু থেকে আপনার পছন্দের টুল বেছে নিন:", reply_markup=get_main_menu_markup(user.id))
                return

            joined = await check_force_join(update, context)
            if joined:
                await query.answer("✅ জয়েন নিশ্চিত হয়েছে! ধন্যবাদ।", show_alert=True)
                await query.message.reply_text("✅ অভিনন্দন! এখন আপনি বটের সকল টুল ব্যবহার করতে পারবেন।", reply_markup=get_main_menu_markup(user.id))
            else:
                await query.answer("❌ আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)
            return

        # 2. Admin Panel Callbacks
        if data.startswith("admin:"):
            if not is_admin(user.id):
                await query.answer()
                return
            action = data.split(":", 1)[1]
            if action == "stats":
                u_cnt = get_total_users()
                o_cnt = get_total_orders()
                b_cnt = get_total_banned()
                p_cnt = get_total_premium()
                ch = get_force_join_channel() or "OFF"
                maint = "ON 🟢" if is_maintenance_on() else "OFF 🔴"
                prem_m = "ON 💎" if is_premium_mode_on() else "OFF 🆓"
                await query.answer()
                await query.message.reply_text(
                    f"📊 <b>বট বিস্তারিত পরিসংখ্যান (Live Stats)</b>\n"
                    f"{DIVIDER}\n"
                    f"<blockquote>"
                    f"👥 <b>মোট ইউজার:</b> {u_cnt} জন\n"
                    f"💎 <b>প্রিমিয়াম ইউজার:</b> {p_cnt} জন\n"
                    f"🚫 <b>ব্যানড ইউজার:</b> {b_cnt} জন\n"
                    f"🛍️ <b>মোট অর্ডার:</b> {o_cnt} টি\n"
                    f"📢 <b>Force Join:</b> {html.escape(ch)}\n"
                    f"🔧 <b>Maintenance:</b> {maint}\n"
                    f"👑 <b>Premium Mode:</b> {prem_m}"
                    f"</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "broadcast":
                context.user_data["state"] = "ADMIN_BROADCAST"
                await query.answer()
                await query.message.reply_text(
                    f"📢 <b>ব্রডকাস্ট মোড চালু হয়েছে</b>\n"
                    f"{DIVIDER}\n"
                    "<blockquote>এখন যে মেসেজ, ছবি বা ভিডিও পাঠাবেন সেটি সকল ব্যবহারকারীর কাছে চলে যাবে (বাতিল করতে 🏠 মেনু চাপুন):</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "channel":
                ch = get_force_join_channel()
                status_txt = f"বর্তমান চ্যানেল: <b>{html.escape(ch)}</b>" if ch else "বর্তমানে কোনো চ্যানেল সেট করা নেই (OFF)।"
                context.user_data["state"] = "ADMIN_SET_CHANNEL"
                await query.answer()
                await query.message.reply_text(
                    f"📢 <b>চ্যানেল (Force Join) সেটিংস</b>\n"
                    f"{DIVIDER}\n"
                    f"<blockquote>{status_txt}\n\n"
                    f"✍️ এখন সরাসরি আপনার চ্যানেলের ইউজারনেম (যেমন <code>@MyChannel</code>) লিখে পাঠান, অথবা বন্ধ করতে <code>off</code> লিখে পাঠান:</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "maint_toggle":
                new_val = "off" if is_maintenance_on() else "on"
                set_setting("maintenance", new_val)
                await query.answer(f"Maintenance এখন {new_val.upper()}")
                await query.edit_message_reply_markup(reply_markup=build_admin_panel_markup())
            elif action == "prem_toggle":
                new_val = "off" if is_premium_mode_on() else "on"
                set_setting("premium_mode", new_val)
                await query.answer(f"Premium Mode এখন {new_val.upper()}")
                await query.edit_message_reply_markup(reply_markup=build_admin_panel_markup())
            elif action == "add_prod":
                context.user_data["state"] = "ADMIN_ADD_PRODUCT"
                await query.answer()
                await query.message.reply_text(
                    f"➕ <b>নতুন পণ্য যোগ করুন</b>\n"
                    f"{DIVIDER}\n"
                    "<blockquote>নিচের ফরম্যাটে মেসেজ পাঠান:\n"
                    "<code>পণ্য নাম | দাম | বিবরণ</code>\n\n"
                    "💡 উদাহরণ:\n<code>Canva Pro | ৯৯ টাকা | ১ বছরের গ্যারান্টিসহ প্রিমিয়াম সাবস্ক্রিপশন</code></blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "del_prod":
                with get_db() as conn:
                    prods = conn.execute("SELECT * FROM products ORDER BY id ASC").fetchall()
                await query.answer()
                if not prods:
                    await query.message.reply_text("⚠️ শপে বর্তমানে কোনো পণ্য নেই।")
                    return
                btns = []
                for p in prods:
                    btns.append([InlineKeyboardButton(f"🗑️ #{p['id']} {p['name']} ({p['price']})", callback_data=f"admin_delp:{p['id']}")])
                await query.message.reply_text(
                    f"🗑️ <b>পণ্য ডিলিট করতে নিচের তালিকা থেকে সিলেক্ট করুন:</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(btns),
                )
            elif action == "ban_user":
                context.user_data["state"] = "ADMIN_BAN_UNBAN"
                await query.answer()
                await query.message.reply_text(
                    f"🚫 <b>ইউজার Ban / Unban করুন</b>\n"
                    f"{DIVIDER}\n"
                    "<blockquote>যেকোনো ইউজারকে ব্যান বা আনব্যান করতে তার <b>Telegram User ID</b> লিখে পাঠান (ব্যান থাকলে আনব্যান হবে, আর আনব্যান থাকলে ব্যান হবে):</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "add_pts":
                context.user_data["state"] = "ADMIN_GIFT_POINTS"
                await query.answer()
                await query.message.reply_text(
                    f"🎁 <b>ইউজারকে পয়েন্ট গিফট করুন</b>\n"
                    f"{DIVIDER}\n"
                    "<blockquote>নিচের ফরম্যাটে ইউজার আইডি ও পয়েন্ট লিখে পাঠান:\n"
                    "<code>User_ID Points</code>\n\n"
                    "💡 উদাহরণ: <code>123456789 100</code></blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "vip_user":
                context.user_data["state"] = "ADMIN_VIP_TOGGLE"
                await query.answer()
                await query.message.reply_text(
                    f"👑 <b>VIP প্রিমিয়াম মেম্বারশিপ কন্ট্রোল</b>\n"
                    f"{DIVIDER}\n"
                    "<blockquote>যেকোনো ইউজারকে <b>VIP প্রিমিয়াম</b> দিতে বা বাতিল করতে তার <b>Telegram User ID</b> লিখে পাঠান (ফ্রি থাকলে VIP হবে, আর VIP থাকলে ফ্রি হবে):</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "vip_list":
                with get_db() as conn:
                    vips = conn.execute("SELECT user_id, name, points FROM users WHERE premium = 1 ORDER BY points DESC LIMIT 30").fetchall()
                await query.answer()
                if not vips:
                    await query.message.reply_text("👑 বর্তমানে কোনো VIP প্রিমিয়াম ইউজার নেই।")
                    return
                lines = [f"👑 <b>VIP প্রিমিয়াম মেম্বার তালিকা ({len(vips)} জন)</b>\n{DIVIDER}"]
                for v in vips:
                    lines.append(f"• <b>{html.escape(v['name'] or 'User')}</b> — ID: <code>{v['user_id']}</code> ({v['points']} pts)")
                await query.message.reply_text("<blockquote>" + "\n".join(lines) + "</blockquote>", parse_mode=ParseMode.HTML)
            elif action == "orders":
                with get_db() as conn:
                    orders = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 10").fetchall()
                await query.answer()
                if not orders:
                    await query.message.reply_text("📦 এখনো কোনো অর্ডার জমা পড়েনি।")
                    return
                lines = [f"📦 <b>সর্বশেষ ১০টি অর্ডার তালিকা</b>\n{DIVIDER}"]
                for o in orders:
                    lines.append(
                        f"<blockquote>🛒 <b>Order #{o['id']}</b> — {html.escape(o['product_name'])}\n"
                        f"👤 User ID: <code>{o['user_id']}</code>\n"
                        f"📝 বিবরণ: {html.escape(o['customer_details'])}</blockquote>"
                    )
                await query.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
            return

        if data.startswith("admin_delp:"):
            if not is_admin(user.id):
                await query.answer()
                return
            pid = int(data.split(":", 1)[1])
            with get_db() as conn:
                conn.execute("DELETE FROM products WHERE id = ?", (pid,))
                conn.commit()
            await query.answer("✅ পণ্য ডিলিট করা হয়েছে!", show_alert=True)
            await query.message.edit_text(f"🗑️ প্রোডাক্ট ID #{pid} সফলভাবে ডিলিট করা হয়েছে।")
            return

        # Check maintenance & force join for normal users
        if is_maintenance_on() and not is_admin(user.id):
            await query.answer("🔧 বট বর্তমানে রক্ষণাবেক্ষণের জন্য বন্ধ আছে।", show_alert=True)
            return

        if not await check_force_join(update, context):
            await query.answer()
            return

        # 3a. Voice Selection for STT (Voice -> Text language mode)
        if data.startswith("stt_lang:"):
            lang_mode = data.split(":", 1)[1]
            context.user_data["stt_lang"] = lang_mode
            context.user_data["state"] = "WAIT_STT_VOICE"
            lang_label = {
                "bn": "🇧🇩 বাংলা (Bangla)",
                "en": "🇬🇧 English",
                "auto": "🌐 অটো ডিটেক্ট (Bangla + English)",
            }.get(lang_mode, "🇧🇩 বাংলা")
            await query.answer("ভয়েসের ভাষা নির্বাচন করা হয়েছে!")
            await query.message.reply_text(
                f"🎤 <b>নির্বাচিত ভয়েস ভাষা:</b> {lang_label}\n"
                f"{DIVIDER}\n"
                "🎙️ এখন আপনার ভয়েস মেসেজ (Voice Message) রেকর্ড করে বা ফরোয়ার্ড করে পাঠান:",
                parse_mode=ParseMode.HTML,
            )
            return

        # 3. Voice Selection for TTS
        if data.startswith("tts_voice:"):
            voice = data.split(":", 1)[1]
            context.user_data["tts_voice"] = voice
            context.user_data["state"] = "WAIT_TTS_TEXT"
            v_label = VOICE_CHARACTER_LABELS.get(voice, voice)
            await query.answer("ভয়েস ক্যারেক্টার নির্বাচন করা হয়েছে!")
            await query.message.reply_text(
                f"🎙️ <b>নির্বাচিত ভয়েস ক্যারেক্টার:</b>\n<blockquote>{v_label} (<code>{voice}</code>)</blockquote>\n"
                f"{DIVIDER}\n"
                "✍️ এখন আপনার টেক্সট বা স্ক্রিপ্ট পাঠান (সর্বোচ্চ <b>২,৫০০ অক্ষর / 2K+ লাইন</b> পর্যন্ত একসাথে পাঠাতে পারবেন):",
                parse_mode=ParseMode.HTML,
            )
            return

        # 4. Translation Direction Selection
        if data.startswith("trans_dir:"):
            direction = data.split(":", 1)[1]
            context.user_data["trans_dir"] = direction
            context.user_data["state"] = "WAIT_TRANSLATE_TEXT"
            label = "বাংলা → English" if direction == "bn2en" else "English → বাংলা"
            await query.answer()
            await query.message.reply_text(
                f"🌐 <b>অনুবাদের ভাষা:</b> {label}\n"
                f"{DIVIDER}\n"
                "✍️ যে লেখাটি অনুবাদ করতে চান তা পাঠান:",
                parse_mode=ParseMode.HTML,
            )
            return

        # 5. Prayer Times City Selection
        if data.startswith("prayer_city:"):
            city_en, _ = data.split(":", 1)[1].split("|")
            context.user_data["state"] = "WAIT_PRAYER"
            await query.answer("নামাজের সময়সূচী লোড হচ্ছে...")
            msg_out = await asyncio.to_thread(fetch_prayer_times_for_location, city_en)
            add_points(user.id, 1)
            await query.message.reply_text(msg_out, parse_mode=ParseMode.HTML)
            return

        # 5b. News Category Selection
        if data.startswith("news_cat:"):
            topic = data.split(":", 1)[1]
            await query.answer("তাজা খবর লোড হচ্ছে...")
            news_text = await asyncio.to_thread(fetch_google_news_bn, topic)
            news_kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔥 ব্রেকিং", callback_data="news_cat:top"),
                        InlineKeyboardButton("🇧🇩 বাংলাদেশ", callback_data="news_cat:bd"),
                        InlineKeyboardButton("🏏 খেলাধুলা", callback_data="news_cat:sports"),
                    ],
                    [
                        InlineKeyboardButton("🌍 আন্তর্জাতিক", callback_data="news_cat:world"),
                        InlineKeyboardButton("💻 প্রযুক্তি", callback_data="news_cat:tech"),
                        InlineKeyboardButton("🔄 রিফ্রেশ", callback_data=f"news_cat:{topic}"),
                    ],
                ]
            )
            await query.message.reply_text(
                news_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=news_kb,
            )
            return

        # 5c. Jokes Category / Next Joke Selection
        if data.startswith("joke_cat:"):
            j_type = data.split(":", 1)[1]
            await query.answer("মজার জোকস তৈরি হচ্ছে...")
            joke_kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🤣 আরেকটা জোকস", callback_data="joke_cat:ai_random"),
                        InlineKeyboardButton("🎓 ছাত্র-শিক্ষক", callback_data="joke_cat:student"),
                    ],
                    [
                        InlineKeyboardButton("💑 স্বামী-স্ত্রী", callback_data="joke_cat:couple"),
                        InlineKeyboardButton("🤪 বল্টু জোকস", callback_data="joke_cat:boltu"),
                    ],
                ]
            )
            if j_type == "builtin":
                joke_body = random.choice(BANGLA_JOKES)
            else:
                topic_map = {
                    "ai_random": "একটি দমফাটা হাসির নতুন বাংলা জোকস (কৌতুক)",
                    "student": "ছাত্র ও শিক্ষকের মধ্যে একটি মজার দমফাটা হাসির বাংলা জোকস",
                    "couple": "স্বামী ও স্ত্রীর মধ্যে একটি মজার হাসির বাংলা জোকস",
                    "boltu": "বল্টু ও তার বন্ধুদের নিয়ে একটি মজার বাংলা জোকস",
                }
                j_prompt = topic_map.get(j_type, "একটি মজার বাংলা জোকস")
                try:
                    joke_body = await asyncio.to_thread(
                        call_groq_chat,
                        [
                            {
                                "role": "system",
                                "content": "You are a witty Bengali comedian. Write 1 short, clean, genuinely hilarious Bangla joke in dialogue format with funny emojis. Do not use raw asterisks (**).",
                            },
                            {"role": "user", "content": j_prompt},
                        ],
                        0.85,
                        350,
                    )
                    joke_body = clean_ai_text(joke_body)
                except Exception:
                    joke_body = random.choice(BANGLA_JOKES)

            add_points(user.id, 1)
            await query.message.reply_text(
                f"😂 <b>মজার বাংলা জোকস</b>\n{DIVIDER}\n<blockquote>{html.escape(joke_body)}</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=joke_kb,
            )
            return

        # 5d. Crypto Refresh Callback
        if data == "crypto_refresh":
            context.user_data["state"] = "WAIT_CRYPTO"
            await query.answer("লাইভ ক্রিপ্টো দাম আপডেট হচ্ছে...")
            crypto_text = await asyncio.to_thread(fetch_crypto_prices)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 লাইভ রেট রিফ্রেশ করুন", callback_data="crypto_refresh")]])
            await query.message.reply_text(crypto_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return

        # 5e. VIP Info / Upgrade Request Callback
        if data == "vip_info":
            await query.answer()
            context.user_data["state"] = "WAIT_CONTACT_ADMIN"
            await query.message.reply_text(
                f"👑 <b>VIP প্রিমিয়াম মেম্বারশিপ সুবিধাসমূহ</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>"
                f"💎 <b>১. আনলিমিটেড ভিডিও ডাউনলোড:</b> প্রিমিয়াম মোড চালু থাকলেও সব ভিডিও ডাউনলোড করতে পারবেন।\n"
                f"⚡ <b>২. ডাবল পয়েন্ট (2x Points):</b> প্রতিটি টুল ব্যবহারে সাধারণ ইউজারের চেয়ে দ্বিগুণ (+২) পয়েন্ট পাবেন!\n"
                f"🏅 <b>৩. স্পেশাল VIP ব্যাজ:</b> আপনার প্রোফাইলে রাজকীয় 👑 VIP ব্যাজ যুক্ত হবে।\n"
                f"🚀 <b>৪. প্রায়োরিটি সাপোর্ট:</b> অ্যাডমিনের কাছ থেকে দ্রুত কাস্টম সেবা।"
                f"</blockquote>\n\n"
                f"📩 <b>VIP মেম্বারশিপ সক্রিয় করতে এখনই নিচে আপনার মেসেজ লিখে পাঠান (সরাসরি অ্যাডমিনের কাছে চলে যাবে):</b>",
                parse_mode=ParseMode.HTML,
            )
            return

        # 6. Password Generator Length Selection
        if data.startswith("pwd_len:"):
            length = int(data.split(":", 1)[1])
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
            pwd_chars = [
                secrets.choice(string.ascii_uppercase),
                secrets.choice(string.ascii_lowercase),
                secrets.choice(string.digits),
                secrets.choice("!@#$%^&*()-_=+"),
            ] + [secrets.choice(alphabet) for _ in range(length - 4)]
            secrets.SystemRandom().shuffle(pwd_chars)
            pwd = "".join(pwd_chars)
            add_points(user.id, 1)
            await query.answer("পাসওয়ার্ড তৈরি হয়েছে!")
            await query.message.reply_text(
                f"🔐 <b>আপনার {en_to_bn_digits(str(length))} অক্ষরের শক্তিশালী পাসওয়ার্ড</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote><code>{html.escape(pwd)}</code></blockquote>\n"
                f"👆 <i>পাসওয়ার্ডটির ওপর ট্যাপ করলেই কপি হয়ে যাবে।</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        # 7. Quiz Answer Selection
        if data.startswith("quiz_ans:"):
            parts = data.split(":")
            q_idx = int(parts[1])
            chosen = int(parts[2])
            quiz_state = context.user_data.get("quiz")
            if not quiz_state or quiz_state.get("index") != q_idx:
                await query.answer("⚠️ এই প্রশ্নটির উত্তর ইতিমধ্যে দেওয়া হয়েছে।", show_alert=True)
                return

            q = quiz_state["questions"][q_idx]
            correct_idx = q["correct"]
            correct_text = q["options"][correct_idx]

            u_row = get_user(user.id)
            cur_streak = int(u_row["quiz_streak"]) if u_row else 0

            if chosen == correct_idx:
                cur_streak += 1
                pts = 5
                bonus_msg = ""
                if cur_streak % 3 == 0:
                    pts += 2
                    bonus_msg = "\n🔥 <b>টানা ৩টি সঠিক উত্তরের জন্য +২ স্ট্রিক বোনাস!</b>"
                add_points(user.id, pts)
                with get_db() as conn:
                    conn.execute("UPDATE users SET quiz_streak = ? WHERE user_id = ?", (cur_streak, user.id))
                    conn.commit()
                quiz_state["score"] += 1
                quiz_state["earned_points"] += pts
                feedback = f"✅ <b>সঠিক উত্তর! (+{pts} পয়েন্ট)</b>{bonus_msg}"
            else:
                with get_db() as conn:
                    conn.execute("UPDATE users SET quiz_streak = 0 WHERE user_id = ?", (user.id,))
                    conn.commit()
                feedback = f"❌ <b>ভুল উত্তর!</b>\nসঠিক উত্তর ছিল: <b>{html.escape(correct_text)}</b>"

            await query.answer()
            await query.edit_message_text(
                f"🧠 <b>কুইজ প্রশ্ন ({q_idx + 1}/{len(quiz_state['questions'])})</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>❓ {html.escape(q['question'])}</blockquote>\n\n"
                f"{feedback}",
                parse_mode=ParseMode.HTML,
            )
            quiz_state["index"] += 1
            await send_quiz_question(query.message, context, user.id)
            return

        # 8. Shop Buy Button
        if data.startswith("buy_prod:"):
            pid = int(data.split(":", 1)[1])
            with get_db() as conn:
                prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if not prod:
                await query.answer("⚠️ পণ্যটি আর স্টকে নেই।", show_alert=True)
                return
            context.user_data["buy_product"] = {"id": prod["id"], "name": prod["name"], "price": prod["price"]}
            context.user_data["state"] = "WAIT_ORDER_DETAILS"
            await query.answer()
            await query.message.reply_text(
                f"🛍️ <b>অর্ডার ফর্ম: {html.escape(prod['name'])}</b>\n"
                f"{DIVIDER}\n"
                f"💰 <b>মূল্য:</b> {html.escape(prod['price'])}\n\n"
                f"<blockquote>অনুগ্রহ করে <b>একটি মেসেজেই</b> আপনার নিচের তথ্যগুলো লিখে পাঠান:\n"
                f"১. আপনার নাম\n"
                f"২. মোবাইল নম্বর\n"
                f"৩. সম্পূর্ণ ঠিকানা</blockquote>",
                parse_mode=ParseMode.HTML,
            )
            return

    except Exception as e:
        logger.error(f"Callback query error: {e}", exc_info=True)
        try:
            await query.message.reply_text(ERROR_MSG_BN)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MAIN MESSAGE & MENU ROUTER
# ---------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    # 1. Silently ignore banned users
    if is_user_banned(user.id):
        return

    ensure_user(user.id, user.full_name or user.first_name or "User")

    # 2. Check if an Admin is replying to a forwarded Contact Admin message
    if is_admin(user.id) and msg.reply_to_message:
        replied_id = msg.reply_to_message.message_id
        with get_db() as conn:
            row = conn.execute(
                "SELECT user_id FROM forwarded_messages WHERE admin_msg_id = ? AND admin_id = ?",
                (replied_id, user.id),
            ).fetchone()
        if row:
            target_uid = row["user_id"]
            try:
                reply_text = msg.text or msg.caption or ""
                await context.bot.send_message(
                    chat_id=target_uid,
                    text=(
                        f"📩 <b>অ্যাডমিনের উত্তর (Admin Reply)</b>\n"
                        f"{DIVIDER}\n"
                        f"<blockquote>{html.escape(reply_text)}</blockquote>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
                await msg.reply_text("✅ আপনার উত্তর ইউজারের কাছে পাঠানো হয়েছে।")
            except Exception as e:
                logger.error(f"Failed to send admin reply to {target_uid}: {e}")
                await msg.reply_text("⚠️ ইউজারের কাছে মেসেজ পাঠানো যায়নি।")
            return

    text = (msg.text or "").strip()
    matched_btn = match_menu_button(text)

    # 3. Handle "🏠 মেনু" reset button at any time
    if matched_btn == BTN_MENU:
        context.user_data["state"] = None
        context.user_data.pop("pdf_images", None)
        context.user_data.pop("quiz", None)
        await msg.reply_text(
            f"🏠 <b>মূল মেনুতে ফিরে এসেছেন</b>\n{DIVIDER}\n👇 নিচের বাটন থেকে আপনার পছন্দের যেকোনো অপশন বেছে নিন:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_markup(user.id),
        )
        return

    # 4. Handle "✅ PDF বানান" button
    if matched_btn == BTN_MAKE_PDF_DONE:
        await finalize_images_to_pdf(msg, user.id, context)
        return

    # 5. If user tapped any main menu button, switch mode & prompt immediately
    if matched_btn:
        if is_maintenance_on() and not is_admin(user.id):
            await msg.reply_text(
                "🔧 বট বর্তমানে রক্ষণাবেক্ষণ (Maintenance) কাজের জন্য সাময়িকভাবে বন্ধ আছে। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন 🙏"
            )
            return
        if not await check_force_join(update, context):
            return
        await route_menu_button(matched_btn, msg, user, context)
        return

    # 6. Handle Admin Interactive States
    state = context.user_data.get("state")
    if is_admin(user.id) and state and state.startswith("ADMIN_"):
        if state == "ADMIN_BROADCAST":
            context.user_data["state"] = None
            with get_db() as conn:
                all_users = conn.execute("SELECT user_id FROM users WHERE banned = 0").fetchall()
            sent = 0
            failed = 0
            status_msg = await msg.reply_text("📢 ব্রডকাস্ট পাঠানো হচ্ছে...")
            for r in all_users:
                uid = r["user_id"]
                try:
                    await msg.copy(chat_id=uid)
                    sent += 1
                    await asyncio.sleep(0.04)
                except Exception:
                    failed += 1
            await status_msg.edit_text(
                f"✅ <b>ব্রডকাস্ট সম্পন্ন!</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>• সফল: <b>{sent} জন</b>\n• ব্যর্থ: <b>{failed} জন</b></blockquote>",
                parse_mode=ParseMode.HTML,
            )
            return

        if state == "ADMIN_SET_CHANNEL":
            context.user_data["state"] = None
            arg = text.strip()
            if arg.lower() in ("off", "none"):
                set_setting("force_join", "off")
                await msg.reply_text("✅ Force Join চ্যানেল বন্ধ (OFF) করা হয়েছে।", reply_markup=get_main_menu_markup(user.id))
            else:
                if not arg.startswith("@") and not arg.startswith("-100"):
                    arg = f"@{arg}"
                set_setting("force_join", arg)
                await msg.reply_text(
                    f"✅ Force Join চ্যানেল সেট করা হয়েছে: <b>{html.escape(arg)}</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_main_menu_markup(user.id),
                )
            return

        if state == "ADMIN_ADD_PRODUCT":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 3 or not all(parts[:3]):
                await msg.reply_text(
                    "⚠️ <b>সঠিক ফরম্যাটে লিখুন:</b>\n<code>পণ্য নাম | দাম | বিবরণ</code>",
                    parse_mode=ParseMode.HTML,
                )
                return
            context.user_data["state"] = None
            name, price, desc = parts[0], parts[1], parts[2]
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO products (name, price, description) VALUES (?, ?, ?)", (name, price, desc))
                pid = cur.lastrowid
                conn.commit()
            await msg.reply_text(
                f"✅ <b>পণ্য সফলভাবে যোগ করা হয়েছে!</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>🆔 ID: <b>#{pid}</b>\n📦 নাম: {html.escape(name)}\n💰 দাম: {html.escape(price)}</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_markup(user.id),
            )
            return

        if state == "ADMIN_BAN_UNBAN":
            target = bn_to_en_digits(text.strip())
            if not target.isdigit():
                await msg.reply_text("⚠️ অনুগ্রহ করে সঠিক সংখ্যার User ID পাঠান।")
                return
            context.user_data["state"] = None
            uid = int(target)
            ensure_user(uid, "User")
            u_row = get_user(uid)
            new_ban = 0 if (u_row and u_row["banned"] == 1) else 1
            with get_db() as conn:
                conn.execute("UPDATE users SET banned = ? WHERE user_id = ?", (new_ban, uid))
                conn.commit()
            status_str = "🚫 ব্যান (Banned)" if new_ban == 1 else "✅ আনব্যান (Unbanned)"
            await msg.reply_text(
                f"ইউজার <code>{uid}</code>-কে <b>{status_str}</b> করা হয়েছে।",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_markup(user.id),
            )
            return

        if state == "ADMIN_VIP_TOGGLE":
            target = bn_to_en_digits(text.strip())
            if not target.isdigit():
                await msg.reply_text("⚠️ অনুগ্রহ করে সঠিক সংখ্যার User ID পাঠান।")
                return
            context.user_data["state"] = None
            uid = int(target)
            ensure_user(uid, "User")
            u_row = get_user(uid)
            new_vip = 0 if (u_row and u_row["premium"] == 1) else 1
            with get_db() as conn:
                conn.execute("UPDATE users SET premium = ? WHERE user_id = ?", (new_vip, uid))
                conn.commit()
            status_str = "👑 VIP প্রিমিয়াম চালু (ON)" if new_vip == 1 else "🆓 সাধারণ মেম্বার (OFF)"
            await msg.reply_text(
                f"ইউজার <code>{uid}</code>-এর স্ট্যাটাস এখন: <b>{status_str}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_markup(user.id),
            )
            if new_vip == 1:
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=(
                            f"👑 <b>অভিনন্দন! আপনি এখন VIP প্রিমিয়াম মেম্বার!</b>\n"
                            f"{DIVIDER}\n"
                            "<blockquote>অ্যাডমিন আপনার অ্যাকাউন্টে <b>💎 VIP প্রিমিয়াম মেম্বারশিপ</b> চালু করে দিয়েছেন! এখন থেকে আপনি সকল প্রিমিয়াম টুল এবং প্রতিবার ব্যবহারে দ্বিগুণ (+২) পয়েন্ট পাবেন 🎉</blockquote>"
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            return

        if state == "ADMIN_GIFT_POINTS":
            nums = re.findall(r"-?\d+", bn_to_en_digits(text))
            if len(nums) < 2:
                await msg.reply_text("⚠️ সঠিক ফরম্যাটে লিখুন: <code>User_ID Points</code>", parse_mode=ParseMode.HTML)
                return
            context.user_data["state"] = None
            uid = int(nums[0])
            pts = int(nums[1])
            ensure_user(uid, "User")
            add_points(uid, pts)
            await msg.reply_text(
                f"🎁 ইউজার <code>{uid}</code>-কে <b>{pts:+} পয়েন্ট</b> দেওয়া হয়েছে!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_markup(user.id),
            )
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"🎁 <b>অভিনন্দন!</b> অ্যাডমিন আপনাকে <b>{pts:+} পয়েন্ট</b> উপহার দিয়েছেন!",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return

    # 7. Check Maintenance Mode & Force Join for non-admins
    if is_maintenance_on() and not is_admin(user.id):
        await msg.reply_text(
            "🔧 বট বর্তমানে রক্ষণাবেক্ষণ (Maintenance) কাজের জন্য সাময়িকভাবে বন্ধ আছে। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন 🙏"
        )
        return

    if not await check_force_join(update, context):
        return

    # 8. Handle incoming Voice, Photo, Document, or Text according to current state
    try:
        if msg.voice or msg.audio:
            await process_voice_message(msg, user.id, context)
            return
        if msg.photo:
            await process_photo_message(msg, user.id, context)
            return
        if msg.document:
            await process_document_message(msg, user.id, context)
            return
        if text:
            await process_state_text(text, msg, user, context)
            return
    except Exception as e:
        logger.error(f"Error handling user input in state {state}: {e}", exc_info=True)
        await msg.reply_text(ERROR_MSG_BN, reply_markup=get_main_menu_markup(user.id))


# ---------------------------------------------------------------------------
# MENU BUTTON ROUTER (STYLISH PROMPTS + NEW TOOLS + ADMIN PANEL)
# ---------------------------------------------------------------------------
async def route_menu_button(
    btn: str, msg, user, context: ContextTypes.DEFAULT_TYPE
) -> None:
    context.user_data["state"] = None

    try:
        if btn == BTN_ADMIN_PANEL:
            if is_admin(user.id):
                await send_admin_panel(msg, user.id)
            else:
                await msg.reply_text("🔒 এই প্যানেলটি শুধুমাত্র বট অ্যাডমিনের জন্য সংরক্ষিত।")
            return

        if btn == BTN_AI_CHAT:
            context.user_data["state"] = "WAIT_AI_CHAT"
            await msg.reply_text(
                f"🤖 <b>স্মার্ট AI চ্যাট অ্যাসিস্ট্যান্ট</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার যেকোনো প্রশ্ন, পড়াশোনা, কোডিং বা সাধারণ কথা বাংলায় অথবা ইংরেজিতে লিখুন। বট আপনার পূর্বের ৮টি কথোপকথন মনে রাখবে!</blockquote>\n"
                "✍️ <b>আপনার প্রশ্নটি লিখুন:</b>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_TTS:
            default_voice = context.user_data.get("tts_voice", "bn-BD-NabanitaNeural")
            context.user_data["tts_voice"] = default_voice
            context.user_data["state"] = "WAIT_TTS_TEXT"
            v_label = VOICE_CHARACTER_LABELS.get(default_voice, default_voice)
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("👩 নবনীতা (মিষ্টি বাংলা)", callback_data="tts_voice:bn-BD-NabanitaNeural"),
                        InlineKeyboardButton("👨 প্রদীপ (ভরাট বাংলা)", callback_data="tts_voice:bn-BD-PradeepNeural"),
                    ],
                    [
                        InlineKeyboardButton("👩‍🎤 তানিশা (স্টুডিও বাংলা)", callback_data="tts_voice:bn-IN-TanishaaNeural"),
                        InlineKeyboardButton("👨‍🎤 ভাস্কর (আবৃত্তি বাংলা)", callback_data="tts_voice:bn-IN-BashkarNeural"),
                    ],
                    [
                        InlineKeyboardButton("👩 Aria (US Female)", callback_data="tts_voice:en-US-AriaNeural"),
                        InlineKeyboardButton("👨 Christopher (US Male)", callback_data="tts_voice:en-US-ChristopherNeural"),
                    ],
                    [
                        InlineKeyboardButton("👑 Sonia (UK Royal)", callback_data="tts_voice:en-GB-SoniaNeural"),
                        InlineKeyboardButton("🎶 Swara (Hindi/Urdu)", callback_data="tts_voice:hi-IN-SwaraNeural"),
                    ],
                ]
            )
            await msg.reply_text(
                f"🎙️ <b>স্টুডিও ভয়েস মেকার (AI Text-to-Speech)</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>🔊 <b>বর্তমান ভয়েস ক্যারেক্টার:</b>\n{v_label}\n\n"
                f"✨ নিচের ৮টি প্রিমিয়াম কণ্ঠ থেকে আপনার পছন্দের ভয়েস বেছে নিন অথবা সরাসরি আপনার লেখা পাঠান (সর্বোচ্চ <b>২,৫০০ অক্ষর / 2K+</b> পর্যন্ত সাপোর্ট করে)!</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )

        elif btn == BTN_STT:
            cur_lang = context.user_data.get("stt_lang", "bn")
            context.user_data["stt_lang"] = cur_lang
            context.user_data["state"] = "WAIT_STT_VOICE"
            lang_label = {
                "bn": "🇧🇩 বাংলা (Default)",
                "en": "🇬🇧 English",
                "auto": "🌐 অটো (Bangla + English)",
            }.get(cur_lang, "🇧🇩 বাংলা (Default)")
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🇧🇩 বাংলা ভয়েস", callback_data="stt_lang:bn"),
                        InlineKeyboardButton("🇬🇧 English Voice", callback_data="stt_lang:en"),
                    ],
                    [
                        InlineKeyboardButton("🌐 অটো (বাংলা + English)", callback_data="stt_lang:auto"),
                    ],
                ]
            )
            await msg.reply_text(
                f"🎤 <b>ভয়েস থেকে টেক্সট (AI Voice → Text)</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>🔊 <b>বর্তমান ভাষা:</b> {lang_label}\n"
                f"নিচের বাটন থেকে ভয়েসের ভাষা পরিবর্তন করতে পারেন, অথবা সরাসরি একটি <b>Voice Message</b> রেকর্ড করে পাঠান—আমি নিখুঁতভাবে টেক্সটে রূপান্তর করে দেব!</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )

        elif btn == BTN_AI_IMG:
            context.user_data["state"] = "WAIT_AI_IMG"
            await msg.reply_text(
                f"🖼️ <b>AI ছবি জেনারেটর (100% Watermark-Free HD)</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনি কীসের ছবি তৈরি করতে চান তা বিস্তারিত লিখুন (ইংরেজি বা বাংলায়)।\n"
                "💡 <b>উদাহরণ:</b> <code>A majestic royal Bengal tiger in Sundarbans at golden hour, photorealistic 8k</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_VID_DL:
            if is_premium_mode_on() and not is_user_premium(user.id):
                await msg.reply_text(
                    f"💎 <b>প্রিমিয়াম ফিচার!</b>\n{DIVIDER}\n"
                    "<blockquote>বর্তমানে ভিডিও ডাউনলোড শুধুমাত্র প্রিমিয়াম মেম্বারদের জন্য চালু আছে। প্রিমিয়াম নিতে অ্যাডমিনের সাথে যোগাযোগ করুন।</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
                return
            context.user_data["state"] = "WAIT_VID_DL"
            await msg.reply_text(
                f"📥 <b>অল-ইন-ওয়ান ভিডিও ডাউনলোডার</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>🎬 <b>TikTok অথবা Instagram</b>-এর যেকোনো পাবলিক ভিডিও বা Reels-এর লিংক পাঠান:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_TRANSLATE:
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🇧🇩 বাংলা → English 🇬🇧", callback_data="trans_dir:bn2en"),
                        InlineKeyboardButton("🇬🇧 English → বাংলা 🇧🇩", callback_data="trans_dir:en2bn"),
                    ]
                ]
            )
            await msg.reply_text(
                f"🌐 <b>স্মার্ট ভাষা অনুবাদক (Translator)</b>\n"
                f"{DIVIDER}\n"
                "👇 অনুগ্রহ করে অনুবাদের দিক নির্বাচন করুন:",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )

        elif btn == BTN_CAPTION:
            context.user_data["state"] = "WAIT_CAPTION"
            await msg.reply_text(
                f"✍️ <b>সোশ্যাল মিডিয়া ক্যাপশন মেকার</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>কোন বিষয়ের ওপর ক্যাপশন চান তা লিখুন (যেমন: বৃষ্টির দিন, বন্ধুদের সাথে আড্ডা, প্রোফাইল পিকচার, ভ্রমণ):</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_STORY:
            context.user_data["state"] = "WAIT_STORY"
            await msg.reply_text(
                f"📖 <b>গল্প ও কবিতা লেখক</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>কোন বিষয়ের ওপর গল্প বা কবিতা চান তা লিখুন (যেমন: গ্রামের সন্ধ্যা নিয়ে কবিতা, একটি রহস্যময় গল্প):</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_IMG_PDF:
            context.user_data["state"] = "WAIT_IMG_PDF"
            context.user_data["pdf_images"] = []
            await msg.reply_text(
                f"🖼️ <b>ছবি থেকে PDF কনভার্টার</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>একের পর এক ছবি (Photo) পাঠাতে থাকুন। সব ছবি পাঠানো শেষ হলে নিচের <b>✅ PDF বানান</b> বাটনে চাপুন!</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=PDF_COLLECT_MARKUP,
            )

        elif btn == BTN_PDF_SUM:
            context.user_data["state"] = "WAIT_PDF_SUM"
            await msg.reply_text(
                f"📄 <b>PDF সারাংশ (AI PDF Summary)</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>অনুগ্রহ করে আপনার PDF ফাইলটি ডকুমেন্ট হিসেবে পাঠান, আমি তার মূল বক্তব্য সহজ বাংলায় সাজিয়ে দেব!</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_PRAYER:
            context.user_data["state"] = "WAIT_PRAYER"
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🕌 ঢাকা", callback_data="prayer_city:Dhaka|ঢাকা"),
                        InlineKeyboardButton("🕌 খুলনা", callback_data="prayer_city:Khulna|খুলনা"),
                    ],
                    [
                        InlineKeyboardButton("🕌 চট্টগ্রাম", callback_data="prayer_city:Chittagong|চট্টগ্রাম"),
                        InlineKeyboardButton("🕌 রাজশাহী", callback_data="prayer_city:Rajshahi|রাজশাহী"),
                    ],
                    [
                        InlineKeyboardButton("🕌 সিলেট", callback_data="prayer_city:Sylhet|সিলেট"),
                        InlineKeyboardButton("🕌 বরিশাল", callback_data="prayer_city:Barisal|বরিশাল"),
                    ],
                    [
                        InlineKeyboardButton("🕌 রংপুর", callback_data="prayer_city:Rangpur|রংপুর"),
                        InlineKeyboardButton("🕌 ময়মনসিংহ", callback_data="prayer_city:Mymensingh|ময়মনসিংহ"),
                    ],
                ]
            )
            await msg.reply_text(
                f"🕐 <b>বাংলাদেশের ৬৪ জেলার নামাজ ও সাহরি-ইফতারের সময়সূচী</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>👇 নিচের বাটন থেকে বিভাগ সিলেক্ট করুন, অথবা <b>আপনার যেকোনো জেলার নাম</b> (যেমন: <code>যশোর</code>, <code>কুমিল্লা</code>, <code>বগুড়া</code>, <code>কক্সবাজার</code>, <code>সাতক্ষীরা</code>) লিখে পাঠান:</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )

        elif btn == BTN_WEATHER:
            context.user_data["state"] = "WAIT_WEATHER"
            await msg.reply_text(
                f"🌦️ <b>লাইভ আবহাওয়ার খবর</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার শহরের নাম লিখুন:\n"
                "যেমন: <code>Dhaka</code>, <code>Khulna</code>, <code>Chittagong</code>, <code>Sylhet</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_CURRENCY:
            context.user_data["state"] = "WAIT_CURRENCY"
            await msg.reply_text(
                f"💱 <b>লাইভ কারেন্সি কনভার্টার</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>পরিমাণ ও মুদ্রার নাম লিখুন:\n"
                "• <code>100 USD</code>\n"
                "• <code>100 dollar</code>\n"
                "• <code>500 taka</code>\n"
                "• <code>50 riyal to bdt</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_SHORTURL:
            context.user_data["state"] = "WAIT_SHORTURL"
            await msg.reply_text(
                f"🔗 <b>লিংক শর্টনার (URL Shortener)</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার বড় ওয়েবসাইট লিংকটি (http/https সহ) পাঠান:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_DICT:
            context.user_data["state"] = "WAIT_DICT"
            await msg.reply_text(
                f"📚 <b>ইংরেজি থেকে বাংলা ডিকশনারি</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>যেকোনো একটি ইংরেজি শব্দ (Word) লিখে পাঠান:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_JOKES:
            add_points(user.id, 1)
            bn_joke = random.choice(BANGLA_JOKES)
            joke_kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🤣 নতুন AI জোকস", callback_data="joke_cat:ai_random"),
                        InlineKeyboardButton("🎓 ছাত্র-শিক্ষক", callback_data="joke_cat:student"),
                    ],
                    [
                        InlineKeyboardButton("💑 স্বামী-স্ত্রী", callback_data="joke_cat:couple"),
                        InlineKeyboardButton("🤪 বল্টু জোকস", callback_data="joke_cat:boltu"),
                    ],
                ]
            )
            await msg.reply_text(
                f"😂 <b>মজার বাংলা জোকস</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>{bn_joke}</blockquote>\n\n"
                f"👇 <i>আনলিমিটেড নতুন জোকস পড়তে নিচের ক্যাটাগরি বাটনে ট্যাপ করুন:</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=joke_kb,
            )

        elif btn == BTN_BMI:
            context.user_data["state"] = "WAIT_BMI"
            await msg.reply_text(
                f"⚖️ <b>BMI ও স্বাস্থ্য ক্যালকুলেটর</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার ওজন (কেজি) এবং উচ্চতা (ফুট.ইঞ্চি) পাঠান।\n"
                "💡 <b>উদাহরণ:</b> <code>70 5.7</code> অথবা <code>70 kg 5.7</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_QR:
            context.user_data["state"] = "WAIT_QR"
            await msg.reply_text(
                f"🔳 <b>QR Code জেনারেটর</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>যে লেখা বা লিংকের QR Code তৈরি করতে চান তা পাঠান:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_NEWS:
            wait_m = await msg.reply_text("⏳ <b>আজকের তাজা খবর লোড হচ্ছে, অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
            news_text = await asyncio.to_thread(fetch_google_news_bn, "top")
            add_points(user.id, 1)
            news_kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔥 ব্রেকিং", callback_data="news_cat:top"),
                        InlineKeyboardButton("🇧🇩 বাংলাদেশ", callback_data="news_cat:bd"),
                        InlineKeyboardButton("🏏 খেলাধুলা", callback_data="news_cat:sports"),
                    ],
                    [
                        InlineKeyboardButton("🌍 আন্তর্জাতিক", callback_data="news_cat:world"),
                        InlineKeyboardButton("💻 প্রযুক্তি", callback_data="news_cat:tech"),
                        InlineKeyboardButton("🔄 রিফ্রেশ", callback_data="news_cat:top"),
                    ],
                ]
            )
            await wait_m.edit_text(
                news_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=news_kb,
            )

        elif btn == BTN_CRYPTO:
            context.user_data["state"] = "WAIT_CRYPTO"
            wait_m = await msg.reply_text("⏳ <b>ক্রিপ্টোকারেন্সির লাইভ বাজারমূল্য লোড হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
            crypto_text = await asyncio.to_thread(fetch_crypto_prices)
            add_points(user.id, 1)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 লাইভ রেট রিফ্রেশ করুন", callback_data="crypto_refresh")]])
            await wait_m.edit_text(crypto_text, parse_mode=ParseMode.HTML, reply_markup=kb)

        elif btn == BTN_AGE:
            context.user_data["state"] = "WAIT_AGE"
            await msg.reply_text(
                f"🎂 <b>নিখুঁত বয়স ক্যালকুলেটর</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার জন্ম তারিখ <code>DD-MM-YYYY</code> ফরম্যাটে পাঠান।\n"
                "💡 <b>উদাহরণ:</b> <code>15-08-2002</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_UNIT:
            context.user_data["state"] = "WAIT_UNIT"
            await msg.reply_text(
                f"🔄 <b>ইউনিট কনভার্টার</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>কনভার্ট করতে নিচের মতো করে লিখুন:\n"
                "• <code>10 kg to pound</code>\n"
                "• <code>5 km to mile</code>\n"
                "• <code>37 C to F</code>\n"
                "• <code>12 inch to cm</code>\n"
                "• <code>5 liter to gallon</code>\n"
                "• <code>5.7 feet to cm</code>\n"
                "• <code>10 meter to feet</code>\n"
                "• <code>2 hour to minute</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_FANCY:
            context.user_data["state"] = "WAIT_FANCY"
            await msg.reply_text(
                f"✨ <b>ফ্যান্সি টেক্সট জেনারেটর</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার নাম বা যেকোনো ইংরেজি লেখা পাঠান:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_LOVE:
            context.user_data["state"] = "WAIT_LOVE"
            await msg.reply_text(
                f"❤️ <b>Love ক্যালকুলেটর</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>দুইজনের নাম কমা (,) বা '+' দিয়ে লিখুন।\n"
                "💡 <b>উদাহরণ:</b> <code>Rahim, Karima</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_COMPRESS:
            context.user_data["state"] = "WAIT_COMPRESS"
            await msg.reply_text(
                f"🗜️ <b>ইমেজ কমপ্রেসর (Photo Compressor)</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>কমপ্রেস করার জন্য একটি ছবি (Photo) পাঠান:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_LYRICS:
            context.user_data["state"] = "WAIT_LYRICS"
            await msg.reply_text(
                f"🎵 <b>গানের তথ্য ও লিরিক্স</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>গানের নাম অথবা প্রথম লাইনটি লিখে পাঠান:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_PASSWORD:
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔐 ৮ অক্ষর", callback_data="pwd_len:8"),
                        InlineKeyboardButton("🔐 ১২ অক্ষর", callback_data="pwd_len:12"),
                        InlineKeyboardButton("🔐 ১৬ অক্ষর", callback_data="pwd_len:16"),
                    ]
                ]
            )
            await msg.reply_text(
                f"🔐 <b>সিকিউর পাসওয়ার্ড জেনারেটর</b>\n"
                f"{DIVIDER}\n"
                "👇 কত অক্ষরের পাসওয়ার্ড তৈরি করতে চান তা বেছে নিন:",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )

        elif btn == BTN_DUA:
            day_of_year = datetime.date.today().timetuple().tm_yday
            dua = SEVEN_DUAS[day_of_year % len(SEVEN_DUAS)]
            add_points(user.id, 1)
            await msg.reply_text(
                f"🤲 <b>আজকের মাসনুন দোয়া</b>\n"
                f"{DIVIDER}\n"
                f"📌 <b>{dua['title']}</b>\n\n"
                f"<blockquote>📖 <b>আরবি:</b>\n{dua['arabic']}</blockquote>\n\n"
                f"<blockquote>🇧🇩 <b>বাংলা অর্থ:</b>\n{dua['bangla']}</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_REMINDER:
            context.user_data["state"] = "WAIT_REMINDER"
            await msg.reply_text(
                f"⏰ <b>স্মার্ট রিমাইন্ডার অ্যালার্ম</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>কত সময় পরে এবং কী মনে করিয়ে দিতে হবে তা নিচের মতো লিখুন:\n"
                "• <code>10 মিনিট পরে পানি খাবো</code>\n"
                "• <code>30 minute por ghumabo</code>\n"
                "• <code>1 ghonta pore call</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_QUIZ:
            status_msg = await msg.reply_text("🧠 আপনার জন্য ৫টি বাংলা কুইজ প্রশ্ন তৈরি করা হচ্ছে, একটু অপেক্ষা করুন...")
            questions = await asyncio.to_thread(generate_quiz_questions)
            add_points(user.id, 1)
            context.user_data["quiz"] = {
                "questions": questions,
                "index": 0,
                "score": 0,
                "earned_points": 0,
            }
            await status_msg.delete()
            await send_quiz_question(msg, context, user.id)

        # --- 6 NEW HIGH-UTILITY BUTTONS ---
        elif btn == BTN_GRAMMAR:
            context.user_data["state"] = "WAIT_GRAMMAR"
            await msg.reply_text(
                f"📝 <b>বানান ও Grammar সংশোধক</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার যেকোনো ইংরেজি বা বাংলা বাক্য পাঠান। বট সেটির বানান ও ব্যাকরণগত ভুল ঠিক করে প্রফেশনালভাবে সাজিয়ে দেবে!</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_EMAIL_CV:
            context.user_data["state"] = "WAIT_EMAIL_CV"
            await msg.reply_text(
                f"📧 <b>ইমেইল, দরখাস্ত ও CV রাইটার</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনি কী বিষয়ে ইমেইল, ছুটির দরখাস্ত বা চাকরির কভার লেটার লিখতে চান তা সংক্ষেপে বলুন:\n"
                "💡 যেমন: <code>অসুস্থতার জন্য ৩ দিনের ছুটির আবেদন</code> অথবা <code>Job application email for Web Developer</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_CODE_HELP:
            context.user_data["state"] = "WAIT_CODE_HELP"
            await msg.reply_text(
                f"💻 <b>কোড জেনারেটর ও ডিবাগার</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>যেকোনো প্রোগ্রামিং ভাষায় (Python, JS, C++, HTML) কোড লিখতে বা এরর ঠিক করতে আপনার সমস্যাটি লিখুন:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_BIO_GEN:
            context.user_data["state"] = "WAIT_BIO_GEN"
            await msg.reply_text(
                f"🪪 <b>স্টাইলিশ প্রোফাইল বায়ো মেকার</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার নাম বা পেশা/শখ লিখে পাঠান (যেমন: <code>Tonmoy, Student & Tech Lover</code>)। বট আপনার Facebook, Instagram ও Telegram-এর জন্য ৫টি ভিআইপি বায়ো তৈরি করে দেবে!</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_DREAM_ISLAM:
            context.user_data["state"] = "WAIT_DREAM_ISLAM"
            await msg.reply_text(
                f"🌙 <b>স্বপ্ন ও ইসলামিক প্রশ্নোত্তর</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>কুরআন ও সহীহ হাদিসের আলোকে যেকোনো ইসলামিক মাসআলা, দোয়া বা স্বপ্নের তাবীর সম্পর্কে আপনার প্রশ্নটি লিখুন:</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_MATH_SOLVE:
            context.user_data["state"] = "WAIT_MATH_SOLVE"
            await msg.reply_text(
                f"🧮 <b>অংক ও বিজ্ঞান সমাধানকারী</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার গণিত, পদার্থবিজ্ঞান বা রসায়নের যেকোনো অংক বা প্রশ্ন লিখে পাঠান—ধাপে ধাপে সহজ বাংলায় সমাধান পেয়ে যাবেন!</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_BLOOD_INFO:
            context.user_data["state"] = "WAIT_BLOOD_INFO"
            await msg.reply_text(
                f"🩸 <b>রক্তের গ্রুপ ও ডোনার গাইড</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>"
                "🔹 <b>O+</b> ➔ দিতে পারবে: O+, A+, B+, AB+ | নিতে পারবে: O+, O-\n"
                "🔹 <b>O- (সর্বজনীন দাতা)</b> ➔ সবাইকে দিতে পারবে | নিতে পারবে: শুধু O-\n"
                "🔹 <b>A+</b> ➔ দিতে পারবে: A+, AB+ | নিতে পারবে: A+, A-, O+, O-\n"
                "🔹 <b>A-</b> ➔ দিতে পারবে: A+, A-, AB+, AB- | নিতে পারবে: A-, O-\n"
                "🔹 <b>B+</b> ➔ দিতে পারবে: B+, AB+ | নিতে পারবে: B+, B-, O+, O-\n"
                "🔹 <b>B-</b> ➔ দিতে পারবে: B+, B-, AB+, AB- | নিতে পারবে: B-, O-\n"
                "🔹 <b>AB+ (সর্বজনীন গ্রহীতা)</b> ➔ দিতে পারবে: শুধু AB+ | সবার রক্ত নিতে পারবে\n"
                "🔹 <b>AB-</b> ➔ দিতে পারবে: AB+, AB- | নিতে পারবে: AB-, A-, B-, O-"
                "</blockquote>\n\n"
                "✍️ <i>রক্তদান বা হিমোগ্লোবিন নিয়ে যেকোনো প্রশ্ন থাকলে নিচে লিখে পাঠান:</i>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_DIET_PLAN:
            context.user_data["state"] = "WAIT_DIET_PLAN"
            await msg.reply_text(
                f"🥗 <b>পার্সোনালাইজড ডায়েট ও স্বাস্থ্য চার্ট</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার <b>বয়স, ওজন এবং লক্ষ্য</b> (ওজন কমানো / ওজন বাড়ানো / ফিট থাকা / ডায়াবেটিস কন্ট্রোল) লিখে পাঠান।\n"
                "💡 যেমন: <code>বয়স ২২, ওজন ৭৮ কেজি, দ্রুত ওজন কমানোর দেশি খাবারের ডায়েট চার্ট চাই</code></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_BIZ_IDEA:
            context.user_data["state"] = "WAIT_BIZ_IDEA"
            await msg.reply_text(
                f"💼 <b>বিজনেস আইডিয়া ও ব্র্যান্ড নেম জেনারেটর</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনার বাজেট বা পছন্দের ক্ষেত্র লিখুন (যেমন: <code>১০ হাজার টাকায় ছাত্রদের জন্য ব্যবসা</code> অথবা <code>কাপড়ের ফেসবুক পেজের সুন্দর নাম</code>):</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_MOVIE_REC:
            context.user_data["state"] = "WAIT_MOVIE_REC"
            await msg.reply_text(
                f"🎬 <b>মুভি ও ওয়েব সিরিজ রিকমেন্ডেশন</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>আপনি কোন ধরনের মুভি বা সিরিজ দেখতে চান তা লিখুন (যেমন: <code>সাসপেন্স থ্রিলার</code>, <code>রোমান্টিক কোরিয়ান ড্রামা</code>, <code>সেরা বাংলা নাটক</code>, <code>হলিউড অ্যাকশন</code>):</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_SHOP:
            with get_db() as conn:
                products = conn.execute("SELECT * FROM products ORDER BY id ASC").fetchall()
            if not products:
                await msg.reply_text(
                    f"🛍️ <b>অফিসিয়াল শপ</b>\n{DIVIDER}\n"
                    "<blockquote>বর্তমানে শপে কোনো পণ্য নেই। অনুগ্রহ করে পরে আবার দেখুন!</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
                return
            await msg.reply_text(f"🛍️ <b>আমাদের শপের পণ্যসমূহ</b>\n{DIVIDER}", parse_mode=ParseMode.HTML)
            for p in products:
                kb = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🛒 অর্ডার করুন (Buy Now)", callback_data=f"buy_prod:{p['id']}")]]
                )
                await msg.reply_text(
                    f"📦 <b>{html.escape(p['name'])}</b>\n"
                    f"<blockquote>💰 <b>মূল্য:</b> {html.escape(p['price'])}\n"
                    f"📝 <b>বিবরণ:</b> {html.escape(p['description'])}</blockquote>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )

        elif btn == BTN_CONTACT:
            context.user_data["state"] = "WAIT_CONTACT_ADMIN"
            await msg.reply_text(
                f"📩 <b>সরাসরি অ্যাডমিনের সাথে যোগাযোগ</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>অ্যাডমিনের কাছে আপনার মেসেজ, মতামত বা প্রশ্নটি লিখে পাঠান। অ্যাডমিন রিপ্লাই দিলে আপনি এখানেই উত্তর পেয়ে যাবেন!</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_PROFILE:
            u = get_user(user.id)
            pts = int(u["points"]) if u else 0
            lvl = get_level_name(pts)
            rank = get_user_rank(user.id)
            refs = get_referral_count(user.id)
            vip_status = "👑 VIP প্রিমিয়াম মেম্বার (2x Points)" if is_user_premium(user.id) else "🆓 ফ্রি মেম্বার"
            bot_uname = context.bot.username or "Bot"
            ref_link = f"https://t.me/{bot_uname}?start=ref_{user.id}"
            prof_kb = None
            if not is_user_premium(user.id):
                prof_kb = InlineKeyboardMarkup([[InlineKeyboardButton("👑 VIP প্রিমিয়াম মেম্বারশিপ নিন", callback_data="vip_info")]])
            await msg.reply_text(
                f"👤 <b>ইউজার প্রোফাইল ড্যাশবোর্ড</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>"
                f"🏷️ <b>নাম:</b> {html.escape(user.full_name or 'User')}\n"
                f"🆔 <b>আইডি:</b> <code>{user.id}</code>\n"
                f"💎 <b>অ্যাকাউন্ট স্ট্যাটাস:</b> {vip_status}\n"
                f"⭐ <b>মোট পয়েন্ট:</b> {pts}\n"
                f"🏅 <b>লেভেল:</b> {lvl}\n"
                f"🏆 <b>গ্লোবাল র‍্যাংক:</b> #{rank}\n"
                f"👥 <b>মোট রেফারেল:</b> {refs} জন"
                f"</blockquote>\n\n"
                f"🔗 <b>আপনার রেফারেল লিংক:</b>\n<code>{ref_link}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=prof_kb,
            )

        elif btn == BTN_LEADERBOARD:
            with get_db() as conn:
                top_all = conn.execute(
                    "SELECT user_id, name, points FROM users ORDER BY points DESC LIMIT 10"
                ).fetchall()
                top_week = conn.execute(
                    "SELECT user_id, name, week_points FROM users ORDER BY week_points DESC LIMIT 5"
                ).fetchall()
            my_rank = get_user_rank(user.id)
            u = get_user(user.id)
            my_pts = int(u["points"]) if u else 0

            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            all_lines = []
            for i, r in enumerate(top_all, 1):
                badge = medals.get(i, f"{i}.")
                all_lines.append(f"{badge} <b>{html.escape(r['name'] or 'User')}</b> — <code>{r['points']} pts</code>")

            week_lines = []
            for i, r in enumerate(top_week, 1):
                badge = medals.get(i, f"{i}.")
                week_lines.append(f"{badge} <b>{html.escape(r['name'] or 'User')}</b> — <code>{r['week_points']} pts</code>")

            await msg.reply_text(
                f"🏆 <b>গ্লোবাল লিডারবোর্ড (Leaderboard)</b>\n"
                f"{DIVIDER}\n"
                f"👑 <b>সর্বকালের সেরা ১০ জন (All-Time Top 10):</b>\n"
                f"<blockquote>" + ("\n".join(all_lines) if all_lines else "এখনো কেউ নেই") + "</blockquote>\n\n"
                f"🔥 <b>এই সপ্তাহের সেরা ৫ জন (This Week Top 5):</b>\n"
                f"<blockquote>" + ("\n".join(week_lines) if week_lines else "এখনো কেউ নেই") + "</blockquote>\n\n"
                f"👤 <b>আপনার অবস্থান:</b> র‍্যাংক <b>#{my_rank}</b> ({my_pts} পয়েন্ট)",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_DAILY:
            today_str = datetime.date.today().isoformat()
            u = get_user(user.id)
            if u and u["last_daily"] == today_str:
                await msg.reply_text(
                    f"⏳ <b>ডেইলি বোনাস ইতিমধ্যে নেওয়া হয়েছে!</b>\n{DIVIDER}\n"
                    "<blockquote>আপনি আজকের বোনাস ইতিমধ্যে সংগ্রহ করেছেন। আগামীকাল আবার নতুন বোনাস নিতে পারবেন!</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
                return
            yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
            streak = (int(u["daily_streak"]) + 1) if (u and u["last_daily"] == yesterday_str) else 1
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET points = points + 5, week_points = week_points + 5, last_daily = ?, daily_streak = ? WHERE user_id = ?",
                    (today_str, streak, user.id),
                )
                conn.commit()
            await msg.reply_text(
                f"🎁 <b>ডেইলি বোনাস ক্লেইম সফল!</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>🎉 অভিনন্দন! আপনি আজকের ডেইলি বোনাস <b>+৫ পয়েন্ট</b> পেয়েছেন!\n"
                f"🔥 <b>ডেইলি স্ট্রিক:</b> টানা {streak} দিন</blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_SPIN:
            today_str = datetime.date.today().isoformat()
            u = get_user(user.id)
            if u and u["last_spin"] == today_str:
                await msg.reply_text(
                    f"🎰 <b>আজকের স্পিন শেষ!</b>\n{DIVIDER}\n"
                    "<blockquote>আপনি আজকের ফ্রি লাকি স্পিন ইতিমধ্যে ব্যবহার করেছেন। আগামীকাল আবার ভাগ্য পরীক্ষা করুন!</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
                return
            won = random.randint(1, 50)
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET points = points + ?, week_points = week_points + ?, last_spin = ? WHERE user_id = ?",
                    (won, won, today_str, user.id),
                )
                conn.commit()
            await msg.reply_text(
                f"🎰 <b>লাকি স্পিন ফলাফল!</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>🎉 অভিনন্দন! ভাগ্যের চাকা ঘুরিয়ে আপনি জিতেছেন <b>+{won} পয়েন্ট!</b></blockquote>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_REFER:
            bot_uname = context.bot.username or "Bot"
            ref_link = f"https://t.me/{bot_uname}?start=ref_{user.id}"
            refs = get_referral_count(user.id)
            await msg.reply_text(
                f"👥 <b>রেফারেল প্রোগ্রাম (Invite & Earn)</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>আপনার রেফারেল লিংক শেয়ার করে বন্ধুদের আমন্ত্রণ জানান। প্রতিটি নতুন বন্ধু জয়েন করলেই আপনি পাবেন <b>+১০ পয়েন্ট!</b>\n\n"
                f"📊 <b>আপনার মোট রেফারেল:</b> {refs} জন</blockquote>\n\n"
                f"🔗 <b>আপনার রেফারেল লিংক (ট্যাপ করে কপি করুন):</b>\n<code>{ref_link}</code>",
                parse_mode=ParseMode.HTML,
            )

        elif btn == BTN_ABOUT:
            await msg.reply_text(ABOUT_TEXT, parse_mode=ParseMode.HTML)

        elif btn == BTN_HELP:
            await msg.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)

        elif btn == BTN_DEV:
            await msg.reply_text(
                f"👨💻 <b>ডেভেলপার পরিচিতি</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote><b>Developer: @Tonmoy581833</b></blockquote>",
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        logger.error(f"Error in route_menu_button ({btn}): {e}", exc_info=True)
        await msg.reply_text(ERROR_MSG_BN, reply_markup=get_main_menu_markup(user.id))


# ---------------------------------------------------------------------------
# MEDIA & STATE INPUT PROCESSORS
# ---------------------------------------------------------------------------
async def process_voice_message(msg, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
    status_msg = await msg.reply_text("🎤 <b>আপনার ভয়েস মেসেজটি শোনা হচ্ছে এবং নিখুঁত টেক্সটে রূপান্তর করা হচ্ছে...</b>", parse_mode=ParseMode.HTML)
    voice_obj = msg.voice or msg.audio
    tg_file = await context.bot.get_file(voice_obj.file_id)
    tmp_ogg = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg").name
    lang_mode = context.user_data.get("stt_lang", "bn")
    try:
        await tg_file.download_to_drive(custom_path=tmp_ogg)
        text_out = await asyncio.to_thread(call_groq_whisper, tmp_ogg, lang_mode)
        add_points(user_id, 1)
        await status_msg.edit_text(
            f"🎤 <b>ভয়েস থেকে রূপান্তরিত নিখুঁত টেক্সট</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(text_out)}</blockquote>\n"
            f"📋 <i>কপি করতে নিচের লেখার ওপর ট্যাপ করুন:</i>\n"
            f"<code>{html.escape(text_out)}</code>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Voice transcription failed: {e}", exc_info=True)
        await status_msg.edit_text("⚠️ ভয়েসটি স্পষ্ট বোঝা যায়নি। অনুগ্রহ করে একটু পরিষ্কারভাবে আবার ভয়েস পাঠান 🙏")
    finally:
        if os.path.exists(tmp_ogg):
            try:
                os.remove(tmp_ogg)
            except OSError:
                pass


async def process_photo_message(msg, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("state")
    photo = msg.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)

    if state == "WAIT_IMG_PDF":
        tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
        await tg_file.download_to_drive(custom_path=tmp_img)
        imgs = context.user_data.setdefault("pdf_images", [])
        imgs.append(tmp_img)
        await msg.reply_text(
            f"✅ <b>ছবি #{len(imgs)} যুক্ত হয়েছে!</b>\n"
            f"আরও ছবি পাঠাতে পারেন অথবা নিচের <b>✅ PDF বানান</b> বাটনে চাপুন।",
            parse_mode=ParseMode.HTML,
            reply_markup=PDF_COLLECT_MARKUP,
        )
        return

    if state == "WAIT_COMPRESS":
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
        tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix="_compressed.jpg").name
        try:
            await tg_file.download_to_drive(custom_path=tmp_in)
            orig_kb = os.path.getsize(tmp_in) / 1024.0
            with Image.open(tmp_in) as im:
                rgb_im = im.convert("RGB")
                rgb_im.save(tmp_out, format="JPEG", quality=55, optimize=True)
            comp_kb = os.path.getsize(tmp_out) / 1024.0
            add_points(user_id, 1)
            with open(tmp_out, "rb") as f:
                await msg.reply_document(
                    document=f,
                    filename="compressed.jpg",
                    caption=(
                        f"🗜️ <b>ছবি কমপ্রেস সম্পন্ন!</b>\n"
                        f"{DIVIDER}\n"
                        f"<blockquote>• আগের সাইজ: <b>{orig_kb:.1f} KB</b>\n"
                        f"• বর্তমান সাইজ: <b>{comp_kb:.1f} KB</b></blockquote>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
        finally:
            for p in (tmp_in, tmp_out):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        return

    await msg.reply_text(
        "📸 আপনি যদি ছবি থেকে PDF বানাতে চান তবে <b>🖼️ ছবি → PDF</b> বাটনে চাপুন, আর কমপ্রেস করতে চাইলে <b>🗜️ ছবি কমপ্রেস</b> বাটনে চাপুন।",
        parse_mode=ParseMode.HTML,
    )


async def finalize_images_to_pdf(msg, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    imgs: List[str] = context.user_data.get("pdf_images", [])
    if not imgs:
        await msg.reply_text("⚠️ আপনি এখনো কোনো ছবি পাঠাননি! প্রথমে এক বা একাধিক ছবি পাঠান।")
        return

    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    pil_images: List[Image.Image] = []
    try:
        for p in imgs:
            if os.path.exists(p):
                im = Image.open(p).convert("RGB")
                pil_images.append(im)
        if not pil_images:
            await msg.reply_text("⚠️ ছবি প্রসেস করা যায়নি। আবার চেষ্টা করুন।", reply_markup=get_main_menu_markup(user_id))
            return

        first_img, rest_imgs = pil_images[0], pil_images[1:]
        first_img.save(tmp_pdf, "PDF", resolution=100.0, save_all=True, append_images=rest_imgs)
        add_points(user_id, 1)
        context.user_data["state"] = None
        context.user_data.pop("pdf_images", None)

        with open(tmp_pdf, "rb") as f:
            await msg.reply_document(
                document=f,
                filename="images.pdf",
                caption=(
                    f"📄 <b>আপনার PDF প্রস্তুত!</b>\n"
                    f"{DIVIDER}\n"
                    f"<blockquote>✅ মোট <b>{len(pil_images)}টি</b> ছবি দিয়ে সুন্দরভাবে PDF তৈরি করা হয়েছে।</blockquote>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_markup(user_id),
            )
    except Exception as e:
        logger.error(f"PDF creation failed: {e}", exc_info=True)
        await msg.reply_text(ERROR_MSG_BN, reply_markup=get_main_menu_markup(user_id))
    finally:
        for im in pil_images:
            try:
                im.close()
            except Exception:
                pass
        for p in imgs:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        if os.path.exists(tmp_pdf):
            try:
                os.remove(tmp_pdf)
            except OSError:
                pass


async def process_document_message(msg, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = msg.document
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".pdf") and doc.mime_type != "application/pdf":
        await msg.reply_text("⚠️ অনুগ্রহ করে একটি সঠিক PDF ফাইল পাঠান।")
        return

    status_msg = await msg.reply_text("📄 PDF ফাইলটি পড়া হচ্ছে এবং বাংলায় সারাংশ তৈরি করা হচ্ছে...")
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(custom_path=tmp_pdf)

        reader = PdfReader(tmp_pdf)
        extracted = []
        total_chars = 0
        for page in reader.pages:
            t = page.extract_text() or ""
            if t:
                extracted.append(t)
                total_chars += len(t)
                if total_chars >= 6000:
                    break

        full_text = "\n".join(extracted)[:6000].strip()
        if not full_text:
            await status_msg.edit_text("⚠️ এই PDF ফাইল থেকে কোনো টেক্সট পাওয়া যায়নি (হয়তো এটি স্ক্যান করা ছবির PDF)।")
            return

        summary = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": "You are a helpful Bengali assistant. Summarize the given PDF text clearly in clean Bangla bullet points. Do not use markdown asterisks (**), use plain clean text with bullet emojis.",
                },
                {
                    "role": "user",
                    "content": f"নিচের PDF টেক্সটটির মূল সারাংশ সহজ ও সুন্দর বাংলায় লিখে দাও:\n\n{full_text}",
                },
            ],
        )
        add_points(user_id, 1)
        await status_msg.edit_text(
            f"📄 <b>PDF ফাইলের মূল সারাংশ</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(clean_ai_text(summary))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"PDF summary error: {e}", exc_info=True)
        await status_msg.edit_text(ERROR_MSG_BN)
    finally:
        if os.path.exists(tmp_pdf):
            try:
                os.remove(tmp_pdf)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# TEXT STATE PROCESSOR FOR ALL TOOLS
# ---------------------------------------------------------------------------
async def process_state_text(text: str, msg, user, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("state")

    # Default to AI Chat if no specific state is set
    if not state or state == "WAIT_AI_CHAT":
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        wait_m = await msg.reply_text("⏳ <b>AI আপনার প্রশ্নের উত্তর তৈরি করছে, অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        history: List[Dict[str, str]] = context.user_data.setdefault("chat_history", [])
        history.append({"role": "user", "content": text})
        if len(history) > 16:
            history[:] = history[-16:]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a polite, smart, and professional Bangla AI assistant on Telegram. "
                    "Always reply naturally in clear, well-structured Bangla with relevant emojis unless the user asks for another language. "
                    "Avoid ugly raw markdown symbols like ** or ###; instead use clean bullet points (• or 🔹) and clear spacing."
                ),
            }
        ] + history

        reply = await asyncio.to_thread(call_groq_chat, messages)
        history.append({"role": "assistant", "content": reply})
        if len(history) > 16:
            history[:] = history[-16:]
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🤖 <b>AI চ্যাট রিপ্লাই</b>\n{DIVIDER}\n{html.escape(clean_ai_text(reply))}",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_TTS_TEXT":
        if len(text) > 2500:
            await msg.reply_text("⚠️ টেক্সট সর্বোচ্চ ২,৫০০ অক্ষরের (2.5K) মধ্যে হতে হবে। অনুগ্রহ করে একটু ছোট করে পাঠান।")
            return
        voice = context.user_data.get("tts_voice", "bn-BD-NabanitaNeural")
        v_label = VOICE_CHARACTER_LABELS.get(voice, voice)
        status_msg = await msg.reply_text(
            f"🎙️ <b>স্টুডিও ভয়েস তৈরি করা হচ্ছে ({v_label})...</b>\n⏳ <i>অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...</i>",
            parse_mode=ParseMode.HTML,
        )
        audio_path = await generate_tts_voice(text, voice)
        try:
            add_points(user.id, 1)
            with open(audio_path, "rb") as f:
                await msg.reply_voice(
                    voice=f,
                    caption=f"🎙️ <b>ভয়েস তৈরি সম্পন্ন!</b>\n🔊 কণ্ঠ: <b>{v_label}</b>",
                    parse_mode=ParseMode.HTML,
                )
            await status_msg.delete()
        finally:
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
        return

    if state == "WAIT_STT_VOICE":
        await msg.reply_text("⚠️ অনুগ্রহ করে টেক্সট না পাঠিয়ে একটি ভয়েস মেসেজ (Voice Message) রেকর্ড করে পাঠান।")
        return

    if state == "WAIT_AI_IMG":
        status_msg = await msg.reply_text(
            "🎨 <b>আপনার প্রম্পট উন্নত করে Ultra-HD AI ছবি তৈরি করা হচ্ছে...</b>\n"
            "⏳ <i>অনুগ্রহ করে ৫–১২ সেকেন্ড অপেক্ষা করুন...</i>",
            parse_mode=ParseMode.HTML,
        )
        enhanced_prompt = await asyncio.to_thread(enhance_image_prompt_with_groq, text)
        try:
            img_bytes = await asyncio.to_thread(generate_ai_image_multi_engine, text, enhanced_prompt)
        except Exception as e:
            logger.error(f"All AI image engines failed: {e}")
            await status_msg.edit_text("দুঃখিত, এই মুহূর্তে ছবিটি তৈরি করা যায়নি। অনুগ্রহ করে একটু পর আবার চেষ্টা করুন 🙏")
            return

        add_points(user.id, 1)
        await msg.reply_photo(
            photo=io.BytesIO(img_bytes),
            caption=(
                f"🖼️ <b>Ultra-HD AI ছবি (100% Watermark-Free)</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>✨ <b>আপনার বিষয়:</b> {html.escape(text)}\n"
                f"🎯 <b>AI Prompt:</b> <i>{html.escape(enhanced_prompt[:220])}</i></blockquote>"
            ),
            parse_mode=ParseMode.HTML,
        )
        await status_msg.delete()
        return

    if state == "WAIT_VID_DL":
        if is_premium_mode_on() and not is_user_premium(user.id):
            await msg.reply_text("💎 ভিডিও ডাউনলোড বর্তমানে শুধুমাত্র প্রিমিয়াম ইউজারদের জন্য চালু আছে।")
            return
        url = extract_first_url(text)
        if not url:
            await msg.reply_text("⚠️ মেসেজে কোনো বৈধ লিংক (http/https) পাওয়া যায়নি। সঠিক লিংক পাঠান।")
            return

        status_msg = await msg.reply_text(
            "📥 <b>আপনার ভিডিওটি খুঁজে ডাউনলোড করা হচ্ছে...</b>\n"
            "⏳ <i>অনুগ্রহ করে ১০–২০ সেকেন্ড অপেক্ষা করুন...</i>",
            parse_mode=ParseMode.HTML,
        )
        vid_path: Optional[str] = None
        try:
            vid_path, title = await asyncio.to_thread(download_video_from_url, url)
            add_points(user.id, 1)
            with open(vid_path, "rb") as f:
                await msg.reply_video(
                    video=f,
                    caption=(
                        f"🎬 <b>ভিডিও ডাউনলোড সম্পন্ন!</b>\n"
                        f"{DIVIDER}\n"
                        f"<blockquote>📌 {html.escape(title[:200])}</blockquote>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            await status_msg.delete()
        except ValueError as ve:
            if str(ve) == "FILE_TOO_LARGE":
                await status_msg.edit_text("⚠️ দুঃখিত, ভিডিওটির সাইজ ৫০ মেগাবাইটের (50MB) বেশি হওয়ায় টেলিগ্রামে পাঠানো সম্ভব নয়।")
            else:
                await status_msg.edit_text(ERROR_MSG_BN)
        except Exception as e:
            logger.error(f"Video download failed: {e}", exc_info=True)
            await status_msg.edit_text(
                "⚠️ <b>ভিডিওটি ডাউনলোড করা যায়নি।</b>\n"
                "<blockquote>অনুগ্রহ করে পাবলিক <b>TikTok অথবা Instagram</b> ভিডিও লিংক পাঠান এবং নিশ্চিত করুন ভিডিওটি প্রাইভেট নয় 🙏</blockquote>",
                parse_mode=ParseMode.HTML,
            )
        finally:
            if vid_path and os.path.exists(vid_path):
                try:
                    parent_dir = os.path.dirname(vid_path)
                    os.remove(vid_path)
                    if parent_dir.startswith(tempfile.gettempdir()):
                        os.rmdir(parent_dir)
                except OSError:
                    pass
        return

    if state == "WAIT_TRANSLATE_TEXT":
        direction = context.user_data.get("trans_dir", "bn2en")
        target_lang = "English" if direction == "bn2en" else "Bangla (Bengali)"
        wait_m = await msg.reply_text("⏳ <b>অনুবাদ করা হচ্ছে, অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": f"You are a professional translator. Translate the user's text accurately into {target_lang}. Output ONLY the translation.",
                },
                {"role": "user", "content": text},
            ],
            0.3,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🌐 <b>অনুবাদ ফলাফল ({'বাংলা → English' if direction == 'bn2en' else 'English → বাংলা'})</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_PRAYER":
        wait_m = await msg.reply_text("⏳ <b>নামাজ ও সাহরি-ইফতারের সময়সূচী লোড হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(fetch_prayer_times_for_location, text)
        add_points(user.id, 1)
        await wait_m.edit_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_CRYPTO":
        wait_m = await msg.reply_text("⏳ <b>ক্রিপ্টো কয়েনের লাইভ দাম যাচাই করা হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(fetch_crypto_prices, text)
        add_points(user.id, 1)
        await wait_m.edit_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_CAPTION":
        wait_m = await msg.reply_text("⏳ <b>আপনার জন্য ৫টি সুন্দর বাংলা ক্যাপশন তৈরি হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "তুমি একজন সাধারণ মানুষের মনের ভাষা বোঝা সোশ্যাল মিডিয়া রাইটার। "
                        "ইউজারের দেওয়া বিষয়ের ওপর ফেসবুক ও ইনস্টাগ্রামে নিজের ছবির সাথে দেওয়ার মতো একদম সহজ, স্বাভাবিক ও আবেগী ভাষায় ৫টি ছোট বাংলা ক্যাপশন (প্রতিটি ১ থেকে ২ লাইন) লিখে দাও।\n\n"
                        "কঠোর নিয়মাবলী (অবশ্যই মানতে হবে):\n"
                        "১. কোনো কঠিন বা সাহিত্যিক কবিতার ভাষা ব্যবহার করবে না—সাধারণ মানুষ প্রতিদিন যেভাবে মনের অনুভূতি প্রকাশ করে, ঠিক তেমন সহজ ও সুন্দর বাংলায় লিখবে।\n"
                        "২. ক্যাপশনের উপরে বা পাশে 'Aesthetic', 'Attitude', 'Emotional', 'Short One-Liner', 'Stylish Banglish'—এই ধরনের কোনো ইংরেজি বা বাংলা লেবেল/হেডিং একদমই লিখবে না! শুধু ১., ২., ৩., ৪., ৫. নম্বর দিয়ে সরাসরি ক্যাপশন লিখবে।\n"
                        "৩. প্রতিটি ক্যাপশনের পরের লাইনে ৪–৫টি ট্রেন্ডিং ইন্‌গলিশ হ্যাশট্যাগ (যেমন: #Mood #LifeVibes #Memories #Smile #Blessed) দেবে। কখনো বাংলা হ্যাশট্যাগ দেবে না।\n"
                        "৪. কোনো ডাবল স্টার (**) বা মার্কডাউন চিহ্ন দেবে না।"
                    ),
                },
                {"role": "user", "content": f"বিষয়: {text}"},
            ],
            0.7,
            1000,
        )
        add_points(user.id, 1)
        cleaned_out = clean_ai_text(out)
        # Strip any accidental category label prefixes if the LLM still tried to add them
        cleaned_out = re.sub(
            r"(?im)^([১-৫1-5][.)]\s*)(?:aesthetic|attitude|emotional|romantic|short|stylish|poetic|one-liner|banglish|ক্যাপশন)[^:\n]*:\s*",
            r"\1",
            cleaned_out,
        )
        await wait_m.edit_text(
            f"✍️ <b>আপনার ছবির জন্য ৫টি সুন্দর বাংলা ক্যাপশন</b>\n"
            f"{DIVIDER}\n"
            f"📌 <b>বিষয়:</b> {html.escape(text)}\n\n"
            f"<blockquote>{html.escape(cleaned_out)}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_STORY":
        wait_m = await msg.reply_text("⏳ <b>আপনার জন্য সুন্দর গল্প / কবিতা লেখা হচ্ছে, অনুগ্রহ করে একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": "You are a talented Bengali writer and poet. Write a heartwarming, vivid short story or poem in literary Bangla based on the user's topic with a fitting title. Do not use raw markdown asterisks (**).",
                },
                {"role": "user", "content": f"বিষয়: {text}"},
            ],
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"📖 <b>গল্প / কবিতা ({html.escape(text)})</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_WEATHER":
        wait_m = await msg.reply_text("⏳ <b>লাইভ আবহাওয়ার তথ্য লোড হচ্ছে, অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(fetch_weather_info, text)
        add_points(user.id, 1)
        await wait_m.edit_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_CURRENCY":
        wait_m = await msg.reply_text("⏳ <b>মুদ্রার লাইভ বিনিময় হার (Exchange Rate) হিসাব করা হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(convert_currency_input, text)
        add_points(user.id, 1)
        await wait_m.edit_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_SHORTURL":
        url = extract_first_url(text)
        if not url:
            await msg.reply_text("⚠️ সঠিক একটি লিংক (http:// বা https:// সহ) পাঠান।")
            return
        wait_m = await msg.reply_text("⏳ <b>লিংকটি ছোট (Short URL) করা হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        api_url = f"https://is.gd/create.php?format=simple&url={urllib.parse.quote(url)}"
        resp = await asyncio.to_thread(requests.get, api_url, timeout=15)
        resp.raise_for_status()
        short_link = resp.text.strip()
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🔗 <b>আপনার ছোট করা লিংক প্রস্তুত!</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote><code>{html.escape(short_link)}</code></blockquote>\n"
            f"🌐 {html.escape(short_link)}",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_DICT":
        word = text.split()[0].strip()
        wait_m = await msg.reply_text("⏳ <b>ডিকশনারি থেকে শব্দের অর্থ ও উদাহরণ খোঁজা হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        dict_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        r = await asyncio.to_thread(requests.get, dict_url, timeout=10)
        if r.status_code == 200:
            data = r.json()[0]
            phonetic = data.get("phonetic", "")
            meanings = data.get("meanings", [])
            defs_out = []
            for m_item in meanings[:3]:
                pos = m_item.get("partOfSpeech", "")
                for d_item in m_item.get("definitions", [])[:2]:
                    d_txt = d_item.get("definition", "")
                    ex_txt = d_item.get("example", "")
                    line = f"• (<i>{html.escape(pos)}</i>) {html.escape(d_txt)}"
                    if ex_txt:
                        line += f"\n  💬 <i>{html.escape(ex_txt)}</i>"
                    defs_out.append(line)
            bn_meaning = ""
            try:
                bn_meaning = await asyncio.to_thread(
                    call_groq_chat,
                    [
                        {"role": "system", "content": "Give the concise Bangla meaning of the English word in 1-2 lines without asterisks."},
                        {"role": "user", "content": word},
                    ],
                    0.3,
                    200,
                )
            except Exception:
                pass
            add_points(user.id, 1)
            await wait_m.edit_text(
                f"📚 <b>ডিকশনারি ফলাফল: {html.escape(word)}</b> {html.escape(phonetic)}\n"
                f"{DIVIDER}\n"
                f"🇧🇩 <b>বাংলা অর্থ:</b>\n<blockquote>{html.escape(clean_ai_text(bn_meaning))}</blockquote>\n\n"
                f"📖 <b>English Definitions:</b>\n<blockquote>" + "\n".join(defs_out) + "</blockquote>",
                parse_mode=ParseMode.HTML,
            )
        else:
            explanation = await asyncio.to_thread(
                call_groq_chat,
                [
                    {
                        "role": "system",
                        "content": "Explain the given word with its Bangla meaning, part of speech, and 2 example sentences. Do not use raw markdown asterisks (**).",
                    },
                    {"role": "user", "content": word},
                ],
            )
            add_points(user.id, 1)
            await wait_m.edit_text(
                f"📚 <b>শব্দের বিস্তারিত ব্যাখ্যা ({html.escape(word)})</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>{html.escape(clean_ai_text(explanation))}</blockquote>",
                parse_mode=ParseMode.HTML,
            )
        return

    if state == "WAIT_BMI":
        out = calculate_bmi_response(text)
        add_points(user.id, 1)
        await msg.reply_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_QR":
        wait_m = await msg.reply_text("⏳ <b>আপনার প্রিমিয়াম স্টাইলিশ QR Card তৈরি হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        bio = await asyncio.to_thread(generate_premium_qr_card, text)
        add_points(user.id, 1)
        await msg.reply_photo(
            photo=bio,
            caption=(
                f"🔳 <b>প্রিমিয়াম স্মার্ট QR Code প্রস্তুত!</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>📌 <b>তথ্য / লিংক:</b> <code>{html.escape(text[:200])}</code></blockquote>"
            ),
            parse_mode=ParseMode.HTML,
        )
        await wait_m.delete()
        return

    if state == "WAIT_AGE":
        out = calculate_age_response(text)
        add_points(user.id, 1)
        await msg.reply_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_UNIT":
        out = convert_unit_input(text)
        add_points(user.id, 1)
        await msg.reply_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_FANCY":
        out = generate_fancy_text(text)
        add_points(user.id, 1)
        await msg.reply_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_LOVE":
        parts = re.split(r"[,+&❤️]+|\band\b|\bআর\b|\bও\b", text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) < 2:
            words = text.split()
            if len(words) >= 2:
                parts = [words[0], " ".join(words[1:])]
            else:
                await msg.reply_text("⚠️ অনুগ্রহ করে দুইজনের নাম কমা (,) দিয়ে লিখুন।\nউদাহরণ: <code>Rahim, Karima</code>", parse_mode=ParseMode.HTML)
                return
        n1, n2 = parts[0].strip(), parts[1].strip()
        key = "::".join(sorted([n1.lower(), n2.lower()]))
        digest = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
        pct = 40 + (digest % 61)
        bars = "❤️" * (pct // 10) + "🤍" * (10 - (pct // 10))
        add_points(user.id, 1)
        await msg.reply_text(
            f"💘 <b>Love ক্যালকুলেটর ফলাফল</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>"
            f"👤 <b>{html.escape(n1)}</b>  ❤️  <b>{html.escape(n2)}</b>\n\n"
            f"📊 <b>ভালোবাসার হার:</b> {pct}%\n"
            f"{bars}"
            f"</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_LYRICS":
        status_msg = await msg.reply_text("⏳ <b>গানের লিরিক্স ও তথ্য খোঁজা হচ্ছে, অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(fetch_song_lyrics_and_info, text)
        add_points(user.id, 1)
        await status_msg.edit_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_REMINDER":
        parsed = parse_reminder_input(text)
        if not parsed:
            await msg.reply_text(
                "⚠️ <b>সঠিক ফরম্যাটে রিমাইন্ডার লিখুন!</b>\n\n"
                "<blockquote>"
                "• <code>10 মিনিট পরে পানি খাবো</code>\n"
                "• <code>30 minute por ghumabo</code>\n"
                "• <code>1 ghonta pore call</code>"
                "</blockquote>",
                parse_mode=ParseMode.HTML,
            )
            return
        seconds, note = parsed
        if context.job_queue:
            context.job_queue.run_once(
                reminder_job_callback,
                when=seconds,
                data={"chat_id": msg.chat_id, "text": note},
                name=f"rem_{user.id}_{int(time.time())}",
            )
            add_points(user.id, 1)
            await msg.reply_text(
                f"✅ <b>রিমাইন্ডার সেট করা হয়েছে!</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>⏳ নির্ধারিত সময় পর আপনাকে মনে করিয়ে দেওয়া হবে:\n<b>{html.escape(note)}</b></blockquote>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await msg.reply_text("⚠️ জব কিউ (Job Queue) সক্রিয় নেই।")
        return

    # --- 10 HIGH-UTILITY STATES (WITH WAITING MESSAGES & CLEAN FORMATTING) ---
    if state == "WAIT_GRAMMAR":
        wait_m = await msg.reply_text("⏳ <b>আপনার বাক্যটির বানান ও Grammar পরীক্ষা করা হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "You are an expert English and Bangla grammar corrector. Format your response clearly in 3 parts without raw asterisks (**):\n"
                        "✅ সঠিক বাক্য (Corrected Sentence):\n"
                        "🔍 কী ভুল ছিল (What Was Fixed in Bangla):\n"
                        "✨ আরও সুন্দর ও প্রফেশনাল রূপ (Better Alternative):"
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.3,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"📝 <b>বানান ও Grammar সংশোধন ফলাফল</b>\n{DIVIDER}\n<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_EMAIL_CV":
        wait_m = await msg.reply_text("⏳ <b>আপনার প্রফেশনাল ইমেইল / আবেদনপত্র তৈরি হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "You are an expert corporate and academic writer. Write a complete, ready-to-send formal Email, Application (দরখাস্ত), or CV Cover Letter "
                        "based on the user's request with Subject line and proper salutation. Do not use raw markdown asterisks (**)."
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.4,
        )
        add_points(user.id, 1)
        clean_doc = clean_ai_text(out)
        await wait_m.edit_text(
            f"📧 <b>আপনার প্রফেশনাল ইমেইল / আবেদনপত্র</b>\n{DIVIDER}\n"
            f"<blockquote>{html.escape(clean_doc)}</blockquote>\n"
            f"📋 <i>নিচের বক্সে ট্যাপ করে পুরো লেখাটি কপি করুন:</i>\n"
            f"<code>{html.escape(clean_doc[:1500])}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_CODE_HELP":
        wait_m = await msg.reply_text("⏳ <b>আপনার কোড তৈরি করা হচ্ছে, অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "তুমি একজন দক্ষ প্রোগ্রামার ও সহজ ভাষার শিক্ষক। ইউজারের চাহিদা অনুযায়ী ১০০% নির্ভুল কোড একটি ```code``` ব্লকের ভেতরে লিখবে। "
                        "আর কোড ব্লকের নিচে একদম সহজ, স্বাভাবিক বাংলায় (যেমন সাধারণ মানুষ কথা বলে) বুঝিয়ে দেবে: "
                        "১) এই কোডটি কীভাবে কাজ করে, এবং ২) কোডটি কীভাবে রান বা ব্যবহার করতে হবে। "
                        "ব্যাখ্যার ভেতরে কঠিন ইংরেজি বাক্য বা জটিল ভাষা ব্যবহার করবে না এবং কোনো ** চিহ্ন দেবে না।"
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.25,
            1800,
        )
        add_points(user.id, 1)
        code_match = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\n(.*?)```", out, flags=re.DOTALL)
        if code_match:
            extracted_code = code_match.group(1).strip()
            explanation_part = (out[:code_match.start()] + "\n" + out[code_match.end():]).strip()
            explanation_part = clean_ai_text(explanation_part)
            formatted_msg = (
                f"💻 <b>প্রফেশনাল কোড জেনারেটর ও সমাধান</b>\n"
                f"{DIVIDER}\n"
                f"📋 <b>কোড (ট্যাপ করে কপি করুন):</b>\n"
                f"<pre><code>{html.escape(extracted_code[:2800])}</code></pre>"
            )
            if explanation_part:
                formatted_msg += f"\n\n💡 <b>সহজ বাংলায় ব্যাখ্যা:</b>\n<blockquote>{html.escape(explanation_part[:1100])}</blockquote>"
        else:
            formatted_msg = (
                f"💻 <b>প্রফেশনাল কোড জেনারেটর ও সমাধান</b>\n"
                f"{DIVIDER}\n"
                f"<pre><code>{html.escape(clean_ai_text(out)[:3500])}</code></pre>"
            )
        await wait_m.edit_text(formatted_msg, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_BIO_GEN":
        wait_m = await msg.reply_text("⏳ <b>আপনার জন্য সুন্দর প্রোফাইল বায়ো তৈরি হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "ইউজারের দেওয়া নাম বা তথ্যের ওপর ভিত্তি করে ফেসবুক, ইনস্টাগ্রাম ও টেলিগ্রাম প্রোফাইলের জন্য ৫টি সুন্দর, মার্জিত ও পরিষ্কার বায়ো (Bio) লিখে দাও (বাংলা এবং সহজ ইংরেজিতে)।\n"
                        "কঠোর নিয়ম:\n"
                        "- কোনো অদ্ভুত বা জটিল ফন্ট ব্যবহার করবে না যা পড়তে কষ্ট হয়। একদম পরিষ্কার ও স্বাভাবিক অক্ষরে সুন্দর ইমোজি দিয়ে সাজিয়ে লিখবে।\n"
                        "- শুধু ১. থেকে ৫. নম্বর দিয়ে পরপর ৫টি বায়ো দেবে, কোনো ইংরেজি ক্যাটাগরি হেডিং বা ** চিহ্ন দেবে না।"
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.7,
            1000,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🪪 <b>আপনার প্রোফাইল বায়ো কালেকশন</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(clean_ai_text(out))}</blockquote>\n"
            f"💡 <i>আপনার পছন্দের যেকোনো বায়ো কপি করে প্রোফাইলে ব্যবহার করুন!</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_DREAM_ISLAM":
        wait_m = await msg.reply_text("⏳ <b>কুরআন ও হাদিসের আলোকে আপনার প্রশ্নের উত্তর প্রস্তুত করা হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "You are a knowledgeable, respectful Islamic scholar assistant. Answer Islamic questions or dream interpretations "
                        "in polite, clear Bangla based on the Quran, Sahih Hadith, and authentic classical scholars (such as Ibn Sirin for dreams). "
                        "Structure with clear bullet points and references. Do not use raw markdown asterisks (**)."
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.4,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🌙 <b>ইসলামিক ও স্বপ্ন বিষয়ক সমাধান</b>\n{DIVIDER}\n<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_MATH_SOLVE":
        wait_m = await msg.reply_text("⏳ <b>আপনার অংক / বিজ্ঞানের প্রশ্নটি ধাপে ধাপে সমাধান করা হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "You are an expert Bangladeshi Mathematics, Physics, and Chemistry professor. "
                        "Solve the user's math or science problem with 100% accuracy in clear Bangla using this exact structure:\n"
                        "📌 প্রদত্ত তথ্য (Given):\n"
                        "📐 প্রয়োজনীয় সূত্র (Formula):\n"
                        "✍️ ধাপে ধাপে সমাধান (Step-by-Step Solution):\n"
                        "✅ চূড়ান্ত উত্তর (Final Answer):\n\n"
                        "CRITICAL RULES:\n"
                        "- Double-check all arithmetic and algebraic steps before outputting.\n"
                        "- NEVER use LaTeX code like \\frac or $$; instead use clean Unicode math symbols (×, ÷, √, ², ³, π, θ, ⇒, ∴).\n"
                        "- Do NOT use raw markdown asterisks (**)."
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.2,
            1500,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🧮 <b>অংক ও বিজ্ঞান নিখুঁত সমাধান</b>\n{DIVIDER}\n<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_BLOOD_INFO":
        wait_m = await msg.reply_text("⏳ <b>রক্তদান ও স্বাস্থ্য বিষয়ক তথ্য প্রস্তুত করা হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": "You are a helpful medical guide. Answer blood group, blood donation eligibility, hemoglobin, and health questions clearly in simple Bangla list format without tables or raw asterisks (**).",
                },
                {"role": "user", "content": text},
            ],
            0.4,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🩸 <b>রক্তের গ্রুপ ও ডোনার গাইড উত্তর</b>\n{DIVIDER}\n<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_DIET_PLAN":
        wait_m = await msg.reply_text("⏳ <b>আপনার জন্য ঘরোয়া দেশি খাবারের ডায়েট চার্ট তৈরি হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "তুমি একজন অভিজ্ঞ বাংলাদেশী পুষ্টিবিদ। ইউজারের বয়স, ওজন ও লক্ষ্য অনুযায়ী সহজ তালিকা আকারে (Bullet points) প্রতিদিনের ডায়েট চার্ট তৈরি করে দাও:\n"
                        "🌅 সকালের নাস্তা:\n"
                        "🍎 দুপুরের আগের হালকা খাবার:\n"
                        "🍛 দুপুরের খাবার:\n"
                        "☕ বিকেলের নাস্তা:\n"
                        "🌙 রাতের খাবার:\n"
                        "💧 জরুরি পরামর্শ:\n\n"
                        "কঠোর নিয়মাবলী (অবশ্যই মানতে হবে):\n"
                        "১. ভুলেও কোনো টেবিল (Table বা | চিহ্ন) ব্যবহার করবে না—সাধারণ তালিকা আকারে পরিষ্কারভাবে লিখবে।\n"
                        "২. কুইনোয়া (Quinoa), ওটস (Oats), টুনা ফিশ (Tuna), স্যামন, অ্যাভোকাডো, ব্রকলি, চিয়া সিড, অলিভ অয়েল—এই ধরনের কোনো বিদেশি খাবার একদমই লিখবে না!\n"
                        "৩. শুধুমাত্র বাংলাদেশের সাধারণ মানুষের প্রতিদিনের সহজলভ্য দেশি খাবার দেবে: যেমন ভাত, লাল আটার রুটি, ডাল, ডিম, দেশি মাছ (রুই, তেলাপিয়া, শিং), মুরগির মাংস, সবজি ভাজি বা ঝোল, শাক, মুড়ি, ছোলা, শসা, পেয়ারা, কলা, পেঁপে, দুধ, টক দই ও লেবু পানি।\n"
                        "৪. কোনো ** চিহ্ন ব্যবহার করবে না।"
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.45,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🥗 <b>আপনার দেশি খাবারের ডায়েট ও স্বাস্থ্য চার্ট</b>\n{DIVIDER}\n<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_BIZ_IDEA":
        wait_m = await msg.reply_text("⏳ <b>আপনার জন্য সহজ বিজনেস আইডিয়া ও গাইড তৈরি হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "তুমি একজন অভিজ্ঞ বাংলাদেশী ব্যবসা পরামর্শদাতা। ইউজারের বাজেট বা পছন্দ অনুযায়ী একদম সহজ ও সাধারণ বাংলা লেখায় (তালিকা আকারে) ব্যবসার আইডিয়া বা পেজের সুন্দর নাম সাজিয়ে দাও।\n"
                        "কঠোর নিয়ম:\n"
                        "১. কখনোই কোনো টেবিল (Table বা | চিহ্ন) ব্যবহার করবে না! সাধারণ প্যারাগ্রাফ ও পয়েন্ট আকারে সহজ বাংলায় লিখবে।\n"
                        "২. কীভাবে শুরু করবে, কত টাকা পুঁজি লাগবে, কোথা থেকে পণ্য আনবে এবং কীভাবে বিক্রি বা মার্কেটিং করবে তা সাধারণ মানুষের ভাষায় বুঝিয়ে দেবে।\n"
                        "৩. কোনো ** চিহ্ন ব্যবহার করবে না।"
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.6,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"💼 <b>বিজনেস আইডিয়া ও গাইড</b>\n{DIVIDER}\n<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_MOVIE_REC":
        wait_m = await msg.reply_text("⏳ <b>আপনার পছন্দের সেরা মুভি ও সিরিজের তালিকা তৈরি হচ্ছে, একটু অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "You are a film critic. Recommend the top 5 best movies or web series matching the user's taste. "
                        "For each item include: 🎬 নাম ও সাল, ⭐ IMDb/রেটিং, 🎭 ধরন (Genre), এবং 📖 সংক্ষিপ্ত কাহিনী (Spoiler-free summary in Bangla). "
                        "Do not use raw asterisks (**)."
                    ),
                },
                {"role": "user", "content": text},
            ],
            0.6,
        )
        add_points(user.id, 1)
        await wait_m.edit_text(
            f"🎬 <b>সেরা মুভি ও সিরিজ রিকমেন্ডেশন</b>\n{DIVIDER}\n<blockquote>{html.escape(clean_ai_text(out))}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_ORDER_DETAILS":
        prod = context.user_data.get("buy_product")
        if not prod:
            context.user_data["state"] = None
            await msg.reply_text("⚠️ অর্ডার সেশন শেষ হয়ে গেছে। আবার শপ থেকে চেষ্টা করুন।")
            return

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders (user_id, product_id, product_name, customer_details) VALUES (?, ?, ?, ?)",
                (user.id, prod["id"], prod["name"], text),
            )
            order_id = cur.lastrowid
            conn.commit()

        context.user_data["state"] = None
        context.user_data.pop("buy_product", None)

        order_summary = (
            f"🛒 <b>নতুন অর্ডার এসেছে! (Order #{order_id})</b>\n"
            f"{DIVIDER}\n"
            f"📦 <b>পণ্য:</b> {html.escape(prod['name'])} ({html.escape(prod['price'])})\n"
            f"👤 <b>ক্রেতা:</b> {html.escape(user.full_name or 'User')} (ID: <code>{user.id}</code>)\n\n"
            f"<blockquote>📝 <b>ক্রেতার বিবরণ (নাম, মোবাইল, ঠিকানা):</b>\n{html.escape(text)}</blockquote>"
        )
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=aid, text=order_summary, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.warning(f"Could not notify admin {aid} of order #{order_id}: {e}")

        await msg.reply_text(
            f"✅ <b>অর্ডার সফলভাবে গৃহীত হয়েছে! (Order #{order_id})</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>খুব শীঘ্রই আমাদের প্রতিনিধি আপনার সাথে যোগাযোগ করবেন। আমাদের সাথে থাকার জন্য ধন্যবাদ 🙏</blockquote>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_markup(user.id),
        )
        return

    if state == "WAIT_CONTACT_ADMIN":
        context.user_data["state"] = None
        if not ADMIN_IDS:
            await msg.reply_text("⚠️ বর্তমানে কোনো অ্যাডমিন আইডি কনফিগার করা নেই।")
            return
        sent_any = False
        for aid in ADMIN_IDS:
            try:
                fwd = await context.bot.send_message(
                    chat_id=aid,
                    text=(
                        f"📩 <b>ইউজারের মেসেজ (Contact Admin)</b>\n"
                        f"{DIVIDER}\n"
                        f"👤 <b>নাম:</b> {html.escape(user.full_name or 'User')}\n"
                        f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
                        f"<blockquote>💬 <b>মেসেজ:</b>\n{html.escape(text)}</blockquote>\n\n"
                        f"↩️ <i>উত্তর দিতে এই মেসেজটিতে Reply দিন।</i>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
                with get_db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO forwarded_messages (admin_msg_id, admin_id, user_id) VALUES (?, ?, ?)",
                        (fwd.message_id, aid, user.id),
                    )
                    conn.commit()
                sent_any = True
            except Exception as e:
                logger.warning(f"Failed forwarding contact msg to admin {aid}: {e}")

        if sent_any:
            await msg.reply_text(
                f"✅ <b>মেসেজ পাঠানো হয়েছে!</b>\n{DIVIDER}\n"
                "<blockquote>আপনার মেসেজটি অ্যাডমিনের কাছে পৌঁছেছে। অ্যাডমিন উত্তর দিলে এখানেই দেখতে পাবেন 🙏</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_markup(user.id),
            )
        else:
            await msg.reply_text(ERROR_MSG_BN, reply_markup=get_main_menu_markup(user.id))
        return


# ---------------------------------------------------------------------------
# GLOBAL ERROR HANDLER
# ---------------------------------------------------------------------------
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):
        logger.warning("Telegram 409 Conflict detected (overlapping deploy or another instance polling). Waiting for other instance to stop...")
        return
    logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(ERROR_MSG_BN)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------
def main() -> None:
    init_db()

    # Start Flask server in a daemon thread so Render free tier health check passes
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask keep-alive server started on port {PORT}.")

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is missing! Waiting on Flask thread...")
        flask_thread.join()
        return

    # Python 3.14+ explicit event loop setup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application: Application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CommandHandler("admin", cmd_admin))
    application.add_handler(CommandHandler("ban", cmd_ban))
    application.add_handler(CommandHandler("unban", cmd_unban))
    application.add_handler(CommandHandler("maintenance", cmd_maintenance))
    application.add_handler(CommandHandler("setchannel", cmd_setchannel))
    application.add_handler(CommandHandler("channel", cmd_channel))
    application.add_handler(CommandHandler("premium", cmd_premium))
    application.add_handler(CommandHandler("addproduct", cmd_addproduct))
    application.add_handler(CommandHandler("delproduct", cmd_delproduct))

    # CallbackQuery Handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Message Handler (Text, Voice, Audio, Photo, Document)
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.VOICE | filters.AUDIO | filters.PHOTO | filters.Document.ALL)
            & ~filters.COMMAND,
            handle_message,
        )
    )

    # Error Handler
    application.add_error_handler(global_error_handler)

    logger.info("Starting Telegram Bot with long polling...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()