#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete Multi-Tool Bangla Telegram Bot (bot.py)
Tech stack:
- python-telegram-bot v21+ (with job-queue, long polling, Python 3.10–3.14+ compatible)
- Flask background keep-alive server on PORT (default 10000)
- SQLite database (bigbot.db)
- Groq API (dynamic model discovery & fallback, Whisper STT)
- 30+ Tools, Points/Levels, Referral, Daily Bonus, Spin, Quiz, Shop, Force Join, Admin Panel
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
from PIL import Image
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
# BANGLA DIGIT CONVERSION HELPER
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


# ---------------------------------------------------------------------------
# PERSISTENT MENU KEYBOARD (EXACT ORDER & LABELS, 2 PER ROW)
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
BTN_MENU = "🏠 মেনু"
BTN_MAKE_PDF_DONE = "✅ PDF বানান"

MAIN_MENU_LAYOUT = [
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
    [KeyboardButton(BTN_SHOP), KeyboardButton(BTN_CONTACT)],
    [KeyboardButton(BTN_PROFILE), KeyboardButton(BTN_LEADERBOARD)],
    [KeyboardButton(BTN_DAILY), KeyboardButton(BTN_SPIN)],
    [KeyboardButton(BTN_REFER), KeyboardButton(BTN_ABOUT)],
    [KeyboardButton(BTN_HELP), KeyboardButton(BTN_DEV)],
    [KeyboardButton(BTN_MENU)],
]

MAIN_MENU_MARKUP = ReplyKeyboardMarkup(MAIN_MENU_LAYOUT, resize_keyboard=True)

PDF_COLLECT_MARKUP = ReplyKeyboardMarkup(
    [[KeyboardButton(BTN_MAKE_PDF_DONE)], [KeyboardButton(BTN_MENU)]],
    resize_keyboard=True,
)

ALL_MENU_BUTTONS = {btn.text for row in MAIN_MENU_LAYOUT for btn in row} | {BTN_MAKE_PDF_DONE}


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
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET points = points + ?, week_points = week_points + ? WHERE user_id = ?",
            (pts, pts, user_id),
        )
        conn.commit()


def get_total_users() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
        return int(row["cnt"]) if row else 0


def get_total_orders() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM orders").fetchone()
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

    # 1. If GROQ_MODEL env is set and available, use it
    if GROQ_MODEL_ENV and (not available_set or GROQ_MODEL_ENV in available_set):
        _cached_groq_selected = GROQ_MODEL_ENV
        return _cached_groq_selected

    # 2. Pick in preference order
    for candidate in GROQ_PREFERRED_MODELS:
        if candidate in available_set:
            _cached_groq_selected = candidate
            return _cached_groq_selected

    # 3. Fallback to any non-whisper/non-guard chat model if none of preferred found
    for m in available:
        lower_m = m.lower()
        if "whisper" not in lower_m and "guard" not in lower_m and "tts" not in lower_m:
            _cached_groq_selected = m
            return _cached_groq_selected

    # 4. Ultimate fallback if model list call itself failed
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

        # If json_mode is unsupported by a specific model, retry without response_format
        if resp.status_code == 400 and json_mode and attempt == 0:
            json_mode = False
            continue

        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content

    raise RuntimeError("Groq chat completion failed after retry.")


def call_groq_whisper(file_path: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

    last_err: Optional[Exception] = None
    for model in GROQ_WHISPER_MODELS:
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "audio/ogg")}
                data = {"model": model}
                resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
            if resp.status_code == 404:
                logger.warning(f"Whisper model {model} returned 404, skipping to next...")
                continue
            resp.raise_for_status()
            result = resp.json()
            text = result.get("text", "").strip()
            if text:
                return text
        except Exception as e:
            last_err = e
            logger.warning(f"Whisper transcription error with {model}: {e}")

    if last_err:
        raise last_err
    raise RuntimeError("All Whisper models failed.")


