# -*- coding: utf-8 -*-
"""
Ferma davomat boti (alohida jarayon):  python -m davomat.bot

  * /start — biriktirilgan bo'lsa huquqiga mos tugmalar, aks holda so'rov yaratadi
    va belgilangan mas'ul odamga (settings.link_admin_id) xabar beradi.
  * Istisno xabarlari faqat mas'ullarga (shaxsiy chat): qorovul kelmadi, smena turi
    aniqlanmadi (tugmalar bilan), kechagi to'liq bo'lmagan yozuvlar.
  * Kunlik qisqa xulosa guruhga (TG_CHATS) + hisobot tugmasi.
Holat `notifications` jadvalida — restartdan keyin takror yuborilmaydi.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import datetime, time, timedelta
from typing import Optional

import httpx
from sqlalchemy import and_, select

import telegram
from config import MINIAPP_LINK, PUBLIC_BASE_URL, TG_CHATS, TG_TOKEN
from database import app_users, create_all, database, notifications, tg_link_requests
from davomat import service
from davomat.engine import SHIFT_GUARD_DAY, SHIFT_GUARD_NIGHT, SHIFT_UNKNOWN, ST_CLOSED, ST_INCOMPLETE, ST_OPEN

logger = logging.getLogger("davomat.bot")
TYPE_LABEL = {SHIFT_GUARD_DAY: "☀️ Kunduzgi", SHIFT_GUARD_NIGHT: "🌙 Tungi"}


def _hm(v: str) -> time:
    h, m = (int(x) for x in v.split(":")[:2])
    return time(h, m)


def _webapp_button(text: str, path: str) -> Optional[dict]:
    if not PUBLIC_BASE_URL:
        return None
    return {"text": text, "web_app": {"url": f"{PUBLIC_BASE_URL}/davomat/{path}"}}


async def responsible_ids() -> list[int]:
    rows = await database.fetch_all(select(app_users).where(app_users.c.is_responsible == 1))
    if not rows:
        rows = await database.fetch_all(select(app_users).where(app_users.c.level.in_(("admin", "superadmin"))))
    return [r["telegram_user_id"] for r in rows]


async def can_decide(uid: int) -> bool:
    r = await database.fetch_one(select(app_users).where(app_users.c.telegram_user_id == uid))
    return bool(r and (r["level"] in ("admin", "superadmin") or r["is_responsible"]))


async def notif_get(key: str):
    return await database.fetch_one(select(notifications).where(notifications.c.key == key))


async def notif_create(key: str, kind: str, payload: dict) -> Optional[int]:
    if await notif_get(key):
        return None
    return await database.execute(notifications.insert().values(
        key=key, kind=kind, payload=json.dumps(payload, ensure_ascii=False, default=str), status="open",
        remind_count=0, last_sent_at=datetime.utcnow(), created_at=datetime.utcnow()))


# ------------------------------ updates ------------------------------

async def handle_start(msg: dict) -> None:
    user = msg.get("from") or {}
    uid = int(user["id"])
    full_name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
    rights = await service.rights_of(uid)
    if rights["level"] or rights["employee_no"]:
        text = f"Assalomu alaykum, {html.escape(rights['name'] or full_name)}!\n\nHuquqlaringiz:{service.rights_text(rights)}"
        if rights["employee_no"]:
            text += "\n\nIshni boshlash/tugatishni pastdagi tugmalar orqali belgilang (joylashuv va kamera majburiy)."
        await telegram.send_to(uid, text, service.main_keyboard(rights))
        return

    existing = await database.fetch_one(select(tg_link_requests).where(tg_link_requests.c.telegram_user_id == uid))
    notify_admin = not existing or existing["status"] != "pending"
    if existing:
        await database.execute(tg_link_requests.update().where(tg_link_requests.c.telegram_user_id == uid).values(
            username=user.get("username"), full_name=full_name, status="pending",
            created_at=existing["created_at"] if existing["status"] == "pending" else datetime.utcnow()))
    else:
        await database.execute(tg_link_requests.insert().values(
            telegram_user_id=uid, username=user.get("username"), full_name=full_name, status="pending",
            created_at=datetime.utcnow()))
    await telegram.send_to(uid, (
        f"Assalomu alaykum!\n\nSizning Telegram ID: <code>{uid}</code>\n\n"
        "Siz hali tizimga biriktirilmagansiz. Rahbar sizni xodimga biriktirgandan keyin "
        "ishlashni boshlaysiz — o'shanda shu yerga xabar keladi."), {"remove_keyboard": True})
    if notify_admin:
        s = await service.get_settings()
        targets = [int(s["link_admin_id"])] if s.get("link_admin_id", "").strip().lstrip("-").isdigit() else await responsible_ids()
        btn = _webapp_button("👤 Biriktirish", "#/admin/requests")
        text = (f"🆕 Yangi foydalanuvchi biriktirishni kutmoqda\n\n"
                f"Ism: <b>{html.escape(full_name or '—')}</b>\n"
                f"{'Username: @' + html.escape(user['username']) + chr(10) if user.get('username') else ''}"
                f"Telegram ID: <code>{uid}</code>\n\nAdmin → So'rovlar bo'limida xodimga biriktiring.")
        for t in targets:
            await telegram.send_to(t, text, {"inline_keyboard": [[btn]]} if btn else None)


async def handle_callback(cb: dict) -> None:
    uid = int(cb["from"]["id"])
    data = cb.get("data") or ""
    answer = "OK"
    try:
        if data.startswith("gt:"):
            _, nid, stype = data.split(":", 2)
            if not await can_decide(uid):
                answer = "Sizda bu qarorni qabul qilish huquqi yo'q"
            else:
                n = await database.fetch_one(select(notifications).where(notifications.c.id == int(nid)))
                if not n:
                    answer = "Topilmadi"
                else:
                    p = json.loads(n["payload"])
                    # Javob smena sanasiga bog'lanadi (smena boshlanish vaqti), bosilgan vaqtga emas.
                    await service.save_resolution(p["employee_no"], datetime.fromisoformat(p["shift_start"]), stype, uid, confirmed=True)
                    await database.execute(notifications.update().where(notifications.c.id == n["id"]).values(
                        status="resolved", resolved_by=uid, resolved_at=datetime.utcnow()))
                    answer = "Saqlandi"
                    msg = cb.get("message")
                    if msg and TG_TOKEN:
                        await telegram._api("editMessageText", {
                            "chat_id": msg["chat"]["id"], "message_id": msg["message_id"], "parse_mode": "HTML",
                            "text": msg.get("text", "") + f"\n\n✅ {TYPE_LABEL.get(stype, stype)} deb belgilandi"})
    finally:
        if TG_TOKEN:
            await telegram._api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": answer})


async def handle_location(msg: dict, edited: bool) -> None:
    """Chatda yuborilgan joylashuv. Xaritadan qo'lda tanlangan nuqta (aniqligi yo'q, jonli emas)
    qabul qilinmaydi — faqat qurilma GPS'i yoki jonli joylashuv."""
    uid = int(msg["from"]["id"])
    loc = msg["location"]
    live = loc.get("live_period")
    acc = loc.get("horizontal_accuracy")
    rights = await service.rights_of(uid)
    if not rights["employee_no"]:
        if not edited:
            await handle_start(msg)
        return
    if not live and acc is None:
        if not edited:
            await telegram.send_to(uid, "⚠️ Bu joylashuv qabul qilinmadi (xaritadan tanlangan nuqta bo'lishi mumkin).\n\n"
                                        "📎 → Joylashuv → <b>«Jonli joylashuvni ulashish»</b> ni tanlang.")
        return
    now = datetime.utcnow()
    live_until = None
    if live:
        start = datetime.utcfromtimestamp(msg.get("date", now.timestamp()))
        live_until = start + timedelta(seconds=int(live)) if int(live) < 0x7FFFFFFF else now + timedelta(days=1)
    await service.save_chat_location(uid, loc["latitude"], loc["longitude"], acc, live_until, now)
    if not edited:
        txt = (f"📍 Jonli joylashuv qabul qilindi ({int(live) // 60} daqiqa)." if live and int(live) < 0x7FFFFFFF
               else "📍 Jonli joylashuv qabul qilindi." if live else "📍 Joylashuv qabul qilindi (3 daqiqa amal qiladi).")
        await telegram.send_to(uid, txt + "\n\nEndi pastdagi «Ishni boshladim» yoki «Ishni tugatdim» tugmasini bosing.",
                               service.main_keyboard(rights))


