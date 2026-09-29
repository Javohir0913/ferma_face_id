# -*- coding: utf-8 -*-
"""
Autentifikatsiya: Telegram Mini App initData, Telegram Login Widget va
imzolangan sessiya tokeni. Frontenddan kelgan user_id'ga hech qachon
ishonilmaydi — faqat bot token bilan tekshirilgan ma'lumotga.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from config import SESSION_SECRET, SESSION_TTL_HOURS, TG_TOKEN
from database import app_users, database, employees

COOKIE_NAME = "dv_session"
INIT_DATA_MAX_AGE = 24 * 3600


class AuthError(Exception):
    pass


def verify_webapp_init_data(init_data: str, bot_token: str, max_age: int = INIT_DATA_MAX_AGE, now: Optional[float] = None) -> dict:
    """https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app"""
    if not init_data or not bot_token:
        raise AuthError("initData yo'q")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        raise AuthError("hash yo'q")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise AuthError("imzo noto'g'ri")
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if (now or time.time()) - auth_date > max_age:
        raise AuthError("initData eskirgan")
    user = json.loads(pairs.get("user", "{}") or "{}")
    if not user.get("id"):
        raise AuthError("user yo'q")
    return user


def verify_login_widget(data: dict, bot_token: str, max_age: int = INIT_DATA_MAX_AGE, now: Optional[float] = None) -> dict:
    """https://core.telegram.org/widgets/login#checking-authorization"""
    data = {k: str(v) for k, v in data.items() if v is not None}
    received = data.pop("hash", None)
    if not received or not bot_token:
        raise AuthError("hash yo'q")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise AuthError("imzo noto'g'ri")
    if (now or time.time()) - int(data.get("auth_date", "0") or 0) > max_age:
        raise AuthError("login eskirgan")
    return {"id": int(data["id"]), "first_name": data.get("first_name"), "username": data.get("username")}


PBKDF2_ITER = 240_000


def hash_password(password: str) -> str:
    import secrets
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, hexdk = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(it))
        return hmac.compare_digest(dk.hex(), hexdk)
    except ValueError:
        return False


def generate_password(length: int = 10) -> str:
    import secrets
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(uid: int, name: str = "", ttl_hours: int = SESSION_TTL_HOURS,
               only_path: Optional[str] = None, ttl_seconds: Optional[int] = None) -> str:
    if not SESSION_SECRET:
        raise AuthError("SESSION_SECRET .env da yo'q")
    payload = {"uid": uid, "name": name, "exp": int(time.time()) + (ttl_seconds or ttl_hours * 3600)}
    if only_path:
        payload["p"] = only_path
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> dict:
    if not SESSION_SECRET or not token or "." not in token:
        raise AuthError("token yo'q")
    body, sig = token.rsplit(".", 1)
    expected = _b64(hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise AuthError("token imzosi noto'g'ri")
    data = json.loads(_unb64(body))
    if data.get("exp", 0) < time.time():
        raise AuthError("token muddati o'tgan")
    return data


async def current_actor(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    dl = request.query_params.get("dl")
    try:
        if dl and not token:
            # Telegram downloadFile uchun: faqat bitta yo'lga, 2 daqiqa amal qiladigan token.
            data = read_token(dl)
            if data.get("p") != request.url.path:
                raise AuthError("havola boshqa fayl uchun")
        else:
            data = read_token(token or "")
            if data.get("p"):
                raise AuthError("yuklab olish tokeni sessiya emas")
    except AuthError:
        raise HTTPException(401, "Avtorizatsiya kerak")
    uid = int(data["uid"])
    # Ruxsat har so'rovda bazadan olinadi — olib tashlangan foydalanuvchi darhol chetlanadi.
    u = await database.fetch_one(select(app_users).where(app_users.c.telegram_user_id == uid))
    e = await database.fetch_one(select(employees).where(employees.c.telegram_user_id == uid))
    return {
        "uid": uid,
        "name": data.get("name") or "",
        "level": u["level"] if u else None,
        "is_responsible": bool(u["is_responsible"]) if u else False,
        "employee_no": e["employee_no"] if e and e["active"] else None,
        "employee_name": e["full_name"] if e else None,
    }


SUPERADMIN = "superadmin"
ADMIN_LEVELS = ("admin", SUPERADMIN)
# Boshqalarning davomatini faqat adminlar ko'radi; qolganlar faqat o'zinikini (/my).
VIEW_LEVELS = ADMIN_LEVELS


async def require_viewer(actor: dict = Depends(current_actor)) -> dict:
    if actor["level"] not in VIEW_LEVELS:
        raise HTTPException(403, "Boshqalarning davomatini faqat admin ko'radi")
    return actor


async def require_admin(actor: dict = Depends(current_actor)) -> dict:
    if actor["level"] not in ADMIN_LEVELS:
        raise HTTPException(403, "Faqat admin uchun")
    return actor


async def require_superadmin(actor: dict = Depends(current_actor)) -> dict:
    if actor["level"] != SUPERADMIN:
        raise HTTPException(403, "Faqat super admin uchun")
    return actor


async def require_employee(actor: dict = Depends(current_actor)) -> dict:
    if not actor["employee_no"]:
        raise HTTPException(403, "Telegram hisobingiz xodimga biriktirilmagan")
    return actor


def bot_token() -> str:
    return TG_TOKEN or ""
