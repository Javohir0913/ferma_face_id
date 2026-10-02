# -*- coding: utf-8 -*-
"""SQLite bazani (data/app.db nusxasi) PostgreSQL'ga ko'chiradi.

    python tools/sqlite_to_postgres.py <sqlite fayl> <postgresql+asyncpg://user:pass@host:port/db>

- SQLite fayl faqat o'qiladi (mode=ro).
- Maqsad bazada ma'lumot bo'lsa to'xtaydi (ustidan yozib yubormaslik uchun).
- Barcha jadvallar id'lari bilan ko'chiriladi, keyin sequence'lar to'g'rilanadi.
- Oxirida har bir jadvalning qatorlar soni va events uchun nazorat summasi solishtiriladi.
"""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src_path, target = sys.argv[1], sys.argv[2]
    if not Path(src_path).is_file():
        sys.exit(f"SQLite fayl topilmadi: {src_path}")
    if not target.startswith("postgresql"):
        sys.exit("Maqsad PostgreSQL manzili bo'lishi kerak")
    os.environ["DATABASE_URL"] = target

    from sqlalchemy import Integer, create_engine, func, inspect, select, text
    import database
    from database import create_all, metadata, sync_url

    src = create_engine(f"sqlite:///file:{Path(src_path).as_posix()}?mode=ro&uri=true")
    dst = create_engine(sync_url())

    # Manbadagi jadval/ustunlar sxemaga mosligini tekshirish — hech narsa jim tashlab ketilmasin.
    insp = inspect(src)
    src_tables = set(insp.get_table_names())
    unknown = src_tables - set(metadata.tables)
    if unknown:
        sys.exit(f"Manbada sxemada yo'q jadvallar bor: {sorted(unknown)}")
    for name in src_tables:
        extra = {c["name"] for c in insp.get_columns(name)} - set(metadata.tables[name].c.keys())
        if extra:
            sys.exit(f"{name}: sxemada yo'q ustunlar: {sorted(extra)}")

    create_all()
    with dst.connect() as con:
        busy = {t.name: n for t in metadata.sorted_tables
                if (n := con.execute(select(func.count()).select_from(t)).scalar())}
    if busy:
        sys.exit(f"Maqsad bazada allaqachon ma'lumot bor: {busy} — bo'sh bazaga ko'chiring")

    counts = {}
    with src.connect() as s, dst.begin() as d:
        for t in metadata.sorted_tables:
            if t.name not in src_tables:
                print(f"  {t.name:18} manbada yo'q — o'tkazib yuborildi")
                continue
            rows = [dict(r._mapping) for r in s.execute(select(t))]
            for i in range(0, len(rows), 1000):
                d.execute(t.insert(), rows[i:i + 1000])
            counts[t.name] = len(rows)
            # id SERIAL bo'lsa — keyingi yangi yozuv to'qnashmasligi uchun sequence'ni oxirgi id'ga qo'yamiz.
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and isinstance(pk[0].type, Integer) and pk[0].autoincrement is not False:
                seq = d.execute(text("SELECT pg_get_serial_sequence(:t, :c)"), {"t": t.name, "c": pk[0].name}).scalar()
                if seq:
                    d.execute(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX({pk[0].name}) FROM {t.name}), 0) + 1, false)"))
            print(f"  {t.name:18} {len(rows):>7} qator")

    # Tekshiruv: qatorlar soni va events nazorat summasi.
    def digest(engine):
        h = hashlib.sha256()
        with engine.connect() as c:
            for r in c.execute(select(database.events).order_by(database.events.c.id)):
                h.update(repr(tuple(r)).encode())
        return h.hexdigest()

    with dst.connect() as c:
        bad = {n: (k, c.execute(select(func.count()).select_from(metadata.tables[n])).scalar())
               for n, k in counts.items()}
    bad = {n: v for n, v in bad.items() if v[0] != v[1]}
    if bad:
        sys.exit(f"XATO: qatorlar soni mos emas: {bad}")
    a, b = digest(src), digest(dst)
    if a != b:
        sys.exit("XATO: events nazorat summasi mos emas")
    print(f"OK — barcha jadvallar mos, events sha256 {a[:16]}…")


if __name__ == "__main__":
    main()
