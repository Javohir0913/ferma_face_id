# -*- coding: utf-8 -*-
"""Ферма — описание таблиц (databases + SQLAlchemy core). Работает с SQLite (локальный тест) и PostgreSQL (Docker)."""
import datetime

from sqlalchemy import (
    BigInteger,
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

IS_SQLITE = DATABASE_URL.startswith("sqlite")
database = Database(DATABASE_URL)


def sync_url() -> str:
    """Адрес синхронного драйвера для create_all/seed."""
    if IS_SQLITE:
        return DATABASE_URL.replace("+aiosqlite", "")
    return "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]
metadata = MetaData()

events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("gate", String, nullable=False),               # "kirish" | "chiqish"
    Column("event_type", String, nullable=True),
    Column("person_name", String, nullable=True),
    Column("employee_no", String, nullable=True),
    Column("serial_no", String, nullable=True),            # собственный serialNo камеры
    Column("matched", Integer, default=0),                 # 1 = распознан, 0 = не распознан
    Column("confidence", Float, nullable=True),
    Column("snapshot_path", String, nullable=True),
    Column("event_time", DateTime, nullable=True),
    Column("raw_data", Text, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

# Если от одной камеры (gate) один и тот же serialNo пришёл дважды — это повторный
# push (проблема сети/ACK), UNIQUE-индекс его блокирует. Разные gate
# (вход/выход) считаются независимыми, поэтому индекс по паре (gate,
# serial_no). В SQLite и PostgreSQL значения NULL в UNIQUE-индексе
# не конфликтуют между собой, поэтому записям с пустым serial_no
# (например, отладочным строкам parse-fail) это ограничение не мешает.
Index("idx_events_gate_serial", events.c.gate, events.c.serial_no, unique=True)
# create_all не добавляет индекс в существующую таблицу — он создаётся отдельно в create_all().
idx_events_emp_time = Index("idx_events_emp_time", events.c.employee_no, events.c.event_time)


# ----------------------------- Слой посещаемости -----------------------------
# Сырые `events` никогда не изменяются. Расчёт каждый раз выполняется заново
# на основе этих таблиц + events + checkins.

employees = Table(
    "employees",
    metadata,
    Column("employee_no", String, primary_key=True),
    Column("full_name", String, nullable=False),
    Column("telegram_user_id", BigInteger, nullable=True, unique=True),
    # Если человек зарегистрирован в камере под двумя ID — привязывается к основному ID.
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
    Column("valid_to", String, nullable=True),     # YYYY-MM-DD, NULL = по сей день
    Column("created_by", BigInteger, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

checkins = Table(
    "checkins",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("employee_no", String, nullable=False, index=True),
    Column("telegram_user_id", BigInteger, nullable=False),
    Column("direction", String, nullable=False),  # "in" | "out"
    Column("ts", DateTime, nullable=False),        # время сервера, Ташкент
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
    Column("work_date", String, nullable=False),  # YYYY-MM-DD (дата смены)
    Column("field", String, nullable=False),      # "kirish" | "chiqish"
    Column("value", DateTime, nullable=True),
    Column("note", Text, nullable=True),
    Column("active", Integer, default=1),
    Column("created_by", BigInteger, nullable=False),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

# Решение, принятое, когда тип смены охранника не был определён.
resolutions = Table(
    "resolutions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("employee_no", String, nullable=False),
    Column("shift_start", DateTime, nullable=False),
    Column("shift_type", String, nullable=False),  # "kunduzgi" | "tungi"
    Column("confirmed", Integer, default=1),       # 0 = система выбрала сама (не подтверждено)
    Column("created_by", BigInteger, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)
Index("idx_resolutions_emp_start", resolutions.c.employee_no, resolutions.c.shift_start, unique=True)

app_users = Table(
    "app_users",
    metadata,
    Column("telegram_user_id", BigInteger, primary_key=True, autoincrement=False),
    Column("name", String, nullable=True),
    Column("level", String, nullable=False),         # "viewer" | "admin"
    Column("is_responsible", Integer, default=0),   # получает сообщения об исключениях
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("actor_id", BigInteger, nullable=True),
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
    Column("telegram_user_id", BigInteger, primary_key=True, autoincrement=False),
    Column("username", String, nullable=True),
    Column("full_name", String, nullable=True),
    Column("status", String, default="pending"),  # pending | linked | rejected
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)

# Последняя геопозиция, отправленная в чат бота (включая обновления трансляции) —
# если GPS не работает внутри Mini App, check-in использует эту геопозицию.
tg_locations = Table(
    "tg_locations",
    metadata,
    Column("telegram_user_id", BigInteger, primary_key=True, autoincrement=False),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    Column("accuracy", Float, nullable=True),
    Column("live_until", DateTime, nullable=True),  # UTC; NULL, если не трансляция
    Column("updated_at", DateTime, nullable=False),  # UTC
)

# Логин/пароль для Web. Привязан к аккаунту Telegram (1 Telegram = 1 пользователь).
web_credentials = Table(
    "web_credentials",
    metadata,
    Column("telegram_user_id", BigInteger, primary_key=True, autoincrement=False),
    Column("login", String, nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.datetime.utcnow),
)

# Сообщения бота об исключениях — чтобы не отправлять повторно и напоминать.
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
    Column("resolved_by", BigInteger, nullable=True),
    Column("resolved_at", DateTime, nullable=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow),
)


def create_all():
    """Создаёт таблицы (если их нет). Вызывается при запуске main.py и бота."""
    engine = create_engine(sync_url(), future=True)
    try:
        with engine.begin() as conn:
            if not IS_SQLITE:
                # На пустой базе 2 воркера gunicorn не должны одновременно создавать таблицы — один ждёт.
                conn.exec_driver_sql("SELECT pg_advisory_xact_lock(4242002)")
            metadata.create_all(conn)
            idx_events_emp_time.create(conn, checkfirst=True)
            # Суперадмин может быть только один — гарантия на уровне базы.
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ux_one_superadmin ON app_users(level) WHERE level = 'superadmin'")
    finally:
        engine.dispose()
