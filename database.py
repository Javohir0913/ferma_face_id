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


def create_all():
    """Jadval(lar)ni (agar mavjud bo'lmasa) yaratadi. main.py startup'da chaqiradi."""
    sync_url = DATABASE_URL.replace("+aiosqlite", "")
    engine = create_engine(sync_url, future=True)
    metadata.create_all(engine)
