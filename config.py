# -*- coding: utf-8 -*-
"""
Ферма — standalone-проект на FastAPI, принимающий события от 2 терминалов
Hikvision Face ID (ВХОД + ВЫХОД). Настройки читаются из переменных окружения
(.env) — чтобы секреты production хранились вне кода.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHATS = [c.strip() for c in (os.getenv("TG_CHATS") or "").split(",") if c.strip()]

# --- Разрешённые IP камер (пусто = проверка отключена) ---
# Камера может приходить через CG-NAT/динамический IP — в этом случае оставьте пустым.
ALLOWED_IPS = [ip.strip() for ip in (os.getenv("ALLOWED_IPS") or "").split(",") if ip.strip()]

# --- Пути к файлам/БД ---
SNAPSHOT_DIR = os.getenv("SNAPSHOT_DIR", "static/snapshots")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db")

# --- Защита от спама ---
# Сообщение «Неизвестный человек» для одного gate (вход/выход) отправляется
# не чаще одного раза за этот интервал — чтобы не было спама, когда человек
# долго стоит перед камерой или камера повторно отправляет push из-за сбоя сети.
UNMATCHED_ALERT_DEBOUNCE_SEC = int(os.getenv("UNMATCHED_ALERT_DEBOUNCE_SEC", "15"))


def _ids(name: str) -> list[int]:
    return [int(x) for x in (os.getenv(name) or "").replace(" ", "").split(",") if x.lstrip("-").isdigit()]


# --- Отчёт посещаемости (Mini App + Web) ---
TIMEZONE = "Asia/Tashkent"
# Для подписи cookie/токена сессии. Если пусто — авторизация не работает.
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1") != "0"
# Только для локального теста: вход без Telegram (/api/davomat/auth/dev). На сервере обязательно 0.
DEV_LOGIN = os.getenv("DEV_LOGIN", "0") == "1"
# Единственный суперадмин — задаётся только здесь (записывается в базу при запуске).
SUPERADMIN_TELEGRAM_ID = (_ids("SUPERADMIN_TELEGRAM_ID") or [None])[0]
# Первые админы (дальше суперадмин добавляет их на странице администрирования).
ADMIN_TELEGRAM_IDS = _ids("ADMIN_TELEGRAM_IDS")
# https://api.ravnaqfarm.uz — HTTPS-адрес для Mini App и Login Widget.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lstrip("@")
# Если в BotFather сделан /newapp: https://t.me/<bot>/<app> (для кнопки в группе).
MINIAPP_LINK = os.getenv("MINIAPP_LINK", "")
CHECKIN_PHOTO_DIR = os.getenv("CHECKIN_PHOTO_DIR", "data/checkins")