async def handle_update(upd: dict) -> None:
    if "callback_query" in upd:
        await handle_callback(upd["callback_query"])
        return
    edited = "edited_message" in upd
    msg = upd.get("message") or upd.get("edited_message")
    if not msg or msg.get("chat", {}).get("type") != "private" or "from" not in msg:
        return
    if "location" in msg:
        await handle_location(msg, edited)
        return
    if edited:
        return
    # Har qanday shaxsiy xabarga /start kabi javob beramiz — ID va holatni bilishi uchun.
    await handle_start(msg)


# ------------------------------ jadval ------------------------------

def _report_markup(date_iso: str) -> Optional[dict]:
    if MINIAPP_LINK:
        return {"inline_keyboard": [[{"text": "📊 Hisobotni ochish", "url": f"{MINIAPP_LINK}?startapp=day_{date_iso.replace('-', '')}"}]]}
    if PUBLIC_BASE_URL:
        return {"inline_keyboard": [[{"text": "📊 Hisobotni ochish", "url": f"{PUBLIC_BASE_URL}/davomat/#/day?date={date_iso}"}]]}
    return None


async def send_daily_report(day, ctx=None, shifts=None, chats=None) -> None:
    """Kechagi kun: kim keldi / kim ketdi — HTML jadval (sendRichMessage) guruhga."""
    from davomat.report import daily_html
    if shifts is None:
        ctx, shifts = await service.compute_range(day, day)
    html_text = daily_html(day, shifts, lambda e: service.name_of(ctx, e), ctx.role_names)
    for chat in chats or TG_CHATS:
        await telegram.send_rich(chat, html_text, _report_markup(str(day)))


