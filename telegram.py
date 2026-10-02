# -*- coding: utf-8 -*-
"""Ферма — push в Telegram."""
import logging
from typing import Any, Dict, Optional

import httpx

from config import TG_CHATS, TG_TOKEN

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


def is_configured() -> bool:
    return bool(TG_TOKEN) and bool(TG_CHATS)


async def _api(method: str, data: Dict[str, Any], files: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = API.format(token=TG_TOKEN, method=method)
    async with httpx.AsyncClient(timeout=30) as client:
        if files:
            r = await client.post(url, data=data, files=files)
        else:
            r = await client.post(url, json=data)
    result = r.json()
    if not result.get("ok"):
        logger.warning("telegram %s xato: %s", method, result)
    return result


async def send_to(chat_id: int | str, text: str, reply_markup: Optional[dict] = None) -> Optional[dict]:
    """Сообщение в один чат (обычно личный). Если токена нет (локальный тест) — только пишется в лог."""
    if not TG_TOKEN:
        logger.info("TG_TOKEN yo'q — [%s] ga yuborilmadi: %s | markup=%s", chat_id, text, reply_markup)
        return None
    data: Dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        return await _api("sendMessage", data)
    except Exception:
        logger.exception("telegram: %s ga yuborilmadi", chat_id)
        return None


def rich_to_plain(html_text: str) -> str:
    """Если sendRichMessage отклонён: <table> превращается в строки, остаются только <b>/<i>."""
    import re
    t = html_text
    t = re.sub(r"<caption>(.*?)</caption>", r"<b>\1</b>\n", t, flags=re.S)
    t = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", " | ", t)
    t = re.sub(r"<tr[^>]*>", "", t)
    t = re.sub(r"</tr>", "\n", t)
    t = re.sub(r"</?table[^>]*>", "\n", t)
    t = re.sub(r"</p>|<br\s*/?>", "\n", t)
    t = re.sub(r"<p>", "", t)
    t = re.sub(r"<(?!/?b>|/?i>)[^>]+>", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


async def send_rich(chat_id: int | str, html_text: str, reply_markup: Optional[dict] = None) -> Optional[dict]:
    """Сообщение с настоящей HTML-таблицей (<table>) — sendRichMessage; иначе обычный текст."""
    if not TG_TOKEN:
        logger.info("TG_TOKEN yo'q — [%s] ga rich yuborilmadi:\n%s", chat_id, rich_to_plain(html_text))
        return None
    payload: Dict[str, Any] = {"chat_id": chat_id, "rich_message": {"html": html_text, "skip_entity_detection": True}}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = await _api("sendRichMessage", payload)
        if res.get("ok"):
            return res
    except Exception:
        logger.exception("sendRichMessage xato — oddiy matnga o'tildi")
    plain = rich_to_plain(html_text)
    out = None
    # Если длиннее 4096 символов — отправляется частями (кнопка в последней).
    chunks, cur = [], ""
    for line in plain.split("\n"):
        if len(cur) + len(line) + 1 > 3900:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    chunks.append(cur)
    for i, ch in enumerate(chunks):
        data: Dict[str, Any] = {"chat_id": chat_id, "text": ch, "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_markup and i == len(chunks) - 1:
            data["reply_markup"] = reply_markup
        out = await _api("sendMessage", data)
    return out


async def notify(text: str, image_bytes: Optional[bytes] = None, image_name: str = "snapshot.jpg") -> None:
    if not is_configured():
        logger.info("TG_TOKEN/TG_CHATS sozlanmagan — telegram xabar yuborilmadi: %s", text)
        return
    for chat_id in TG_CHATS:
        try:
            if image_bytes:
                await _api(
                    "sendPhoto",
                    {"chat_id": chat_id, "caption": text, "parse_mode": "HTML"},
                    files={"photo": (image_name, image_bytes, "image/jpeg")},
                )
            else:
                await _api(
                    "sendMessage",
                    {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                )
        except Exception:
            logger.exception("telegram: chat %s ga yuborilmadi", chat_id)
