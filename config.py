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