async def job_daily(now: datetime, s: dict) -> None:
    if now.time() < _hm(s["daily_summary_time"]):
        return
    day = (now - timedelta(days=1)).date()
    if await notif_get(f"summary:{day}") and await notif_get(f"incomplete:{day}"):
        return
    ctx, shifts = await service.compute_range(day, day)
    if await notif_create(f"summary:{day}", "summary", {"date": str(day)}):
        await send_daily_report(day, ctx, shifts)

    incomplete = [x for x in shifts if x.status == ST_INCOMPLETE]
    if incomplete and await notif_create(f"incomplete:{day}", "incomplete", {"date": str(day), "count": len(incomplete)}):
        lines = []
        for x in incomplete[:25]:
            why = "kirish yo'q" if not x.kirish else ("chiqish yo'q" if not x.chiqish else "oxirida kirish, chiqish yo'q")
            lines.append(f"• {html.escape(service.name_of(ctx, x.employee_no))} — {why}")
        more = f"\n… yana {len(incomplete) - 25} ta" if len(incomplete) > 25 else ""
        btn = _webapp_button("✏️ Ko'rish va tuzatish", f"#/day?date={day}")
        for t in await responsible_ids():
            await telegram.send_to(t, f"⚠️ <b>{day.day}.{day.month:02d}</b> — to'liq bo'lmagan yozuvlar ({len(incomplete)}):\n\n"
                                      + "\n".join(lines) + more + "\n\nTasdiqlash yoki tuzatish uchun hisobotni oching.",
                                   {"inline_keyboard": [[btn]]} if btn else None)


async def job_guard_absent(now: datetime, s: dict) -> None:
    ctx = await service.load_context()
    today = now.date()
    guards = [no for no in ctx.employees if ctx.role_code_at(no, today) == "qorovul" and ctx.employees[no]["active"]]
    if not guards:
        return
    grace = timedelta(minutes=float(s["guard_grace_min"]))
    for stype, key in ((SHIFT_GUARD_DAY, "guard_day_start"), (SHIFT_GUARD_NIGHT, "guard_night_start")):
        start = datetime.combine(today, _hm(s[key]))
        if not (start + grace <= now < start + timedelta(hours=6)):
            continue
        nkey = f"guard_absent:{today}:{stype}"
        if await notif_get(nkey):
            continue
        punches = await service.load_punches(ctx, start - timedelta(hours=3), now)
        if any(no in punches for no in guards):
            continue
        await notif_create(nkey, "guard_absent", {"date": str(today), "type": stype})
        for t in await responsible_ids():
            await telegram.send_to(t, f"🚨 {TYPE_LABEL[stype]} smenaga ({start:%H:%M}) hozirgacha qorovul kelmadi "
                                      f"({now:%H:%M}).")


