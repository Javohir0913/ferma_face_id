# -*- coding: utf-8 -*-
"""
Ferma — kameradan (KIRISH yoki CHIQISH) kelgan HTTP Listening event'ini
qayta ishlaydigan umumiy mantiq. Ikkala endpoint (`/event/kirish`,
`/event/chiqish`) shu funksiyani `gate` farqi bilan chaqiradi.

Auth yo'q — kamera sozlamasida buni ta'minlab bo'lmaydi, shuning uchun
faqat ixtiyoriy IP whitelist bilan cheklanadi. Har doim HTTP 200
qaytariladi — aks holda kamera eventni qayta-qayta yuborishga urinaveradi.
"""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request

from config import ALLOWED_IPS, SNAPSHOT_DIR, UNMATCHED_ALERT_DEBOUNCE_SEC
from database import database, events

import parser
import telegram

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = Path(SNAPSHOT_DIR)
SNAPSHOT_PATH.mkdir(parents=True, exist_ok=True)

GATE_LABELS = {"kirish": "🟢 Kirish", "chiqish": "🔴 Chiqish"}

UZ_MONTHS = (
    "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
    "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
)


def _format_time_uz(dt: datetime) -> str:
    return f"{dt.day} {UZ_MONTHS[dt.month - 1]} {dt.strftime('%H:%M')}"


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


async def handle_event(gate: str, request: Request) -> dict:
    ip = _client_ip(request)
    if ALLOWED_IPS and ip not in ALLOWED_IPS:
        logger.warning("%s: ruxsat etilmagan IP dan so'rov: %s", gate, ip)
        return {"status": "ignored"}

    fpath = None
    try:
        content_type = request.headers.get("content-type", "")
        raw_body = await request.body()
        text_payload, payload_format, image_bytes, image_name = parser.parse_event(content_type, raw_body)
        fields = parser.parse_fields(text_payload, payload_format)

        debug_dump = None
        if not text_payload:
            logger.warning(
                "%s: payload topilmadi. content-type=%r body_len=%d",
                gate, content_type, len(raw_body),
            )
            debug_dump = (
                f"[DEBUG parse-fail] content-type={content_type!r}\n"
                + raw_body[:4000].decode("utf-8", errors="replace")
            )

        event_time = fields.get("date_time_parsed") or datetime.now(timezone.utc)
        matched = bool(fields.get("matched"))
        person_name = fields.get("name")
        employee_no = fields.get("employee_no")
        confidence = fields.get("confidence")
        serial_no = fields.get("serial_no")
        # Kamera vaqti-vaqti bilan bo'sh/administrativ signal yuboradi
        # (masalan currentVerifyMode=invalid, xodim/ism yo'q) — bu haqiqiy
        # yuz tanish urinishi emas, DB'ga ham yozilmaydi.
        has_outcome = bool(fields.get("has_outcome", True)) if fields else False

        # Rasm Telegram'ga xotiradagi baytlardan (image_bytes) to'g'ridan-to'g'ri
        # yuboriladi — diskka faqat vaqtincha yoziladi, funksiya tugagach
        # (pastdagi `finally`da, qaysi yo'l bilan chiqishidan qat'iy nazar)
        # o'chiriladi. Doimiy nusxa disk to'lib ketishiga sabab bo'lardi.
        snapshot_path = None
        try:
            if not has_outcome and not debug_dump:
                logger.info("%s: outcome'siz event — DB'ga yozilmadi, xabar yuborilmadi", gate)
                return {"status": "ignored"}

            if image_bytes:
                fname = f"{gate}_{event_time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
                fpath = SNAPSHOT_PATH / fname
                fpath.write_bytes(image_bytes)
                snapshot_path = str(fpath)

            send_unmatched_alert = has_outcome
            if not matched and has_outcome:
                # Gunicorn ko'p worker bilan ishlaganda xotira o'rniga DB'dagi
                # shu gate uchun oxirgi "unmatched" yozuv vaqtiga qaraymiz.
                try:
                    last_row = await database.fetch_one(
                        events.select()
                        .where(events.c.gate == gate)
                        .where(events.c.matched == 0)
                        .order_by(events.c.id.desc())
                        .limit(1)
                    )
                    if last_row and last_row["created_at"]:
                        elapsed = (datetime.utcnow() - last_row["created_at"]).total_seconds()
                        if elapsed < UNMATCHED_ALERT_DEBOUNCE_SEC:
                            send_unmatched_alert = False
                except Exception:
                    logger.exception("%s: debounce tekshiruvida xato", gate)

            # Insertdan oldin tekshiriladi: joriy event hali bazada yo'q, shuning
            # uchun bugun undan oldingi kirish topilmasa — bu birinchi kirish.
            first_today = False
            if matched and gate == "kirish" and employee_no:
                local_time = event_time.replace(tzinfo=None)
                try:
                    prev = await database.fetch_one(
                        events.select()
                        .where(events.c.gate == "kirish")
                        .where(events.c.employee_no == employee_no)
                        .where(events.c.event_time >= local_time.replace(hour=0, minute=0, second=0, microsecond=0))
                        .where(events.c.event_time < local_time)
                        .limit(1)
                    )
                    first_today = prev is None
                except Exception:
                    logger.exception("%s: birinchi kirish tekshiruvida xato", gate)

            try:
                await database.execute(
                    events.insert().values(
                        gate=gate,
                        event_type=fields.get("event_type") or "unknown",
                        person_name=person_name,
                        employee_no=employee_no,
                        serial_no=serial_no,
                        matched=1 if matched else 0,
                        confidence=confidence,
                        snapshot_path=snapshot_path,
                        event_time=event_time.replace(tzinfo=None),
                        raw_data=(text_payload or debug_dump or "")[:20000],
                        created_at=datetime.utcnow(),
                    )
                )
            except Exception as e:
                if serial_no and "unique" in str(e).lower():
                    # Kamera tarmoq/ACK muammosi tufayli bitta eventni bir necha
                    # marta qayta yuborishi mumkin (bir xil serialNo) — DB'dagi
                    # UNIQUE index buni ushlaydi, jim o'tkazib yuboramiz.
                    logger.info("%s: takroriy event (serialNo=%s) — o'tkazib yuborildi", gate, serial_no)
                    return {"status": "duplicate"}
                logger.exception("%s: DB ga yozishda xato", gate)

            time_label = _format_time_uz(event_time)
            label = GATE_LABELS.get(gate, gate)
            if matched:
                display_name = person_name or "Noma’lum F.I.O"
                if first_today:
                    display_name += " ⭐️ Bugun 1-marta"
                text = f"{label}\n\n{time_label}\n\n{display_name}"
                await telegram.notify(text, image_bytes=image_bytes)
            elif send_unmatched_alert:
                text = f"{label}\n\n{time_label}\n\n⚠️ Noma’lum odam"
                await telegram.notify(text, image_bytes=image_bytes)
            elif not has_outcome:
                logger.info("%s: parse qilinmagan event DB'ga yozildi (debug), xabar yuborilmadi", gate)
            else:
                logger.info("%s: unmatched alert debounce bilan o'tkazib yuborildi", gate)
        finally:
            if fpath is not None:
                try:
                    fpath.unlink(missing_ok=True)
                except Exception:
                    logger.exception("%s: snapshot faylini o'chirishda xato: %s", gate, fpath)

    except Exception:
        logger.exception("%s: event qayta ishlashda xato", gate)

    return {"status": "ok"}
