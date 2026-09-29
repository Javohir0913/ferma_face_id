# -*- coding: utf-8 -*-
"""
Davomat hisoblash mantiqi — bazaga bog'liq emas, sof funksiyalar.

Kirish: bitta xodimning kirish/chiqish belgilari (Face ID yoki Telegram check-in).
Chiqish: smenalar (kun yoki qorovul smenasi) — ish soati, fermada o'tgan vaqt, holat.

Asosiy qoidalar (tahlil natijasiga ko'ra):
  * Bir xil yo'nalishdagi, bir xil manbadan kelgan, `debounce_sec` ichidagi
    belgilar bitta hisoblanadi (kirishda birinchisi, chiqishda oxirgisi qoladi).
  * Ish soati = birinchi kirish -> oxirgi chiqish.
  * Fermada = ish soati - tashqarida o'tgan vaqt (chiqish -> keyingi kirish).
    Kirish kamerasi odamlarni ko'p o'tkazib yuboradi, shuning uchun ketma-ket
    ikki chiqish orasidagi vaqt kesilmaydi, faqat belgi qo'yiladi.
  * Juftsiz holat taxmin qilinmaydi — "to'liq emas".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

IN, OUT = "in", "out"

ST_CLOSED = "yopildi"
ST_OPEN = "jarayonda"
ST_INCOMPLETE = "to'liq emas"
ST_UNCONFIRMED = "tasdiqlanmagan"
ST_MANUAL = "qo'lda tuzatilgan"

SHIFT_DAY = "kun"            # oddiy kunlik hisob (standart, sog'uvchi, tashqi)
SHIFT_GUARD_DAY = "kunduzgi"
SHIFT_GUARD_NIGHT = "tungi"
SHIFT_UNKNOWN = "noma'lum"


@dataclass(frozen=True)
class Punch:
    ts: datetime
    direction: str            # IN | OUT
    source: str = "faceid"    # faceid | telegram
    ref: str = ""             # "e:<events.id>" | "c:<checkins.id>"
    outside: bool = False     # Telegram check-in ferma hududidan tashqarida


@dataclass(frozen=True)
class RoleParams:
    code: str = "standart"
    mode: str = "day"                   # "day" | "shift" (qorovul)
    day_boundary: time = time(3, 0)     # shu vaqtgacha bo'lgan belgilar oldingi kunga
    debounce_sec: int = 60
    max_shift_hours: float = 16.0       # "jarayonda" holati shu muddatgacha
    day_window: tuple[int, int] = (6, 11)     # qorovul kunduzgi smena boshlanish soatlari [from, to)
    night_window: tuple[int, int] = (18, 24)  # qorovul tungi smena boshlanish soatlari [from, to)

    @staticmethod
    def from_dict(code: str, d: dict) -> "RoleParams":
        def _t(v, default):
            if not v:
                return default
            h, m = (int(x) for x in str(v).split(":")[:2])
            return time(h, m)
        return RoleParams(
            code=code,
            mode=d.get("mode", "day"),
            day_boundary=_t(d.get("day_boundary"), time(3, 0)),
            debounce_sec=int(d.get("debounce_sec", 60)),
            max_shift_hours=float(d.get("max_shift_hours", 16)),
            day_window=tuple(d.get("day_window", (6, 11))),
            night_window=tuple(d.get("night_window", (18, 24))),
        )


@dataclass
class Correction:
    field: str                  # "kirish" | "chiqish"
    value: Optional[datetime]
    note: str = ""


@dataclass
class Shift:
    employee_no: str
    work_date: date
    role: str
    shift_type: str
    kirish: Optional[datetime] = None
    chiqish: Optional[datetime] = None
    span_sec: Optional[int] = None      # ish soati
    inside_sec: Optional[int] = None    # fermada
    outside_sec: int = 0
    status: str = ST_INCOMPLETE
    flags: list[str] = field(default_factory=list)
    punches: list[Punch] = field(default_factory=list)   # hisobga olinganlar
    merged: list[Punch] = field(default_factory=list)    # dublikat sifatida birlashtirilgan
    corrected: bool = False
    unconfirmed: bool = False

    @property
    def start(self) -> datetime:
        return self.punches[0].ts if self.punches else datetime.combine(self.work_date, time())


def work_date_of(ts: datetime, boundary: time) -> date:
    return (ts - timedelta(hours=boundary.hour, minutes=boundary.minute)).date()


def debounce(punches: Iterable[Punch], sec: int) -> tuple[list[Punch], list[Punch]]:
    """Ketma-ket, bir xil yo'nalish + manba, `sec` ichidagi belgilarni birlashtiradi.

    Zanjir bo'yicha: har bir belgi oldingisidan `sec` ichida bo'lsa bitta "portlash".
    Kirishda birinchisi, chiqishda oxirgisi qoldiriladi.
    """
    kept: list[Punch] = []
    merged: list[Punch] = []
    last_in_burst: Optional[Punch] = None
    for p in sorted(punches, key=lambda x: x.ts):
        prev = kept[-1] if kept else None
        same_burst = (
            prev is not None
            and last_in_burst is not None
            and p.direction == prev.direction
            and p.source == prev.source
            and (p.ts - last_in_burst.ts).total_seconds() < sec
        )
        if same_burst:
            if p.direction == OUT:
                merged.append(kept[-1])
                kept[-1] = p
            else:
                merged.append(p)
        else:
            kept.append(p)
        last_in_burst = p
    return kept, merged


def _guard_type(start: datetime, rp: RoleParams) -> str:
    h = start.hour
    if rp.day_window[0] <= h < rp.day_window[1]:
        return SHIFT_GUARD_DAY
    if rp.night_window[0] <= h < rp.night_window[1]:
        return SHIFT_GUARD_NIGHT
    return SHIFT_UNKNOWN


def group(kept: list[Punch], rp: RoleParams) -> list[tuple[date, str, list[Punch]]]:
    """Belgilarni smenalarga ajratadi: (smena sanasi, smena turi, belgilar)."""
    if not kept:
        return []
    if rp.mode != "shift":
        by_day: dict[date, list[Punch]] = {}
        for p in kept:
            by_day.setdefault(work_date_of(p.ts, rp.day_boundary), []).append(p)
        return [(d, SHIFT_DAY, ps) for d, ps in sorted(by_day.items())]

    # Qorovul: smena birinchi belgidan boshlanadi va max_shift_hours ichidagi
    # barcha belgilarni o'z ichiga oladi. Smena sanasi boshlanish vaqti va rolning
    # kun chegarasi (qorovul uchun 12:00) bo'yicha — smena o'rtasidan bo'linmaydi.
    # Ketma-ket ikki smena (masalan tungi, keyin kunduzgi): 10 soatdan keyingi
    # yangi kirish — smena almashuvi.
    out: list[tuple[date, str, list[Punch]]] = []
    cur: list[Punch] = []
    for p in kept:
        elapsed = (p.ts - cur[0].ts).total_seconds() if cur else 0
        if cur and (elapsed > rp.max_shift_hours * 3600 or (p.direction == IN and elapsed >= 10 * 3600)):
            out.append((work_date_of(cur[0].ts, rp.day_boundary), _guard_type(cur[0].ts, rp), cur))
            cur = []
        cur.append(p)
    if cur:
        out.append((work_date_of(cur[0].ts, rp.day_boundary), _guard_type(cur[0].ts, rp), cur))
    return out


def summarize(
    employee_no: str,
    work_date: date,
    shift_type: str,
    ps: list[Punch],
    rp: RoleParams,
    now: datetime,
    corrections: Optional[list[Correction]] = None,
) -> Shift:
    sh = Shift(employee_no=employee_no, work_date=work_date, role=rp.code, shift_type=shift_type, punches=ps)

    first_in = next((p for p in ps if p.direction == IN), None)
    kirish = first_in.ts if first_in else None
    last_out = next((p for p in reversed(ps) if p.direction == OUT and (kirish is None or p.ts > kirish)), None)
    chiqish = last_out.ts if last_out else None

    for a, b in zip(ps, ps[1:]):
        if a.direction == OUT and b.direction == OUT:
            sh.flags.append("kirish qayd etilmagan")
        elif a.direction == IN and b.direction == IN:
            sh.flags.append("chiqish qayd etilmagan")
    if ps and ps[0].direction == OUT:
        sh.flags.append("kun chiqish bilan boshlangan")
    if any(p.outside for p in ps):
        sh.flags.append("hududdan tashqarida belgilangan")

    for c in corrections or []:
        if c.field == "kirish":
            kirish = c.value
        elif c.field == "chiqish":
            chiqish = c.value
        sh.corrected = True

    sh.kirish, sh.chiqish = kirish, chiqish

    if kirish and chiqish and chiqish > kirish:
        span = int((chiqish - kirish).total_seconds())
        outside = 0
        for a, b in zip(ps, ps[1:]):
            if a.direction == OUT and b.direction == IN and a.ts >= kirish and b.ts <= chiqish:
                outside += int((b.ts - a.ts).total_seconds())
        sh.span_sec = span
        sh.outside_sec = outside
        sh.inside_sec = max(span - outside, 0)

    ends_inside = bool(ps) and ps[-1].direction == IN and not (chiqish and ps[-1].ts < chiqish)
    still_running = kirish is not None and (now - kirish).total_seconds() < rp.max_shift_hours * 3600

    if sh.corrected:
        sh.status = ST_MANUAL if (sh.kirish and sh.chiqish) else ST_INCOMPLETE
    elif kirish and chiqish and not ends_inside:
        sh.status = ST_CLOSED
    elif kirish and still_running and (ends_inside or chiqish is None):
        sh.status = ST_OPEN
    else:
        sh.status = ST_INCOMPLETE

    if shift_type == SHIFT_UNKNOWN and sh.status != ST_MANUAL:
        sh.flags.append("smena turi aniqlanmadi")
    return sh


def compute(
    employee_no: str,
    punches: Iterable[Punch],
    rp: RoleParams,
    now: datetime,
    corrections: Optional[dict[date, list[Correction]]] = None,
    resolutions: Optional[dict[datetime, tuple[str, bool]]] = None,
) -> list[Shift]:
    """Bitta xodim, bitta rol davri uchun smenalar ro'yxati.

    resolutions: {smena boshlanish vaqti: (smena turi, tasdiqlanganmi)} — qorovul
    smenasi turi aniqlanmaganda qabul qilingan qaror.
    """
    kept, merged = debounce(punches, rp.debounce_sec)
    shifts: list[Shift] = []
    for wd, stype, ps in group(kept, rp):
        if stype == SHIFT_UNKNOWN and resolutions and ps[0].ts in resolutions:
            stype, confirmed = resolutions[ps[0].ts]
            unconfirmed = not confirmed
        else:
            unconfirmed = False
        sh = summarize(employee_no, wd, stype, ps, rp, now, (corrections or {}).get(wd))
        if unconfirmed and sh.status != ST_MANUAL:
            sh.status = ST_UNCONFIRMED
            sh.unconfirmed = True
        lo, hi = ps[0].ts, ps[-1].ts
        sh.merged = [m for m in merged if lo - timedelta(seconds=rp.debounce_sec) <= m.ts <= hi + timedelta(seconds=rp.debounce_sec)]
        shifts.append(sh)
    return shifts


def compute_with_roles(
    employee_no: str,
    punches: Iterable[Punch],
    role_at,  # Callable[[date], RoleParams]
    now: datetime,
    corrections: Optional[dict[date, list[Correction]]] = None,
    resolutions: Optional[dict[datetime, tuple[str, bool]]] = None,
) -> list[Shift]:
    """Rol vaqt bilan o'zgarsa, har bir rol davri alohida hisoblanadi —
    eski oylar yangi rol parametrlari bilan qayta buzilmaydi."""
    segments: list[tuple[RoleParams, list[Punch]]] = []
    for p in sorted(punches, key=lambda x: x.ts):
        # Rol sanasi kun chegarasi (03:00) bo'yicha aniqlanadi, aks holda
        # yarim tundan keyingi chiqish boshqa rol davriga tushib qolishi mumkin.
        rp = role_at(work_date_of(p.ts, time(3, 0)))
        if segments and segments[-1][0] == rp:
            segments[-1][1].append(p)
        else:
            segments.append((rp, [p]))
    out: list[Shift] = []
    for rp, ps in segments:
        out.extend(compute(employee_no, ps, rp, now, corrections, resolutions))
    return out


def guard_shift_count(punches: Iterable[Punch], day_start: time, night_start: time, tol_h: float = 1.5) -> tuple[int, int]:
    """Qorovul smenalari sonini va ishlangan kunlar sonini qaytaradi.

    Smena: kirish ~kunduzgi boshlanishda va chiqish shu kuni ~tungi boshlanishda
    (09:00 -> 21:00), yoki kirish ~tungi boshlanishda va ertasi kuni chiqish
    ~kunduzgi boshlanishda (21:00 -> 09:00).
    """
    def near(ts: datetime, t: time) -> bool:
        x = ts.hour + ts.minute / 60
        y = t.hour + t.minute / 60
        d = abs(x - y)
        return min(d, 24 - d) <= tol_h

    by_day: dict[date, list[Punch]] = {}
    for p in punches:
        by_day.setdefault(p.ts.date(), []).append(p)
    shifts = 0
    for d, ps in by_day.items():
        ins_day = any(p.direction == IN and near(p.ts, day_start) for p in ps)
        outs_night = any(p.direction == OUT and near(p.ts, night_start) for p in ps)
        ins_night = any(p.direction == IN and near(p.ts, night_start) for p in ps)
        next_ps = by_day.get(d + timedelta(days=1), [])
        outs_next_morning = any(p.direction == OUT and near(p.ts, day_start) for p in next_ps)
        shifts += (ins_day and outs_night) + (ins_night and outs_next_morning)
    return shifts, len(by_day)


def fmt_duration(sec: Optional[int]) -> str:
    if sec is None:
        return "—"
    h, m = divmod(int(sec) // 60, 60)
    return f"{h}s {m:02d}m"
