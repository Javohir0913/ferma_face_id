# -*- coding: utf-8 -*-
"""Kunlik davomat hisoboti — Telegram sendRichMessage uchun HTML jadval."""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from typing import Optional

from davomat.engine import ST_CLOSED, ST_INCOMPLETE, ST_OPEN, Shift

OYLAR = ("yanvar", "fevral", "mart", "aprel", "may", "iyun",
         "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr")
ROLE_ORDER = ["direktor", "administrator", "standart", "soguvchi", "qorovul", "taminotchi", "tashqi"]
ROLE_TITLE = {"direktor": "👔 Direktor", "administrator": "🗂 Administratorlar", "standart": "👷 Standart",
              "soguvchi": "🐄 Sog'uvchilar", "qorovul": "🛡 Qorovullar", "taminotchi": "🚚 Ta'minotchilar",
              "tashqi": "🚜 Tashqi ish"}
STATUS_MARK = {ST_CLOSED: "", ST_OPEN: " ⏳", ST_INCOMPLETE: " ⚠️", "tasdiqlanmagan": " ❓", "qo'lda tuzatilgan": " ✏️"}


def nice_date(d: date) -> str:
    return f"{d.day} {OYLAR[d.month - 1]}"


def dur_long(sec: Optional[int]) -> str:
    if sec is None:
        return "—"
    m = int(sec) // 60
    h, m = divmod(m, 60)
    if h and m:
        return f"{h} soat {m} minut"
    return f"{h} soat" if h else f"{m} minut"


def _t(ts: Optional[datetime], day: date) -> str:
    if not ts:
        return "—"
    s = ts.strftime("%H:%M")
    return s if ts.date() == day else f"{s} <i>({ts.day}.{ts.month:02d})</i>"


def _table(caption: str, rows: list[list[str]]) -> str:
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in ("F.I.O.", "Kirish", "Chiqish", "Ish soati", "Fermada ish soati")) + "</tr>"
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table bordered striped><caption>{escape(caption)}</caption>{head}{body}</table>"


def daily_html(day: date, shifts: list[Shift], name_of, role_names: dict[str, str]) -> str:
    people = len({s.employee_no for s in shifts})
    closed = sum(1 for s in shifts if s.status in (ST_CLOSED, "qo'lda tuzatilgan"))
    incomplete = sum(1 for s in shifts if s.status == ST_INCOMPLETE)
    parts = [f"<p>📋 <b>{nice_date(day)} — kim keldi, kim ketdi</b></p>",
             f"<p><i>Jami {people} kishi · yopildi {closed} · to'liq emas {incomplete}</i></p>"]
    by_role: dict[str, list[Shift]] = {}
    for s in shifts:
        by_role.setdefault(s.role, []).append(s)
    for role in ROLE_ORDER + sorted(set(by_role) - set(ROLE_ORDER)):
        # Fermada ish soati bo'yicha o'sish tartibida — eng kam ishlagan tepada.
        # Soati hisoblanmaganlar (chiqish yo'q — ehtimol hali fermada) oxirida.
        items = sorted(by_role.get(role, []),
                       key=lambda s: (s.inside_sec is None, s.inside_sec or 0, name_of(s.employee_no)))
        if not items:
            continue
        rows = []
        for s in items:
            name = escape(name_of(s.employee_no)) + STATUS_MARK.get(s.status, "")
            if s.shift_type in ("kunduzgi", "tungi"):
                name += " <i>(" + ("☀️ kunduzgi" if s.shift_type == "kunduzgi" else "🌙 tungi") + ")</i>"
            rows.append([name, _t(s.kirish, day), _t(s.chiqish, day), dur_long(s.span_sec), f"<b>{dur_long(s.inside_sec)}</b>"])
        parts.append(_table(f"{ROLE_TITLE.get(role, role_names.get(role, role))} ({len(items)})", rows))
    if not shifts:
        parts.append("<p>Bu kun uchun belgi yo'q.</p>")
    parts.append("<p><i>⚠️ to'liq emas · ⏳ jarayonda · ❓ tasdiqlanmagan · ✏️ qo'lda tuzatilgan. "
                 "Tartib: eng kam ishlagan tepada, chiqishi yo'qlar oxirida. Kun almashishi: sog'uvchi — 03:00, qorovul — 12:00, qolganlar — 00:00.</i></p>")
    return "".join(parts)
