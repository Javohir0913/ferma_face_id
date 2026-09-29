# -*- coding: utf-8 -*-
"""Bazadan ma'lumot yuklab, engine orqali smenalarni hisoblaydi."""
from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select

from config import PUBLIC_BASE_URL, TIMEZONE
from database import (
    app_users, audit_log, checkins, corrections, database, employee_roles,
    employees, events, notifications, resolutions, roles, settings, tg_locations, web_credentials,
)
from davomat.engine import IN, OUT, Correction, Punch, RoleParams, Shift, compute_with_roles

TZ = ZoneInfo(TIMEZONE)

ROLE_DEFAULTS = {
    "standart": ("Standart", {"mode": "day", "day_boundary": "03:00", "debounce_sec": 60, "max_shift_hours": 16}),
    "soguvchi": ("Sog'uvchi", {"mode": "day", "day_boundary": "03:00", "debounce_sec": 60, "max_shift_hours": 23}),
    # Smenalar 09:00–21:00 va 21:00–09:00; boshlanish oynasi ±2 soat.
    "qorovul": ("Qorovul", {"mode": "shift", "day_boundary": "12:00", "debounce_sec": 60, "max_shift_hours": 14,
                            "day_window": [6, 13], "night_window": [17, 24]}),
    "tashqi": ("Tashqi ish", {"mode": "day", "day_boundary": "03:00", "debounce_sec": 60, "max_shift_hours": 16}),
}

SETTING_DEFAULTS = {
    "farm_lat": "",
    "farm_lon": "",
    "farm_radius_m": "300",
    "max_accuracy_m": "100",
    "guard_day_start": "09:00",
    "guard_night_start": "21:00",
    "guard_grace_min": "30",
    "daily_summary_time": "08:00",
    "remind_after_h": "3",
    "auto_resolve_after_h": "6",
    # Botga /start bosgan, hali biriktirilmagan odamlar haqida xabar oladigan bitta Telegram ID.
    "link_admin_id": "",
    # Qorovulni smena naqshidan avtomatik aniqlash (sinovda xato natija berdi — o'chiq).
    "auto_guard_detect": "0",
}

# 1-bosqich tahlilidagi guruhlar — boshlang'ich taxmin, admin sahifasida tuzatiladi.
# Boshlang'ich rollar: faqat qorovullar (ferma rahbari aytgan). Qolganlar — standart,
# sog'uvchilarni admin o'zi belgilaydi.
SEED_ROLES = {
    "qorovul": ["00000020", "00000034"],  # Abdumutal Abdullayev, Fayziyev Tavakkal
}
# Qorovul qo'lda belgilanmaydi — detect_guards() smena naqshidan o'zi aniqlaydi.
GUARD_LOOKBACK_DAYS = 28
GUARD_MIN_SHIFTS = 6
GUARD_MIN_RATIO = 0.4
GUARD_TOL_H = 1.5
# Bitta odam ikki ID bilan bo'lsa — admin sahifasida qo'lda birlashtiriladi.
SEED_MERGES: dict[str, str] = {}
SEED_INACTIVE = {"1"}
SEED_ROLE_FROM = "2026-07-01"


def now_local() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


async def audit(actor_id: Optional[int], action: str, entity: str, entity_id, before=None, after=None):
    await database.execute(audit_log.insert().values(
        actor_id=actor_id, action=action, entity=entity, entity_id=str(entity_id) if entity_id is not None else None,
        before=json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
        after=json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
        created_at=datetime.utcnow(),
    ))


_NEW_EMPLOYEES_SQL = (
    "INSERT OR IGNORE INTO employees (employee_no, full_name, active, created_at) "
    "SELECT e.employee_no, COALESCE(e.person_name, 'ID ' || e.employee_no), "
    "       CASE WHEN e.employee_no IN ({inactive}) THEN 0 ELSE 1 END, CURRENT_TIMESTAMP "
    "FROM events e WHERE e.matched = 1 AND e.employee_no IS NOT NULL "
    "  AND e.employee_no NOT IN (SELECT employee_no FROM employees) "
    "  AND e.id = (SELECT MAX(id) FROM events x WHERE x.employee_no = e.employee_no AND x.matched = 1)"
).format(inactive=",".join(f"'{x}'" for x in SEED_INACTIVE))