# ---------------------------------------------------------------------------
# WATERMARK-FREE IMAGE CLEANING (100% LOGO REMOVAL GUARANTEE)
# ---------------------------------------------------------------------------
def remove_bottom_watermark_and_polish(img_bytes: bytes) -> bytes:
    """
    Guarantees 100% watermark-free AI images.
    Pollinations sometimes burns a small logo strip in the bottom-right / bottom 6%
    even when ?nologo=true is passed. We request a slightly taller image (or standard 1024)
    and cleanly crop out the bottom watermark zone, then resize to a crisp 1024x1024 JPEG.
    """
    with Image.open(io.BytesIO(img_bytes)) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        # Crop bottom 6.5% where any watermark/logo badge sits, and center-crop width slightly to keep aspect ratio
        crop_bottom = int(h * 0.935)
        margin_x = int(w * 0.0325)
        cropped = rgb.crop((margin_x, 0, w - margin_x, crop_bottom))
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        final_im = cropped.resize((1024, 1024), resample_filter)
        out_bio = io.BytesIO()
        final_im.save(out_bio, format="JPEG", quality=95, optimize=True)
        return out_bio.getvalue()


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
]

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
    "৫. <b>📥 ভিডিও ডাউনলোড</b> — TikTok (HD), YouTube, FB, Insta ভিডিও ডাউনলোড\n"
    "৬. <b>🌐 অনুবাদ</b> — বাংলা ↔ English নিখুঁত অনুবাদ\n"
    "৭. <b>✍️ Caption বানান</b> — ইমোজি ও হ্যাশট্যাগসহ ৫টি ভাইরাল বাংলা ক্যাপশন\n"
    "৮. <b>📖 গল্প / কবিতা</b> — যেকোনো টপিকে বাংলা গল্প বা কবিতা রচনা"
    "</blockquote>\n\n"
    "📂 <b>ডকুমেন্ট ও ইউটিলিটি টুলস:</b>\n"
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
    "৩০. <b>🧠 কুইজ খেলুন</b> — ৫টি বাংলা সাধারণ জ্ঞানের কুইজ খেলে পয়েন্ট অর্জন"
    "</blockquote>\n\n"
    "🎁 <b>শপ, প্রোফাইল ও অন্যান্য:</b>\n"
    "<blockquote>"
    "৩১. <b>🛍️ শপ</b> — বট স্টোর থেকে পণ্য দেখা ও অর্ডার করা\n"
    "৩২. <b>📩 Contact Admin</b> — সরাসরি অ্যাডমিনের সাথে মেসেজে কথা বলা\n"
    "৩৩. <b>👤 প্রোফাইল</b> — নিজের পয়েন্ট, লেভেল, র‍্যাংক ও রেফারেল লিংক\n"
    "৩৪. <b>🏆 লিডারবোর্ড</b> — সর্বকালের সেরা ১০ ও সাপ্তাহিক সেরা ৫ জনের তালিকা\n"
    "৩৫. <b>🎁 ডেইলি বোনাস</b> — প্রতিদিন ফ্রি +৫ পয়েন্ট বোনাস\n"
    "৩৬. <b>🎰 স্পিন</b> — প্রতিদিন লাকি স্পিনে ১–৫০ পয়েন্ট জয়ের সুযোগ\n"
    "৩৭. <b>👥 রেফার করুন</b> — বন্ধু আমন্ত্রণ জানিয়ে প্রতি রেফারে +১০ পয়েন্ট\n"
    "৩৮. <b>ℹ️ About</b> — বটের সকল বাটনের বিস্তারিত তালিকা\n"
    "৩৯. <b>❓ Help</b> — বট ব্যবহারের গাইডলাইন ও নিয়মাবলী\n"
    "৪০. <b>👨💻 Developer</b> — বট নির্মাতার পরিচিতি\n"
    "৪১. <b>🏠 মেনু</b> — যেকোনো টুল থেকে মূল মেনুতে ফিরে আসা"
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
    "• <code>/myid</code> — আপনার টেলিগ্রাম আইডি দেখুন\n\n"
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
    """
    Converts '05:12' or '05:12 (BST)' into '05:12 AM'
    """
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
    """
    Geocode with Open-Meteo geocoding API, then forecast API.
    Retry 3 times with delays on 429/error, then fallback to wttr.in/<city>?format=j1.
    """
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

    # Fallback: wttr.in
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
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    styles = {
        "𝐁𝐨𝐥𝐝": "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗",
        "𝐼𝑡𝑎𝑙𝑖𝑐": "𝑖𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍0123456789",
        "𝑩𝒐𝒍𝒅 𝑰𝒕𝒂𝒍𝒊𝒄": "𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁0123456789",
        "𝒮𝒸𝓇𝒾𝓅𝓉": "𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐJKℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵0123456789",
        "𝕭𝖔𝖑𝖉 𝕾𝖈𝖗𝖎𝖕𝖙": "𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅0123456789",
        "𝔻𝕠𝕦𝕓𝕝𝕖": "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
        "𝙼𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎": "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿",
        "Ⓒⓘⓡⓒⓛⓔⓓ": "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ0①②③④⑤⑥⑦⑧⑨",
    }

    out = [f"✨ <b>আপনার স্টাইলিশ ফ্যান্সি টেক্সট</b>\n{DIVIDER}"]
    lines = []
    for label, target in styles.items():
        if len(target) == len(normal):
            table = str.maketrans(normal, target)
            converted = text.translate(table)
        else:
            converted = text
        lines.append(f"◈ {label}: <code>{html.escape(converted)}</code>")

    spaced = " ".join(list(text))
    lines.append(f"◈ S p a c e d: <code>{html.escape(spaced)}</code>")
    out.append("<blockquote>" + "\n".join(lines) + "</blockquote>")
    out.append("👆 <i>যেকোনো স্টাইলের ওপর ট্যাপ করলেই কপি হয়ে যাবে!</i>")
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
    """
    Parses inputs like:
    - "10 মিনিট পরে পানি খাবো"
    - "30 minute por ghumabo"
    - "1 ghonta pore call"
    Returns (seconds, reminder_text) or None.
    """
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