async def job_guard_unknown(now: datetime, s: dict) -> None:
    ctx, shifts = await service.compute_range(now.date() - timedelta(days=2), now.date())
    remind = timedelta(hours=float(s["remind_after_h"]))
    auto = timedelta(hours=float(s["auto_resolve_after_h"]))
    for sh in shifts:
        if sh.role != "qorovul" or sh.shift_type != SHIFT_UNKNOWN or not sh.punches:
            continue
        start = sh.punches[0].ts
        key = f"guard_type:{sh.employee_no}:{start.isoformat()}"
        payload = {"employee_no": sh.employee_no, "shift_start": start.isoformat()}
        name = html.escape(service.name_of(ctx, sh.employee_no))
        text = (f"❓ Qorovul smenasi aniqlanmadi\n\n<b>{name}</b> {start:%d.%m %H:%M} da keldi — "
                f"bu kunduzgi yoki tungi smenami?")
        nid = await notif_create(key, "guard_type", payload)
        if nid:
            await _send_guard_question(nid, text)
    utcnow = datetime.utcnow()
    for n in await database.fetch_all(select(notifications).where(and_(
            notifications.c.kind == "guard_type", notifications.c.status == "open"))):
        p = json.loads(n["payload"])
        if utcnow - n["created_at"] >= auto:
            st = datetime.fromisoformat(p["shift_start"])
            h = st.hour
            dist = lambda a: min(abs(h - a), 24 - abs(h - a))
            guess = SHIFT_GUARD_DAY if dist(_hm(s["guard_day_start"]).hour) <= dist(_hm(s["guard_night_start"]).hour) else SHIFT_GUARD_NIGHT
            await service.save_resolution(p["employee_no"], st, guess, None, confirmed=False)
            await database.execute(notifications.update().where(notifications.c.id == n["id"]).values(
                status="auto", resolved_at=utcnow))
            for t in await responsible_ids():
                await telegram.send_to(t, f"⏱ Javob bo'lmagani uchun {st:%d.%m %H:%M} dagi smena "
                                          f"<b>{TYPE_LABEL[guess]}</b> deb belgilandi (tasdiqlanmagan). Hisobotda o'zgartirish mumkin.")
        elif n["remind_count"] == 0 and utcnow - (n["last_sent_at"] or n["created_at"]) >= remind:
            st = datetime.fromisoformat(p["shift_start"])
            await _send_guard_question(n["id"], f"🔔 Eslatma: {st:%d.%m %H:%M} dagi qorovul smenasi turi hali tanlanmadi.")
            await database.execute(notifications.update().where(notifications.c.id == n["id"]).values(
                remind_count=1, last_sent_at=utcnow))


async def _send_guard_question(nid: int, text: str) -> None:
    kb = {"inline_keyboard": [[{"text": "☀️ Kunduzgi", "callback_data": f"gt:{nid}:{SHIFT_GUARD_DAY}"},
                               {"text": "🌙 Tungi", "callback_data": f"gt:{nid}:{SHIFT_GUARD_NIGHT}"}]]}
    for t in await responsible_ids():
        await telegram.send_to(t, text, kb)


async def tick(now: Optional[datetime] = None) -> None:
    now = now or service.now_local()
    s = await service.get_settings()
    await service.sync_employees()
    for job in (job_daily, job_guard_absent, job_guard_unknown):
        try:
            await job(now, s)
        except Exception:
            logger.exception("job %s xato", job.__name__)


# ------------------------------ main ------------------------------

async def poll_loop() -> None:
    offset = 0
    async with httpx.AsyncClient(timeout=40) as client:
        while True:
            try:
                r = await client.post(telegram.API.format(token=TG_TOKEN, method="getUpdates"),
                                      json={"offset": offset, "timeout": 25, "allowed_updates": ["message", "edited_message", "callback_query"]})
                data = r.json()
                if not data.get("ok"):
                    logger.error("getUpdates: %s", data)
                    await asyncio.sleep(10 if data.get("error_code") != 409 else 60)
                    continue
                for upd in data["result"]:
                    offset = upd["update_id"] + 1
                    try:
                        await handle_update(upd)
                    except Exception:
                        logger.exception("update qayta ishlashda xato: %s", upd.get("update_id"))
            except (httpx.HTTPError, ValueError):
                logger.warning("getUpdates tarmoq xatosi, 5s kutamiz")
                await asyncio.sleep(5)


async def schedule_loop() -> None:
    while True:
        await tick()
        await asyncio.sleep(60)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    create_all()
    await database.connect()
    await database.execute("PRAGMA busy_timeout=5000")
    if not TG_TOKEN:
        logger.error("TG_TOKEN yo'q — bot ishga tushmaydi")
        return
    if PUBLIC_BASE_URL:
        await telegram._api("setChatMenuButton", {"menu_button": {
            "type": "web_app", "text": "Davomat", "web_app": {"url": f"{PUBLIC_BASE_URL}/davomat/"}}})
    logger.info("🤖 Bot ishga tushdi")
    await asyncio.gather(poll_loop(), schedule_loop())


if __name__ == "__main__":
    asyncio.run(main())
