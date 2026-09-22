# -*- coding: utf-8 -*-
"""Ferma — Telegram push."""
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
