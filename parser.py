# -*- coding: utf-8 -*-
"""
Ferma — Hikvision Face ID terminal (HTTP Listening) event'ini parse qilish.

Qurilma XML ham, JSON ham yuborishi mumkin (`multipart/form-data`, matn
qismi + ixtiyoriy JPEG rasm qismi). Har ikkisini ham qo'llab-quvvatlaymiz,
strukturaviy parsing ishlamasa xom baytlardan qidirib topamiz — hech qachon
butunlay bo'sh qaytmaslik uchun, `raw_data` doim to'liq saqlanadi.
"""
import json
import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from typing import Optional, Tuple
from xml.etree import ElementTree as ET

_JPEG_RE = re.compile(rb"\xff\xd8.*?\xff\xd9", re.DOTALL)
_DATE_FORMATS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S")


def _extract_jpeg_from_raw(raw: bytes) -> Optional[bytes]:
    m = _JPEG_RE.search(raw)
    return m.group(0) if m else None


def _extract_xml_from_raw(raw: bytes) -> Optional[str]:
    start = raw.find(b"<?xml")
    if start == -1:
        start = raw.find(b"<EventNotificationAlert")
    if start == -1:
        return None
    end = raw.rfind(b">")
    if end == -1 or end <= start:
        return None
    return raw[start:end + 1].decode("utf-8", errors="ignore")


def _parse_multipart(content_type: str, raw_body: bytes) -> Tuple[Optional[str], Optional[str], Optional[bytes], Optional[str]]:
    """(text_payload, payload_format, image_bytes, image_name) qaytaradi."""
    header = f"Content-Type: {content_type}\r\n\r\n".encode("ascii", errors="ignore")
    msg = BytesParser(policy=policy.compat32).parsebytes(header + raw_body)

    text_payload = None
    payload_format = None
    image_bytes = None
    image_name = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            ctype = (part.get_content_type() or "").lower()
            filename = part.get_filename()
            stripped = payload.strip()
            if ctype.startswith("image/") or (filename and filename.lower().endswith((".jpg", ".jpeg"))):
                image_bytes = payload
                image_name = filename or "snapshot.jpg"
            elif text_payload is None and (
                ctype in ("application/xml", "text/xml") or stripped.startswith(b"<")
            ):
                text_payload = payload.decode("utf-8", errors="ignore")
                payload_format = "xml"
            elif text_payload is None and (
                ctype == "application/json" or stripped.startswith(b"{") or stripped.startswith(b"[")
            ):
                text_payload = payload.decode("utf-8", errors="ignore")
                payload_format = "json"
    return text_payload, payload_format, image_bytes, image_name


def parse_event(content_type: str, raw_body: bytes) -> Tuple[Optional[str], Optional[str], Optional[bytes], Optional[str]]:
    """(text_payload, payload_format, image_bytes, image_name) qaytaradi."""
    content_type_l = (content_type or "").lower()
    text_payload = None
    payload_format = None
    image_bytes = None
    image_name = None

    if content_type_l.startswith("multipart/"):
        try:
            text_payload, payload_format, image_bytes, image_name = _parse_multipart(content_type, raw_body)
        except Exception:
            text_payload, payload_format, image_bytes, image_name = None, None, None, None
    elif "json" in content_type_l:
        text_payload, payload_format = raw_body.decode("utf-8", errors="ignore"), "json"
    elif "xml" in content_type_l:
        text_payload, payload_format = raw_body.decode("utf-8", errors="ignore"), "xml"

    if text_payload is None:
        text_payload = _extract_xml_from_raw(raw_body)
        if text_payload is not None:
            payload_format = "xml"
    if text_payload is None:
        stripped = raw_body.strip()
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            try:
                json.loads(stripped)
                text_payload = stripped.decode("utf-8", errors="ignore")
                payload_format = "json"
            except (ValueError, UnicodeDecodeError):
                pass
    if image_bytes is None:
        image_bytes = _extract_jpeg_from_raw(raw_body)
        if image_bytes:
            image_name = image_name or "snapshot.jpg"

    return text_payload, payload_format, image_bytes, image_name


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    v = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_xml_fields(xml_text: str) -> dict:
    if not xml_text:
        return {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    values = {}
    for el in root.iter():
        tag = _strip_ns(el.tag)
        text = (el.text or "").strip()
        if text and tag not in values:
            values[tag] = text

    event_type = values.get("eventType") or values.get("majorEventType") or _strip_ns(root.tag)
    employee_no = (values.get("employeeNoString") or values.get("employeeNo") or "").strip()
    name = values.get("name")

    confidence_raw = values.get("similarity") or values.get("FaceScore") or values.get("faceScore")
    confidence = None
    if confidence_raw:
        try:
            confidence = float(confidence_raw)
            if confidence <= 1:
                confidence *= 100
        except ValueError:
            confidence = None

    matched = bool(employee_no) and employee_no != "0"

    return {
        "event_type": event_type,
        "employee_no": employee_no or None,
        "name": name,
        "matched": matched,
        "confidence": confidence,
        "date_time_parsed": _parse_datetime(values.get("dateTime")),
        "event_description": values.get("eventDescription"),
        "verify_mode": values.get("currentVerifyMode"),
        "serial_no": values.get("serialNo") or None,
        "has_outcome": True,
    }


def parse_json_fields(json_text: str) -> dict:
    """DS-K1T343EWX kabi qurilmalar XML o'rniga JSON yuboradi (multipart
    qismi `event_log`, ichida `AccessControllerEvent` obyekti nested holda)."""
    if not json_text:
        return {}
    try:
        data = json.loads(json_text)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}

    merged = dict(data)
    for key, val in data.items():
        if isinstance(val, dict) and key.lower().endswith("event"):
            merged.update(val)

    def _get(*names):
        for n in names:
            v = merged.get(n)
            if v not in (None, ""):
                return v
        return None

    employee_no = _get("employeeNoString", "employeeNo", "cardNo")
    employee_no = str(employee_no).strip() if employee_no is not None else ""
    name = _get("name")

    confidence_raw = _get("similarity", "FaceScore", "faceScore")
    confidence = None
    if confidence_raw is not None:
        try:
            confidence = float(confidence_raw)
            if confidence <= 1:
                confidence *= 100
        except (TypeError, ValueError):
            confidence = None

    matched = bool(employee_no) and employee_no != "0"
    verify_mode = _get("currentVerifyMode")
    status_value = _get("statusValue")

    # "invalid" verifyMode + xodim/ism yo'q — bu haqiqiy yuz tanish natijasi
    # emas, balki qurilmaning oraliq/administrativ signali. Bunday holatda
    # hech qanday xabar yuborilmaydi va DB'ga ham yozilmaydi (spam'ning oldi
    # olinadi — bitrix24_and_sap/v3/hikvision'da amalda tasdiqlangan yechim).
    has_outcome = matched or (verify_mode not in (None, "invalid"))
    serial_no = _get("serialNo")
    serial_no = str(serial_no) if serial_no is not None else None

    return {
        "event_type": _get("eventType") or "AccessControllerEvent",
        "employee_no": employee_no or None,
        "name": name,
        "matched": matched,
        "confidence": confidence,
        "date_time_parsed": _parse_datetime(_get("dateTime")),
        "event_description": _get("eventDescription"),
        "verify_mode": verify_mode,
        "status_value": status_value,
        "serial_no": serial_no,
        "has_outcome": has_outcome,
    }


def parse_fields(text_payload: Optional[str], payload_format: Optional[str]) -> dict:
    if not text_payload:
        return {}
    if payload_format == "json":
        return parse_json_fields(text_payload)
    return parse_xml_fields(text_payload)
