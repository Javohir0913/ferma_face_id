# -*- coding: utf-8 -*-
"""Ferma — SQLite jadval ta'rifi (databases + SQLAlchemy core)."""
import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from databases import Database

from config import DATABASE_URL

database = Database(DATABASE_URL)
metadata = MetaData()

events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("gate", String, nullable=False),               # "kirish" | "chiqish"
    Column("event_type", String, nullable=True),
    Column("person_name", String, nullable=True),
    Column("employee_no", String, nullable=True),
    Column("serial_no", String, nullable=True),            # kameraning o'z serialNo'si
    Column("matched", Integer, default=0),                 # 1 = tanildi, 0 = tanilmadi
    Column("confidence", Float, nullable=True),
    Column("snapshot_path", String, nullable=True),
    Column("event_time", DateTime, nullable=True),
    Column("raw_data", Text, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

# Bir xil kameradan (gate) bir xil serialNo ikki marta kelsa — bu takroriy
# push (tarmoq/ACK muammosi), UNIQUE index buni bloklaydi. Ikki xil gate
# (kirish/chiqish) o'z-o'zicha mustaqil sanaladi, shuning uchun (gate,
# serial_no) juftligi bo'yicha. SQLite'da UNIQUE composite indexda NULL
# qiymatlar bir-biriga to'qnashmaydi, shuning uchun serial_no bo'sh bo'lgan
# yozuvlarga (masalan parse-fail debug qatorlariga) bu cheklov xalaqit bermaydi.
Index("idx_events_gate_serial", events.c.gate, events.c.serial_no, unique=True)
# Mavjud jadvalga create_all index qo'shmaydi — create_all() ichida alohida yaratiladi.
idx_events_emp_time = Index("idx_events_emp_time", events.c.employee_no, events.c.event_time)


# ----------------------------- Davomat qatlami -----------------------------
# Xom `events` hech qachon o'zgartirilmaydi. Hisob har safar shu jadvallar +
# events + checkins asosida qayta hisoblanadi.

employees = Table(
    "employees",
    metadata,
    Column("employee_no", String, primary_key=True),
    Column("full_name", String, nullable=False),
    Column("telegram_user_id", Integer, nullable=True, unique=True),
    # Kamerada bitta odam ikki ID bilan ro'yxatda bo'lsa — asosiy ID'ga ulanadi.
    Column("merged_into", String, nullable=True),
    Column("active", Integer, default=1),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

roles = Table(
    "roles",
    metadata,
    Column("code", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("params", Text, nullable=False),  # JSON
)

employee_roles = Table(
    "employee_roles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("employee_no", String, nullable=False, index=True),
    Column("role", String, nullable=False),
    Column("valid_from", String, nullable=False),  # YYYY-MM-DD
    Column("valid_to", String, nullable=True),     # YYYY-MM-DD, NULL = hozirgacha
    Column("created_by", Integer, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

checkins = Table(
    "checkins",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("employee_no", String, nullable=False, index=True),
    Column("telegram_user_id", Integer, nullable=False),
    Column("direction", String, nullable=False),  # "in" | "out"
    Column("ts", DateTime, nullable=False),        # server vaqti, Toshkent
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    Column("accuracy", Float, nullable=True),
    Column("distance_m", Float, nullable=True),
    Column("outside", Integer, default=0),
    Column("photo_path", String, nullable=False),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

corrections = Table(
    "corrections",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("employee_no", String, nullable=False, index=True),
    Column("work_date", String, nullable=False),  # YYYY-MM-DD (smena sanasi)
    Column("field", String, nullable=False),      # "kirish" | "chiqish"
    Column("value", DateTime, nullable=True),
    Column("note", Text, nullable=True),
    Column("active", Integer, default=1),
    Column("created_by", Integer, nullable=False),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

# Qorovul smenasi turi aniqlanmaganda qabul qilingan qaror.
resolutions = Table(
    "resolutions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("employee_no", String, nullable=False),
    Column("shift_start", DateTime, nullable=False),
    Column("shift_type", String, nullable=False),  # "kunduzgi" | "tungi"
    Column("confirmed", Integer, default=1),       # 0 = tizim o'zi tanladi (tasdiqlanmagan)
    Column("created_by", Integer, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)
Index("idx_resolutions_emp_start", resolutions.c.employee_no, resolutions.c.shift_start, unique=True)

app_users = Table(
    "app_users",
    metadata,
    Column("telegram_user_id", Integer, primary_key=True),
    Column("name", String, nullable=True),
    Column("level", String, nullable=False),         # "viewer" | "admin"
    Column("is_responsible", Integer, default=0),   # istisno xabarlarini oladi
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("actor_id", Integer, nullable=True),
    Column("action", String, nullable=False),
    Column("entity", String, nullable=False),
    Column("entity_id", String, nullable=True),
    Column("before", Text, nullable=True),
    Column("after", Text, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

settings = Table(
    "settings",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", Text, nullable=False),
)

tg_link_requests = Table(
    "tg_link_requests",
    metadata,
    Column("telegram_user_id", Integer, primary_key=True),
    Column("username", String, nullable=True),
    Column("full_name", String, nullable=True),
    Column("status", String, default="pending"),  # pending | linked | rejected
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

# Bot chatida yuborilgan oxirgi joylashuv (jonli joylashuv yangilanishlari ham) —
# Mini App ichida GPS ishlamasa, check-in shu joylashuvdan foydalanadi.
tg_locations = Table(
    "tg_locations",
    metadata,
    Column("telegram_user_id", Integer, primary_key=True),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    Column("accuracy", Float, nullable=True),
    Column("live_until", DateTime, nullable=True),  # UTC; jonli bo'lmasa NULL
    Column("updated_at", DateTime, nullable=False),  # UTC
)

# Web uchun login/parol. Telegram hisobiga bog'lanadi (1 Telegram = 1 foydalanuvchi).
web_credentials = Table(
    "web_credentials",
    metadata,
    Column("telegram_user_id", Integer, primary_key=True),
    Column("login", String, nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.datetime.utcnow),
)

# Bot yuborgan istisno xabarlari — takror yubormaslik va eslatma uchun.
notifications = Table(
    "notifications",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("key", String, nullable=False, unique=True),
    Column("kind", String, nullable=False),
    Column("payload", Text, nullable=True),
    Column("status", String, default="open"),  # open | resolved | auto
    Column("remind_count", Integer, default=0),
    Column("last_sent_at", DateTime, nullable=True),
    Column("resolved_by", Integer, nullable=True),
    Column("resolved_at", DateTime, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)


def create_all():
    """Jadval(lar)ni (agar mavjud bo'lmasa) yaratadi. main.py startup'da chaqiradi."""
    sync_url = DATABASE_URL.replace("+aiosqlite", "")
    engine = create_engine(sync_url, future=True)
    metadata.create_all(engine)
    idx_events_emp_time.create(engine, checkfirst=True)
    with engine.begin() as conn:
        # Super admin faqat bitta bo'lishi mumkin — baza darajasida kafolat.
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ux_one_superadmin ON app_users(level) WHERE level = 'superadmin'")
    engine.dispose()