def fetch_crypto_prices() -> str:
    coins = [
        ("bitcoin", "BTC", "BTCUSDT", "Bitcoin (BTC)"),
        ("ethereum", "ETH", "ETHUSDT", "Ethereum (ETH)"),
        ("binancecoin", "BNB", "BNBUSDT", "BNB (BNB)"),
        ("dogecoin", "DOGE", "DOGEUSDT", "Dogecoin (DOGE)"),
        ("ripple", "XRP", "XRPUSDT", "XRP (XRP)"),
        ("solana", "SOL", "SOLUSDT", "Solana (SOL)"),
    ]

    usd_to_bdt = 120.0
    try:
        r_fx = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        if r_fx.status_code == 200:
            usd_to_bdt = float(r_fx.json().get("rates", {}).get("BDT", 120.0))
    except Exception:
        pass

    prices_usd: Dict[str, float] = {}

    try:
        ids_str = ",".join(c[0] for c in coins)
        cg_url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids_str}&vs_currencies=usd"
        cg_resp = requests.get(cg_url, timeout=10)
        if cg_resp.status_code == 200:
            cg_data = cg_resp.json()
            for cid, sym, _, _ in coins:
                if cid in cg_data and "usd" in cg_data[cid]:
                    prices_usd[sym] = float(cg_data[cid]["usd"])
    except Exception as e:
        logger.warning(f"CoinGecko failed, falling back to Binance: {e}")

    for _, sym, binance_sym, _ in coins:
        if sym not in prices_usd:
            try:
                b_url = f"https://api.binance.com/api/v3/ticker/price?symbol={binance_sym}"
                b_resp = requests.get(b_url, timeout=8)
                if b_resp.status_code == 200:
                    prices_usd[sym] = float(b_resp.json()["price"])
            except Exception as e:
                logger.warning(f"Binance fallback failed for {binance_sym}: {e}")

    if not prices_usd:
        raise RuntimeError("Could not fetch crypto prices from CoinGecko or Binance.")

    body = []
    for _, sym, _, label in coins:
        if sym in prices_usd:
            usd = prices_usd[sym]
            bdt = usd * usd_to_bdt
            if usd >= 1:
                body.append(f"🪙 <b>{label}</b>\n   💵 <code>${usd:,.2f}</code>  |  🇧🇩 <code>৳{bdt:,.0f}</code>")
            else:
                body.append(f"🪙 <b>{label}</b>\n   💵 <code>${usd:.4f}</code>  |  🇧🇩 <code>৳{bdt:,.2f}</code>")

    return (
        f"📈 <b>ক্রিপ্টোকারেন্সির লাইভ বাজারমূল্য</b>\n"
        f"{DIVIDER}\n"
        f"<blockquote>" + "\n\n".join(body) + "</blockquote>"
    )


def fetch_google_news_bn() -> str:
    url = "https://news.google.com/rss?hl=bn&gl=BD&ceid=BD:bn"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = root.findall(".//item")[:5]
    if not items:
        return "📰 বর্তমানে কোনো খবর পাওয়া যায়নি।"

    lines = [f"📰 <b>আজকের শীর্ষ ৫টি তাজা খবর (Google News)</b>\n{DIVIDER}"]
    for idx, item in enumerate(items, 1):
        title = item.findtext("title") or "শিরোনাম নেই"
        link = item.findtext("link") or ""
        lines.append(f"<blockquote><b>{en_to_bn_digits(str(idx))}.</b> <a href=\"{html.escape(link)}\">{html.escape(title)}</a></blockquote>")
    return "\n".join(lines)


