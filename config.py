# -*- coding: utf-8 -*-
"""
Ferma — 2 ta Hikvision Face ID terminal (KIRISH + CHIQISH) event qabul
qiluvchi standalone FastAPI loyiha. Sozlamalar muhit o'zgaruvchilaridan
(.env) o'qiladi — production maxfiy ma'lumotlarni koddan tashqarida
saqlash uchun.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHATS = [c.strip() for c in (os.getenv("TG_CHATS") or "").split(",") if c.strip()]

# --- Kameralardan ruxsat etilgan IP'lar (bo'sh = tekshiruv o'chiq) ---
# Kamera CG-NAT/dinamik IP orqali kelishi mumkin — shunday bo'lsa bo'sh qoldiring.
ALLOWED_IPS = [ip.strip() for ip in (os.getenv("ALLOWED_IPS") or "").split(",") if ip.strip()]

# --- Fayl/DB yo'llari ---
SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "static/snapshots")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db")

# --- Spam-oldi sozlamalari ---
# Bitta gate (kirish/chiqish) uchun "Noma'lum odam" xabari shu oraliqda
# faqat bitta marta yuboriladi — kamera bir kishi oldida davomiy turganda
# yoki tarmoq xatosi tufayli qayta-qayta urinib push qilganda spam bo'lmasin.
UNMATCHED_ALERT_DEBOUNCE_SEC = int(os.getenv("UNMATCHED_ALERT_DEBOUNCE_SEC", "15"))


def _ids(name: str) -> list[int]:
    return [int(x) for x in (os.getenv(name) or "").replace(" ", "").split(",") if x.lstrip("-").isdigit()]


# --- Davomat hisoboti (Mini App + Web) ---
TIMEZONE = "Asia/Tashkent"
# Sessiya cookie/token imzosi uchun. Bo'sh bo'lsa auth ishlamaydi.
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") != "0"
# Faqat lokal test uchun: Telegram'siz kirish (/api/davomat/auth/dev). Serverda 0 bo'lishi shart.
DEV_LOGIN = os.getenv("DEV_LOGIN", "0") == "1"
# Yagona super admin — faqat shu yerdan belgilanadi (ishga tushishda bazaga yoziladi).
SUPERADMIN_TELEGRAM_ID = (_ids("SUPERADMIN_TELEGRAM_ID") or [None])[0]
# Birinchi adminlar (keyin super admin admin sahifasidan qo'shadi).
ADMIN_TELEGRAM_IDS = _ids("ADMIN_TELEGRAM_IDS")
# https://api.ravnaqfarm.uz — Mini App va Login Widget uchun HTTPS manzil.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")
# BotFather'da /newapp qilingan bo'lsa: https://t.me/<bot>/<app> (guruhdagi tugma uchun).
MINIAPP_LINK = os.getenv("MINIAPP_LINK", "")
CHECKIN_PHOTO_DIR = os.getenv("CHECKIN_PHOTO_DIR", "data/checkins")