async def sync_employees() -> None:
    """events'da paydo bo'lgan yangi xodimlarni employees'ga qo'shadi (ism — oxirgisi)."""
    await database.execute(_NEW_EMPLOYEES_SQL)


def seed_sync(db_path: str, admin_ids: list[int], superadmin_id: Optional[int] = None) -> list[int]:
    """Boshlang'ich ma'lumotlar. BEGIN IMMEDIATE — bir nechta gunicorn worker bir vaqtda
    ishga tushsa ham faqat bittasi yozadi, qolganlari kutib, tayyor holatni ko'radi.
    Super admin .env dagi SUPERADMIN_TELEGRAM_ID dan olinadi (boshqa super admin bo'lsa admin qilinadi).
    Yangi yaratilgan adminlar ro'yxatini qaytaradi (ularga xabar yuborish uchun)."""
    import sqlite3
    con = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    new_admins: list[int] = []
    try:
        con.execute("BEGIN IMMEDIATE")
        for code, (name, params) in ROLE_DEFAULTS.items():
            con.execute("INSERT OR IGNORE INTO roles (code, name, params) VALUES (?, ?, ?)", (code, name, json.dumps(params)))
        for k, v in SETTING_DEFAULTS.items():
            con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        first_run = con.execute("SELECT 1 FROM employees LIMIT 1").fetchone() is None
        con.execute(_NEW_EMPLOYEES_SQL)
        if first_run:
            for code, nos in SEED_ROLES.items():
                for no in nos:
                    if con.execute("SELECT 1 FROM employees WHERE employee_no = ?", (no,)).fetchone():
                        con.execute("INSERT INTO employee_roles (employee_no, role, valid_from, created_at) "
                                    "VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (no, code, SEED_ROLE_FROM))
            for src, dst in SEED_MERGES.items():
                con.execute("UPDATE employees SET merged_into = ? WHERE employee_no = ?", (dst, src))
            con.execute("INSERT INTO audit_log (action, entity, after, created_at) VALUES ('seed', 'employees', ?, CURRENT_TIMESTAMP)",
                        (json.dumps({"roles": SEED_ROLES, "merges": SEED_MERGES}),))
        if superadmin_id:
            con.execute("UPDATE app_users SET level = 'admin' WHERE level = 'superadmin' AND telegram_user_id != ?", (superadmin_id,))
            cur = con.execute("INSERT OR IGNORE INTO app_users (telegram_user_id, name, level, is_responsible, created_at) "
                              "VALUES (?, 'Super admin', 'superadmin', 1, CURRENT_TIMESTAMP)", (superadmin_id,))
            if cur.rowcount:
                new_admins.append(superadmin_id)
            else:
                con.execute("UPDATE app_users SET level = 'superadmin' WHERE telegram_user_id = ?", (superadmin_id,))
        for uid in admin_ids:
            if uid == superadmin_id:
                continue
            cur = con.execute("INSERT OR IGNORE INTO app_users (telegram_user_id, name, level, is_responsible, created_at) "
                              "VALUES (?, 'Admin', 'admin', 1, CURRENT_TIMESTAMP)", (uid,))
            if cur.rowcount:
                new_admins.append(uid)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return new_admins


async def get_settings() -> dict[str, str]:
    rows = await database.fetch_all(select(settings))
    out = dict(SETTING_DEFAULTS)
    out.update({r["key"]: r["value"] for r in rows})
    return out


@dataclass
class Context:
    employees: dict[str, dict]
    roles: dict[str, RoleParams]
    role_names: dict[str, str]
    role_periods: dict[str, list[tuple[str, Optional[str], str]]]  # emp -> [(from, to, role)]
    corrections: dict[str, dict[date, list[Correction]]]
    resolutions: dict[str, dict[datetime, tuple[str, bool]]]
    auto_guards: set[str]

    def role_is_auto(self, emp: str, d: date) -> bool:
        ds = d.isoformat()
        explicit = any(frm <= ds and (to is None or ds <= to) for frm, to, _ in self.role_periods.get(emp, []))
        return not explicit and emp in self.auto_guards

    def canonical(self, emp: str) -> str:
        seen = set()
        while emp in self.employees and self.employees[emp].get("merged_into") and emp not in seen:
            seen.add(emp)
            emp = self.employees[emp]["merged_into"]
        return emp

    def role_code_at(self, emp: str, d: date) -> str:
        ds = d.isoformat()
        for frm, to, role in self.role_periods.get(emp, []):
            if frm <= ds and (to is None or ds <= to):
                return role
        return "qorovul" if emp in self.auto_guards else "standart"

    def role_at(self, emp: str):
        def f(d: date) -> RoleParams:
            return self.roles.get(self.role_code_at(emp, d), self.roles["standart"])
        return f


async def load_context() -> Context:
    emps = {r["employee_no"]: dict(r) for r in await database.fetch_all(select(employees))}
    role_rows = await database.fetch_all(select(roles))
    rps = {r["code"]: RoleParams.from_dict(r["code"], json.loads(r["params"])) for r in role_rows}
    names = {r["code"]: r["name"] for r in role_rows}
    if "standart" not in rps:
        rps["standart"] = RoleParams()
    periods: dict[str, list] = {}
    for r in await database.fetch_all(select(employee_roles).order_by(employee_roles.c.valid_from.desc(), employee_roles.c.id.desc())):
        periods.setdefault(r["employee_no"], []).append((r["valid_from"], r["valid_to"], r["role"]))
    corr: dict[str, dict[date, list[Correction]]] = {}
    for r in await database.fetch_all(select(corrections).where(corrections.c.active == 1).order_by(corrections.c.id)):
        corr.setdefault(r["employee_no"], {}).setdefault(date.fromisoformat(r["work_date"]), []).append(
            Correction(r["field"], r["value"], r["note"] or ""))
    res: dict[str, dict] = {}
    for r in await database.fetch_all(select(resolutions)):
        res.setdefault(r["employee_no"], {})[r["shift_start"]] = (r["shift_type"], bool(r["confirmed"]))
    ctx = Context(emps, rps, names, periods, corr, res, set())
    ctx.auto_guards = await detect_guards(ctx)
    return ctx


_GUARD_CACHE: dict = {"at": None, "value": set()}


async def detect_guards(ctx: "Context") -> set[str]:
    """Oxirgi 28 kundagi smena naqshi bo'yicha qorovullarni aniqlaydi (10 daqiqa kesh)."""
    now = now_local()
    if _GUARD_CACHE["at"] and (now - _GUARD_CACHE["at"]).total_seconds() < 600:
        return _GUARD_CACHE["value"]
    if (await get_settings()).get("auto_guard_detect", "0") != "1":
        _GUARD_CACHE.update(at=now, value=set())
        return set()
    from davomat.engine import guard_shift_count
    s = await get_settings()
    day_start, night_start = (datetime.strptime(s[k], "%H:%M").time() for k in ("guard_day_start", "guard_night_start"))
    punches = await load_punches(ctx, now - timedelta(days=GUARD_LOOKBACK_DAYS), now)
    found = set()
    for emp, ps in punches.items():
        n, days = guard_shift_count([p for p in ps if p.source == "faceid"], day_start, night_start, GUARD_TOL_H)
        if n >= GUARD_MIN_SHIFTS and days and n / days >= GUARD_MIN_RATIO:
            found.add(emp)
    _GUARD_CACHE.update(at=now, value=found)
    return found


def reset_guard_cache():
    _GUARD_CACHE["at"] = None


async def load_punches(ctx: Context, start: datetime, end: datetime, only: Optional[str] = None) -> dict[str, list[Punch]]:
    out: dict[str, list[Punch]] = {}
    q = select(events.c.id, events.c.employee_no, events.c.gate, events.c.event_time).where(and_(
        events.c.matched == 1, events.c.employee_no.isnot(None),
        events.c.event_time >= start, events.c.event_time < end))
    for r in await database.fetch_all(q):
        emp = ctx.canonical(r["employee_no"])
        if only and emp != only:
            continue
        out.setdefault(emp, []).append(Punch(r["event_time"], IN if r["gate"] == "kirish" else OUT, "faceid", f"e:{r['id']}"))
    q = select(checkins).where(and_(checkins.c.ts >= start, checkins.c.ts < end))
    for r in await database.fetch_all(q):
        emp = ctx.canonical(r["employee_no"])
        if only and emp != only:
            continue
        out.setdefault(emp, []).append(Punch(r["ts"], r["direction"], "telegram", f"c:{r['id']}", bool(r["outside"])))
    return out


async def compute_range(d_from: date, d_to: date, only: Optional[str] = None, ctx: Optional[Context] = None) -> tuple[Context, list[Shift]]:
    """[d_from, d_to] oralig'idagi smena sanalari uchun barcha smenalar."""
    ctx = ctx or await load_context()
    start = datetime.combine(d_from - timedelta(days=1), datetime.min.time())
    end = datetime.combine(d_to + timedelta(days=2), datetime.min.time()) + timedelta(hours=12)
    punches = await load_punches(ctx, start, end, only)
    now = now_local()
    shifts: list[Shift] = []
    for emp, ps in punches.items():
        info = ctx.employees.get(emp)
        if info is not None and not info.get("active", 1):
            continue
        for sh in compute_with_roles(emp, ps, ctx.role_at(emp), now, ctx.corrections.get(emp), ctx.resolutions.get(emp)):
            if d_from <= sh.work_date <= d_to:
                shifts.append(sh)
    shifts.sort(key=lambda s: (s.work_date, name_of(ctx, s.employee_no)))
    return ctx, shifts


def name_of(ctx: Context, emp: str) -> str:
    e = ctx.employees.get(emp)
    return e["full_name"] if e else f"ID {emp}"


def _t(ts: Optional[datetime]) -> Optional[str]:
    return ts.strftime("%Y-%m-%d %H:%M:%S") if ts else None


def shift_to_dict(ctx: Context, sh: Shift, detail: bool = False) -> dict:
    d = {
        "employee_no": sh.employee_no,
        "name": name_of(ctx, sh.employee_no),
        "work_date": sh.work_date.isoformat(),
        "role": sh.role,
        "role_name": ctx.role_names.get(sh.role, sh.role),
        "shift_type": sh.shift_type,
        "kirish": _t(sh.kirish),
        "chiqish": _t(sh.chiqish),
        "span_sec": sh.span_sec,
        "inside_sec": sh.inside_sec,
        "outside_sec": sh.outside_sec,
        "status": sh.status,
        "flags": sorted(set(sh.flags)),
        "merged_count": len(sh.merged),
        "sources": sorted({p.source for p in sh.punches}),
    }
    if detail:
        timeline = [{"ts": _t(p.ts), "direction": p.direction, "source": p.source, "ref": p.ref,
                     "outside": p.outside, "merged": False} for p in sh.punches]
        timeline += [{"ts": _t(p.ts), "direction": p.direction, "source": p.source, "ref": p.ref,
                      "outside": p.outside, "merged": True} for p in sh.merged]
        d["timeline"] = sorted(timeline, key=lambda x: x["ts"])
    return d


async def save_resolution(employee_no: str, shift_start: datetime, shift_type: str, actor_id: Optional[int], confirmed: bool = True):
    if shift_type not in ("kunduzgi", "tungi"):
        raise ValueError("smena turi: kunduzgi yoki tungi")
    before = await database.fetch_one(select(resolutions).where(and_(
        resolutions.c.employee_no == employee_no, resolutions.c.shift_start == shift_start)))
    vals = {"shift_type": shift_type, "confirmed": 1 if confirmed else 0, "created_by": actor_id, "created_at": datetime.utcnow()}
    if before:
        await database.execute(resolutions.update().where(resolutions.c.id == before["id"]).values(**vals))
    else:
        await database.execute(resolutions.insert().values(employee_no=employee_no, shift_start=shift_start, **vals))
    await audit(actor_id, "resolve", "guard_shift", f"{employee_no}@{shift_start}", dict(before) if before else None, vals)


CHAT_LOC_STATIC_MAX = timedelta(minutes=3)
CHAT_LOC_LIVE_STALE = timedelta(minutes=10)
OPEN_CHECKIN_MAX = timedelta(hours=16)


async def save_chat_location(uid: int, lat: float, lon: float, acc, live_until, now_utc: datetime) -> None:
    vals = {"lat": lat, "lon": lon, "accuracy": acc, "live_until": live_until, "updated_at": now_utc}
    if await database.fetch_one(select(tg_locations).where(tg_locations.c.telegram_user_id == uid)):
        await database.execute(tg_locations.update().where(tg_locations.c.telegram_user_id == uid).values(**vals))
    else:
        await database.execute(tg_locations.insert().values(telegram_user_id=uid, **vals))


async def fresh_chat_location(uid: int) -> Optional[dict]:
    """Chatdagi joylashuv hali yaroqlimi: oddiy — 3 daqiqa, jonli — ulashish davom etsa va 10 daqiqada yangilangan bo'lsa."""
    r = await database.fetch_one(select(tg_locations).where(tg_locations.c.telegram_user_id == uid))
    if not r:
        return None
    now = datetime.utcnow()
    if r["live_until"]:
        ok = r["live_until"] > now and now - r["updated_at"] <= CHAT_LOC_LIVE_STALE
    else:
        ok = now - r["updated_at"] <= CHAT_LOC_STATIC_MAX
    if not ok:
        return None
    return {"lat": r["lat"], "lon": r["lon"], "accuracy": r["accuracy"], "live": bool(r["live_until"]),
            "age_sec": int((now - r["updated_at"]).total_seconds())}


async def checkin_permissions(employee_no: str) -> dict:
    """Ishni boshlamasdan tugatib bo'lmaydi; boshlangan ishni tugatmasdan qayta boshlab bo'lmaydi.
    16 soatdan eski ochiq "boshladim" yopilmagan hisoblanadi va yangi ish boshlashga to'sqinlik qilmaydi."""
    last = await database.fetch_one(select(checkins).where(checkins.c.employee_no == employee_no)
                                    .order_by(checkins.c.ts.desc()).limit(1))
    open_ = bool(last and last["direction"] == "in" and now_local() - last["ts"] <= OPEN_CHECKIN_MAX)
    return {"open": open_, "can_in": not open_, "can_out": open_,
            "last": {"direction": last["direction"], "ts": last["ts"].strftime("%Y-%m-%d %H:%M:%S")} if last else None}


async def rights_of(uid: int) -> dict:
    u = await database.fetch_one(select(app_users).where(app_users.c.telegram_user_id == uid))
    e = await database.fetch_one(select(employees).where(employees.c.telegram_user_id == uid))
    return {
        "level": u["level"] if u else None,
        "name": (e["full_name"] if e else None) or (u["name"] if u else None) or "",
        "employee_no": e["employee_no"] if e and e["active"] else None,
        "employee_name": e["full_name"] if e else None,
    }


def _slug(name: str) -> str:
    base = "".join(ch if ch.isascii() and ch.isalnum() else " " for ch in (name or "").lower().replace("'", ""))
    parts = base.split()
    return ".".join(parts[:2])[:24]


async def _unique_login(base: str, uid: int) -> str:
    base = base or f"user{uid}"
    login, n = base, 1
    while await database.fetch_one(select(web_credentials).where(web_credentials.c.login == login)):
        n += 1
        login = f"{base}{n}"
    return login


async def issue_credentials(uid: int, name: str, reset: bool = False) -> tuple[str, Optional[str]]:
    """Login/parol yaratadi (yoki reset=True bo'lsa parolni yangilaydi). Parol faqat shu yerda ochiq ko'rinadi."""
    from davomat.auth import generate_password, hash_password
    existing = await database.fetch_one(select(web_credentials).where(web_credentials.c.telegram_user_id == uid))
    if existing and not reset:
        return existing["login"], None
    password = generate_password()
    if existing:
        await database.execute(web_credentials.update().where(web_credentials.c.telegram_user_id == uid)
                               .values(password_hash=hash_password(password), updated_at=datetime.utcnow()))
        return existing["login"], password
    login = await _unique_login(_slug(name), uid)
    await database.execute(web_credentials.insert().values(
        telegram_user_id=uid, login=login, password_hash=hash_password(password),
        created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
    return login, password


async def drop_credentials_if_orphan(uid: int):
    r = await rights_of(uid)
    if not r["level"] and not r["employee_no"]:
        await database.execute(web_credentials.delete().where(web_credentials.c.telegram_user_id == uid))


def main_keyboard(rights: dict) -> Optional[dict]:
    """Huquqqa mos doimiy klaviatura (WebApp tugmalari faqat HTTPS bilan ishlaydi)."""
    if not PUBLIC_BASE_URL:
        return None
    base = f"{PUBLIC_BASE_URL}/davomat"
    rows = []
    if rights.get("employee_no"):
        rows.append([{"text": "▶️ Ishni boshladim", "web_app": {"url": f"{base}/checkin?dir=in"}},
                     {"text": "⏹ Ishni tugatdim", "web_app": {"url": f"{base}/checkin?dir=out"}}])
    if rights.get("level") in ("admin", "superadmin"):
        rows.append([{"text": "📊 Hisobot", "web_app": {"url": f"{base}/"}}])
    if rights.get("employee_no"):
        rows.append([{"text": "📋 Mening davomatim", "web_app": {"url": f"{base}/#/my"}}])
    if not rows:
        return {"remove_keyboard": True}
    return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}


def rights_text(rights: dict) -> str:
    parts = []
    if rights.get("employee_no"):
        parts.append(f"xodim: <b>{html.escape(rights['employee_name'] or '')}</b> (o'z keldi-ketdingizni ko'rasiz, ishni boshlash/tugatish)")
    if rights.get("level") == "superadmin":
        parts.append("👑 super admin (hamma narsa, admin berish)")
    elif rights.get("level") == "admin":
        parts.append("🛠 admin (barcha xodimlarning keldi-ketdisi, tuzatish)")
    return "\n• ".join([""] + parts) if parts else " yo'q"


def _creds_key(uid: int) -> str:
    return f"creds_delivered:{uid}"


async def credentials_delivered(uid: int) -> bool:
    return bool(await database.fetch_one(select(notifications).where(notifications.c.key == _creds_key(uid))))


async def _set_creds_delivered(uid: int, delivered: bool) -> None:
    await database.execute(notifications.delete().where(notifications.c.key == _creds_key(uid)))
    if delivered:
        await database.execute(notifications.insert().values(
            key=_creds_key(uid), kind="creds", status="resolved", created_at=datetime.utcnow()))


async def notify_linked(uid: int, reset: bool = False) -> bool:
    """Biriktirilganda (yoki parol qayta berilganda) foydalanuvchining Telegramiga xabar.
    Yetib borganmi — qaytaradi va eslab qoladi: foydalanuvchi botga hali /start yozmagan
    bo'lsa xabar yetmaydi, keyin /start yozganda parol avtomatik qayta yuboriladi."""
    import telegram
    rights = await rights_of(uid)
    login, password = await issue_credentials(uid, rights["name"], reset=reset)
    web = f"{PUBLIC_BASE_URL}/davomat/" if PUBLIC_BASE_URL else "/davomat/"
    head = "🔑 Parolingiz yangilandi." if reset else "✅ Siz biriktirildingiz."
    text = f"{head}\n\nHuquqlaringiz:{rights_text(rights)}"
    if password:
        text += (f"\n\n🌐 Web orqali kirish: {web}\nLogin: <code>{html.escape(login)}</code>\n"
                 f"Parol: <code>{html.escape(password)}</code>\n\nKirgandan keyin «Profil» bo'limida login va parolni o'zgartiring."
                 f"\nParolni unutsangiz — botga /parol yozing.")
    else:
        text += f"\n\n🌐 Web: {web}\nLogin: <code>{html.escape(login)}</code> (parol avvalgidek, unutgan bo'lsangiz — /parol)"
    res = await telegram.send_to(uid, text, main_keyboard(rights))
    delivered = bool(res and res.get("ok"))
    if password:
        await _set_creds_delivered(uid, delivered)
    return delivered


async def notify_unlinked(uid: int) -> None:
    import telegram
    await telegram.send_to(uid, "Sizning Telegram hisobingiz tizimdan uzildi. Savollar bo'lsa, rahbaringizga murojaat qiling.",
                           {"remove_keyboard": True})


async def user_level(telegram_user_id: int) -> Optional[str]:
    r = await database.fetch_one(select(app_users).where(app_users.c.telegram_user_id == telegram_user_id))
    return r["level"] if r else None