async def generate_tts_voice(text: str, voice: str) -> str:
    """
    Generates an OGG/MP3 audio file using edge-tts (retries 3 times),
    falls back to gTTS if edge-tts fails 3 times, and converts with ffmpeg if needed.
    Returns path to generated audio file.
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
        lang = "bn" if voice.startswith("bn") else "en"
        tts = gTTS(text=text, lang=lang)
        tts.save(tmp_mp3)

    tmp_ogg = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg").name
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", tmp_mp3, "-c:a", "libopus", "-b:a", "48k", tmp_ogg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
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


def download_video_from_url(url: str) -> Tuple[str, str]:
    """
    Downloads video under 50MB.
    For tiktok.com links, tries tikwm API first (hdplay or play).
    Falls back to yt-dlp limited to <46MB mp4.
    Returns (file_path, title).
    """
    tmp_dir = tempfile.mkdtemp(prefix="vid_")

    if "tiktok.com" in url.lower():
        try:
            api_url = f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}&hd=1"
            resp = requests.get(api_url, timeout=20)
            if resp.status_code == 200:
                j = resp.json()
                data = j.get("data") or {}
                play_url = data.get("hdplay") or data.get("play")
                title = data.get("title") or "TikTok Video"
                if play_url:
                    if play_url.startswith("/"):
                        play_url = "https://www.tikwm.com" + play_url
                    v_resp = requests.get(play_url, stream=True, timeout=60)
                    v_resp.raise_for_status()
                    out_path = os.path.join(tmp_dir, "tiktok.mp4")
                    total_bytes = 0
                    with open(out_path, "wb") as f:
                        for chunk in v_resp.iter_content(chunk_size=65536):
                            if chunk:
                                total_bytes += len(chunk)
                                if total_bytes > 50 * 1024 * 1024:
                                    raise ValueError("FILE_TOO_LARGE")
                                f.write(chunk)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                        return out_path, title
        except ValueError as ve:
            if str(ve) == "FILE_TOO_LARGE":
                raise
        except Exception as e:
            logger.warning(f"tikwm API failed, falling back to yt-dlp: {e}")

    out_tmpl = os.path.join(tmp_dir, "video.%(ext)s")
    ydl_opts = {
        "format": "best[filesize<46M][ext=mp4]/best[filesize_approx<46M][ext=mp4]/best[ext=mp4]/best",
        "outtmpl": out_tmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 50 * 1024 * 1024,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "Downloaded Video") if info else "Downloaded Video"
        downloaded_path = ydl.prepare_filename(info)

    if not os.path.exists(downloaded_path):
        files = [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)]
        if not files:
            raise RuntimeError("Video download failed.")
        downloaded_path = files[0]

    if os.path.getsize(downloaded_path) > 50 * 1024 * 1024:
        raise ValueError("FILE_TOO_LARGE")

    return downloaded_path, title


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


async def send_quiz_question(message, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            reply_markup=MAIN_MENU_MARKUP,
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
        f"🛠️ <b>মোট সার্ভিস:</b> ৩০+ প্রিমিয়াম টুলস (সম্পূর্ণ ফ্রি)"
        f"</blockquote>\n\n"
        f"👇 <b>নিচের মেনু থেকে আপনার পছন্দের সেবাটি বেছে নিন:</b>"
    )
    await update.effective_message.reply_text(
        welcome_msg,
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_MENU_MARKUP,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message or is_user_banned(user.id):
        return
    await update.effective_message.reply_text(
        HELP_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_MENU_MARKUP,
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
# ADMIN PANEL & ADMIN TEXT COMMANDS
# ---------------------------------------------------------------------------
def build_admin_panel_markup() -> InlineKeyboardMarkup:
    maint_status = "চালু (ON) 🟢" if is_maintenance_on() else "বন্ধ (OFF) 🔴"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Stats", callback_data="admin:stats"),
                InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast"),
            ],
            [
                InlineKeyboardButton("📢 চ্যানেল (Force Join)", callback_data="admin:channel"),
                InlineKeyboardButton(f"🔧 Maintenance: {maint_status}", callback_data="admin:maint_toggle"),
            ],
        ]
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message:
        return
    if not is_admin(user.id):
        return

    await update.effective_message.reply_text(
        f"🛠️ <b>অ্যাডমিন কন্ট্রোল প্যানেল (Admin Panel)</b>\n"
        f"{DIVIDER}\n"
        "<blockquote>"
        "• <code>/ban &lt;id&gt;</code> | <code>/unban &lt;id&gt;</code>\n"
        "• <code>/maintenance on|off</code>\n"
        "• <code>/setchannel @ChannelName</code> | <code>/setchannel off</code>\n"
        "• <code>/channel</code>\n"
        "• <code>/premium &lt;id&gt; on|off</code>\n"
        "• <code>/addproduct নাম|দাম|বিবরণ</code>\n"
        "• <code>/delproduct &lt;id&gt;</code>"
        "</blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=build_admin_panel_markup(),
    )


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
                await query.message.reply_text("✅ মূল মেনু থেকে আপনার পছন্দের টুল বেছে নিন:", reply_markup=MAIN_MENU_MARKUP)
                return

            joined = await check_force_join(update, context)
            if joined:
                await query.answer("✅ জয়েন নিশ্চিত হয়েছে! ধন্যবাদ।", show_alert=True)
                await query.message.reply_text("✅ অভিনন্দন! এখন আপনি বটের সকল টুল ব্যবহার করতে পারবেন।", reply_markup=MAIN_MENU_MARKUP)
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
                ch = get_force_join_channel() or "OFF"
                maint = "ON" if is_maintenance_on() else "OFF"
                await query.answer()
                await query.message.reply_text(
                    f"📊 <b>বট পরিসংখ্যান (Live Stats)</b>\n"
                    f"{DIVIDER}\n"
                    f"<blockquote>"
                    f"👥 <b>মোট ইউজার:</b> {u_cnt} জন\n"
                    f"🛍️ <b>মোট অর্ডার:</b> {o_cnt} টি\n"
                    f"📢 <b>Force Join:</b> {html.escape(ch)}\n"
                    f"🔧 <b>Maintenance:</b> {maint}"
                    f"</blockquote>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "broadcast":
                context.user_data["state"] = "ADMIN_BROADCAST"
                await query.answer()
                await query.message.reply_text(
                    f"📢 <b>ব্রডকাস্ট মোড চালু হয়েছে</b>\n"
                    f"{DIVIDER}\n"
                    "এখন যে মেসেজটি পাঠাবেন সেটি সকল ব্যবহারকারীর কাছে চলে যাবে (বাতিল করতে 🏠 মেনু চাপুন):",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "channel":
                ch = get_force_join_channel()
                status_txt = f"বর্তমান চ্যানেল: <b>{html.escape(ch)}</b>" if ch else "বর্তমানে কোনো চ্যানেল সেট করা নেই (OFF)।"
                await query.answer()
                await query.message.reply_text(
                    f"📢 <b>চ্যানেল (Force Join) সেটিংস</b>\n"
                    f"{DIVIDER}\n"
                    f"<blockquote>{status_txt}</blockquote>\n\n"
                    f"🔹 চ্যানেল সেট করতে কমান্ড দিন:\n<code>/setchannel @ChannelName</code>\n"
                    f"🔹 বন্ধ করতে কমান্ড দিন:\n<code>/setchannel off</code>",
                    parse_mode=ParseMode.HTML,
                )
            elif action == "maint_toggle":
                new_val = "off" if is_maintenance_on() else "on"
                set_setting("maintenance", new_val)
                await query.answer(f"Maintenance এখন {new_val.upper()}")
                await query.edit_message_reply_markup(reply_markup=build_admin_panel_markup())
            return

        # Check maintenance & force join for normal users
        if is_maintenance_on() and not is_admin(user.id):
            await query.answer("🔧 বট বর্তমানে রক্ষণাবেক্ষণের জন্য বন্ধ আছে।", show_alert=True)
            return

        if not await check_force_join(update, context):
            await query.answer()
            return

        # 3. Voice Selection for TTS
        if data.startswith("tts_voice:"):
            voice = data.split(":", 1)[1]
            context.user_data["tts_voice"] = voice
            context.user_data["state"] = "WAIT_TTS_TEXT"
            await query.answer("ভয়েস নির্বাচন করা হয়েছে!")
            await query.message.reply_text(
                f"🎙️ <b>নির্বাচিত ভয়েস:</b> <code>{voice}</code>\n"
                f"{DIVIDER}\n"
                "✍️ এখন আপনার টেক্সট পাঠান (সর্বোচ্চ ৮০০ অক্ষর):",
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
            city_en, city_bn = data.split(":", 1)[1].split("|")
            await query.answer("নামাজের সময়সূচী লোড হচ্ছে...")
            today_str = datetime.date.today().strftime("%d-%m-%Y")
            url = f"https://api.aladhan.com/v1/timingsByCity/{today_str}?city={urllib.parse.quote(city_en)}&country=Bangladesh&method=1"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            timings = resp.json()["data"]["timings"]
            msg = (
                f"🕌 <b>আজকের নামাজের সময়সূচী ({city_bn})</b>\n"
                f"{DIVIDER}\n"
                f"📅 <b>তারিখ:</b> {today_str}\n\n"
                f"<blockquote>"
                f"🌅 <b>ফজর (Fajr):</b> {format_12h(timings['Fajr'])}\n"
                f"☀️ <b>সূর্যোদয় (Sunrise):</b> {format_12h(timings['Sunrise'])}\n"
                f"🌞 <b>যোহর (Dhuhr):</b> {format_12h(timings['Dhuhr'])}\n"
                f"🌤️ <b>আসর (Asr):</b> {format_12h(timings['Asr'])}\n"
                f"🌇 <b>মাগরিব (Maghrib):</b> {format_12h(timings['Maghrib'])}\n"
                f"🌙 <b>ইশা (Isha):</b> {format_12h(timings['Isha'])}"
                f"</blockquote>"
            )
            add_points(user.id, 1)
            await query.message.reply_text(msg, parse_mode=ParseMode.HTML)
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
            await send_quiz_question(query.message, context)
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

    # 3. Handle "🏠 মেনু" reset button at any time
    if text == BTN_MENU:
        context.user_data["state"] = None
        context.user_data.pop("pdf_images", None)
        context.user_data.pop("quiz", None)
        await msg.reply_text(
            f"🏠 <b>মূল মেনুতে ফিরে এসেছেন</b>\n{DIVIDER}\n👇 নিচের বাটন থেকে আপনার পছন্দের যেকোনো অপশন বেছে নিন:",
            parse_mode=ParseMode.HTML,
            reply_markup=MAIN_MENU_MARKUP,
        )
        return

    # 4. Handle Admin Broadcast State
    state = context.user_data.get("state")
    if state == "ADMIN_BROADCAST" and is_admin(user.id):
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

    # 5. Check Maintenance Mode for non-admins
    if is_maintenance_on() and not is_admin(user.id):
        await msg.reply_text(
            "🔧 বট বর্তমানে রক্ষণাবেক্ষণ (Maintenance) কাজের জন্য সাময়িকভাবে বন্ধ আছে। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন 🙏"
        )
        return

    # 6. Check Force Join before using tools
    if not await check_force_join(update, context):
        return

    # 7. Check if user pressed "✅ PDF বানান"
    if text == BTN_MAKE_PDF_DONE:
        await finalize_images_to_pdf(msg, user.id, context)
        return

    # 8. If user tapped any main menu button, switch mode & prompt
    if text in ALL_MENU_BUTTONS:
        await route_menu_button(text, msg, user, context)
        return

    # 9. Handle incoming Voice, Photo, Document, or Text according to current state
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
        await msg.reply_text(ERROR_MSG_BN, reply_markup=MAIN_MENU_MARKUP)


# ---------------------------------------------------------------------------
# MENU BUTTON ROUTER (STYLISH PROMPTS)
# ---------------------------------------------------------------------------
async def route_menu_button(
    btn: str, msg, user, context: ContextTypes.DEFAULT_TYPE
) -> None:
    context.user_data["state"] = None

    try:
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
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("👩 বাংলা (Nabanita - Default)", callback_data="tts_voice:bn-BD-NabanitaNeural"),
                        InlineKeyboardButton("👨 বাংলা (Pradeep)", callback_data="tts_voice:bn-BD-PradeepNeural"),
                    ],
                    [
                        InlineKeyboardButton("👩 English (Aria)", callback_data="tts_voice:en-US-AriaNeural"),
                    ],
                ]
            )
            await msg.reply_text(
                f"🎙️ <b>টেক্সট থেকে ভয়েস (Text-to-Speech)</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>🔊 <b>বর্তমান ভয়েস:</b> <code>{default_voice}</code>\n"
                f"নিচের বাটন থেকে কণ্ঠ পরিবর্তন করতে পারেন অথবা সরাসরি আপনার লেখাটি পাঠান (সর্বোচ্চ ৮০০ অক্ষর)।</blockquote>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )

        elif btn == BTN_STT:
            context.user_data["state"] = "WAIT_STT_VOICE"
            await msg.reply_text(
                f"🎤 <b>ভয়েস থেকে টেক্সট (Voice → Text)</b>\n"
                f"{DIVIDER}\n"
                "<blockquote>অনুগ্রহ করে একটি ভয়েস মেসেজ (Voice Message) রেকর্ড করে পাঠান, আমি তা সাথে সাথে লেখায় রূপান্তর করে দেব!</blockquote>",
                parse_mode=ParseMode.HTML,
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
                "<blockquote>TikTok (ওয়াটারমার্ক ছাড়া HD), YouTube, Facebook বা Instagram ভিডিওর লিংক (অথবা শেয়ার টেক্সট) পাঠান:</blockquote>",
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
                ]
            )
            await msg.reply_text(
                f"🕐 <b>আজকের নামাজের সময়সূচী</b>\n"
                f"{DIVIDER}\n"
                "👇 আপনার বিভাগ/শহর নির্বাচন করুন:",
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
            en_joke_str = ""
            try:
                r = requests.get("https://official-joke-api.appspot.com/random_joke", timeout=6)
                if r.status_code == 200:
                    jd = r.json()
                    en_joke_str = (
                        f"\n\n🌐 <b>English Joke:</b>\n"
                        f"<blockquote>{html.escape(jd.get('setup', ''))}\n— <i>{html.escape(jd.get('punchline', ''))}</i></blockquote>"
                    )
            except Exception:
                pass
            await msg.reply_text(
                f"😂 <b>আজকের মজার জোকস</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>{bn_joke}</blockquote>{en_joke_str}",
                parse_mode=ParseMode.HTML,
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
            await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
            news_text = await asyncio.to_thread(fetch_google_news_bn)
            add_points(user.id, 1)
            await msg.reply_text(news_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        elif btn == BTN_CRYPTO:
            await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
            crypto_text = await asyncio.to_thread(fetch_crypto_prices)
            add_points(user.id, 1)
            await msg.reply_text(crypto_text, parse_mode=ParseMode.HTML)

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
            await send_quiz_question(msg, context)

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
            bot_uname = context.bot.username or "Bot"
            ref_link = f"https://t.me/{bot_uname}?start=ref_{user.id}"
            await msg.reply_text(
                f"👤 <b>ইউজার প্রোফাইল ড্যাশবোর্ড</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>"
                f"🏷️ <b>নাম:</b> {html.escape(user.full_name or 'User')}\n"
                f"🆔 <b>আইডি:</b> <code>{user.id}</code>\n"
                f"⭐ <b>মোট পয়েন্ট:</b> {pts}\n"
                f"🏅 <b>লেভেল:</b> {lvl}\n"
                f"🏆 <b>গ্লোবাল র‍্যাংক:</b> #{rank}\n"
                f"👥 <b>মোট রেফারেল:</b> {refs} জন"
                f"</blockquote>\n\n"
                f"🔗 <b>আপনার রেফারেল লিংক:</b>\n<code>{ref_link}</code>",
                parse_mode=ParseMode.HTML,
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
        await msg.reply_text(ERROR_MSG_BN, reply_markup=MAIN_MENU_MARKUP)


# ---------------------------------------------------------------------------
# MEDIA & STATE INPUT PROCESSORS
# ---------------------------------------------------------------------------
async def process_voice_message(msg, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
    voice_obj = msg.voice or msg.audio
    tg_file = await context.bot.get_file(voice_obj.file_id)
    tmp_ogg = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg").name
    try:
        await tg_file.download_to_drive(custom_path=tmp_ogg)
        text_out = await asyncio.to_thread(call_groq_whisper, tmp_ogg)
        add_points(user_id, 1)
        await msg.reply_text(
            f"🎤 <b>ভয়েস থেকে রূপান্তরিত টেক্সট</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(text_out)}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
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
            await msg.reply_text("⚠️ ছবি প্রসেস করা যায়নি। আবার চেষ্টা করুন।", reply_markup=MAIN_MENU_MARKUP)
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
                    f"📄 <b> আপনার PDF প্রস্তুত!</b>\n"
                    f"{DIVIDER}\n"
                    f"<blockquote>✅ মোট <b>{len(pil_images)}টি</b> ছবি দিয়ে সুন্দরভাবে PDF তৈরি করা হয়েছে।</blockquote>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=MAIN_MENU_MARKUP,
            )
    except Exception as e:
        logger.error(f"PDF creation failed: {e}", exc_info=True)
        await msg.reply_text(ERROR_MSG_BN, reply_markup=MAIN_MENU_MARKUP)
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
            f"<blockquote>{html.escape(summary)}</blockquote>",
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
        await msg.reply_text(
            f"🤖 <b>AI চ্যাট রিপ্লাই</b>\n{DIVIDER}\n{html.escape(reply)}",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_TTS_TEXT":
        if len(text) > 800:
            await msg.reply_text("⚠️ টেক্সট সর্বোচ্চ ৮০০ অক্ষরের মধ্যে হতে হবে। অনুগ্রহ করে ছোট করে পাঠান।")
            return
        voice = context.user_data.get("tts_voice", "bn-BD-NabanitaNeural")
        status_msg = await msg.reply_text("🎙️ ভয়েস তৈরি করা হচ্ছে, একটু অপেক্ষা করুন...")
        audio_path = await generate_tts_voice(text, voice)
        try:
            add_points(user.id, 1)
            with open(audio_path, "rb") as f:
                await msg.reply_voice(
                    voice=f,
                    caption=f"🎙️ <b>ভয়েস তৈরি সম্পন্ন!</b> (Voice: <code>{voice}</code>)",
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
        await msg.reply_text("⚠️ অনুগ্রহ করে টেক্সট না পাঠিয়ে একটি ভয়েস মেসেজ (Voice Message) পাঠান।")
        return

    if state == "WAIT_AI_IMG":
        status_msg = await msg.reply_text("🎨 <b>আপনার HD AI ছবি তৈরি হচ্ছে, অনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
        encoded_prompt = urllib.parse.quote(text)
        # Request with nologo=true&nofeed=true&enhance=true, then pass through remove_bottom_watermark_and_polish()
        # so even if Pollinations burns a bottom logo, it is 100% cropped out and upscaled cleanly to 1024x1024!
        url1 = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&nofeed=true&enhance=true"
        url2 = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed=42"

        img_bytes: Optional[bytes] = None
        for target_url in (url1, url2):
            try:
                r = await asyncio.to_thread(
                    requests.get,
                    target_url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=45,
                )
                if r.status_code == 200 and r.content and len(r.content) > 1000:
                    img_bytes = await asyncio.to_thread(remove_bottom_watermark_and_polish, r.content)
                    break
            except Exception as e:
                logger.warning(f"Pollinations download attempt failed ({target_url}): {e}")

        if not img_bytes:
            await status_msg.edit_text("দুঃখিত, এই মুহূর্তে ছবিটি তৈরি করা যায়নি। অনুগ্রহ করে একটু পর আবার চেষ্টা করুন 🙏")
            return

        add_points(user.id, 1)
        await msg.reply_photo(
            photo=io.BytesIO(img_bytes),
            caption=(
                f"🖼️ <b>AI জেনারেটেড HD ছবি (Watermark-Free)</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>✨ <b>Prompt:</b> {html.escape(text)}</blockquote>"
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

        status_msg = await msg.reply_text("📥 <b>ভিডিও ডাউনলোড হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...</b>", parse_mode=ParseMode.HTML)
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
            await status_msg.edit_text("⚠️ ভিডিওটি ডাউনলোড করা যায়নি। লিংকটি সঠিক ও পাবলিক কি না যাচাই করুন 🙏")
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
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
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
        await msg.reply_text(
            f"🌐 <b>অনুবাদ ফলাফল ({'বাংলা → English' if direction == 'bn2en' else 'English → বাংলা'})</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(out)}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_CAPTION":
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": "You are a creative social media expert. Generate 5 short, catchy Bangla social media captions with fitting emojis and trending hashtags. Number them ১ to ৫ clearly without raw markdown asterisks (**).",
                },
                {"role": "user", "content": f"টপিক: {text}"},
            ],
        )
        add_points(user.id, 1)
        await msg.reply_text(
            f"✍️ <b>আপনার আকর্ষণীয় সোশ্যাল মিডিয়া ক্যাপশন</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(out)}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_STORY":
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": "You are a talented Bengali writer and poet. Write a heartwarming short story or poem in Bangla based on the user's topic. Do not use raw markdown asterisks (**).",
                },
                {"role": "user", "content": f"বিষয়: {text}"},
            ],
        )
        add_points(user.id, 1)
        await msg.reply_text(
            f"📖 <b>গল্প / কবিতা ({html.escape(text)})</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(out)}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_WEATHER":
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        out = await asyncio.to_thread(fetch_weather_info, text)
        add_points(user.id, 1)
        await msg.reply_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_CURRENCY":
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        out = await asyncio.to_thread(convert_currency_input, text)
        add_points(user.id, 1)
        await msg.reply_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_SHORTURL":
        url = extract_first_url(text)
        if not url:
            await msg.reply_text("⚠️ সঠিক একটি লিংক (http:// বা https:// সহ) পাঠান।")
            return
        api_url = f"https://is.gd/create.php?format=simple&url={urllib.parse.quote(url)}"
        resp = await asyncio.to_thread(requests.get, api_url, timeout=15)
        resp.raise_for_status()
        short_link = resp.text.strip()
        add_points(user.id, 1)
        await msg.reply_text(
            f"🔗 <b>আপনার ছোট করা লিংক প্রস্তুত!</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote><code>{html.escape(short_link)}</code></blockquote>\n"
            f"🌐 {html.escape(short_link)}",
            parse_mode=ParseMode.HTML,
        )
        return

    if state == "WAIT_DICT":
        word = text.split()[0].strip()
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
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
            await msg.reply_text(
                f"📚 <b>ডিকশনারি ফলাফল: {html.escape(word)}</b> {html.escape(phonetic)}\n"
                f"{DIVIDER}\n"
                f"🇧🇩 <b>বাংলা অর্থ:</b>\n<blockquote>{html.escape(bn_meaning)}</blockquote>\n\n"
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
            await msg.reply_text(
                f"📚 <b>শব্দের বিস্তারিত ব্যাখ্যা ({html.escape(word)})</b>\n"
                f"{DIVIDER}\n"
                f"<blockquote>{html.escape(explanation)}</blockquote>",
                parse_mode=ParseMode.HTML,
            )
        return

    if state == "WAIT_BMI":
        out = calculate_bmi_response(text)
        add_points(user.id, 1)
        await msg.reply_text(out, parse_mode=ParseMode.HTML)
        return

    if state == "WAIT_QR":
        qr_img = qrcode.make(text)
        bio = io.BytesIO()
        qr_img.save(bio, format="PNG")
        bio.seek(0)
        add_points(user.id, 1)
        await msg.reply_photo(
            photo=bio,
            caption=f"🔳 <b>QR Code সফলভাবে তৈরি হয়েছে!</b>\n{DIVIDER}\n<blockquote><code>{html.escape(text[:150])}</code></blockquote>",
            parse_mode=ParseMode.HTML,
        )
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
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        out = await asyncio.to_thread(
            call_groq_chat,
            [
                {
                    "role": "system",
                    "content": (
                        "You are a music encyclopedia assistant. Provide song details (artist, album/movie, theme) "
                        "in Bangla without raw markdown asterisks (**). IMPORTANT: If the song is copyrighted, provide ONLY a short 2-4 line excerpt "
                        "and a detailed summary/meaning in Bangla rather than full copyrighted lyrics."
                    ),
                },
                {"role": "user", "content": f"গান: {text}"},
            ],
        )
        add_points(user.id, 1)
        await msg.reply_text(
            f"🎵 <b>গানের তথ্য ও লিরিক্স সংক্ষেপ</b>\n"
            f"{DIVIDER}\n"
            f"<blockquote>{html.escape(out)}</blockquote>",
            parse_mode=ParseMode.HTML,
        )
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
            reply_markup=MAIN_MENU_MARKUP,
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
                reply_markup=MAIN_MENU_MARKUP,
            )
        else:
            await msg.reply_text(ERROR_MSG_BN, reply_markup=MAIN_MENU_MARKUP)
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

    # Python 3.14+ removed implicit event loop creation in asyncio.get_event_loop().
    # Explicitly create and set an event loop on the main thread before building/running Application.
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