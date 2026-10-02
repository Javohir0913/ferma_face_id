"""Полный сценарий: бот /start -> админ привязывает -> логин/пароль -> права -> check-in -> отчёт -> расписание бота."""
import asyncio
import io
import json
from datetime import date, datetime

import httpx
import pytest

import telegram
from database import create_all, database, events, notifications
from davomat import bot, service
from main import app

SENT: list[tuple] = []


BLOCKED: set[int] = set()  # пользователи, которые ещё не писали боту /start


async def _fake_send_to(chat_id, text, reply_markup=None):
    SENT.append((int(chat_id), text, reply_markup))
    return {"ok": int(chat_id) not in BLOCKED}


async def _fake_notify(text, image_bytes=None, image_name="x.jpg"):
    SENT.append(("group", text, None))


def _jpeg() -> bytes:
    return b"\xff\xd8" + b"\x00" * 20_000 + b"\xff\xd9"


async def _seed_events():
    rows = [
        ("kirish", "00000005", "Ali Valiyev", "2026-09-10 08:00:00", "1"),
        ("chiqish", "00000005", "Ali Valiyev", "2026-09-10 12:00:00", "2"),
        ("kirish", "00000005", "Ali Valiyev", "2026-09-10 13:00:00", "3"),
        ("chiqish", "00000005", "Ali Valiyev", "2026-09-10 18:00:00", "4"),
        ("kirish", "00000020", "Qorovul Karimov", "2026-09-10 14:00:00", "5"),
        ("chiqish", "00000020", "Qorovul Karimov", "2026-09-10 23:00:00", "6"),
    ]
    # Шаблон охранника: чередование 09->21 и 21->09 — система должна сама определить охранника.
    for i in range(8):
        d = [1, 2, 4, 5, 7, 8, 9, 11][i]
        if i % 2 == 0:
            rows += [("kirish", "00000020", "Qorovul Karimov", f"2026-09-{d:02d} 09:01:00", f"g{i}a"),
                     ("chiqish", "00000020", "Qorovul Karimov", f"2026-09-{d:02d} 21:02:00", f"g{i}b")]
        else:
            rows += [("kirish", "00000020", "Qorovul Karimov", f"2026-09-{d:02d} 20:58:00", f"g{i}a"),
                     ("chiqish", "00000020", "Qorovul Karimov", f"2026-09-{d + 1:02d} 09:04:00", f"g{i}b")]
    rows += [
        ("kirish", "00000007", "Dala Ishchisi", "2026-09-10 07:30:00", "7"),
    ]
    for gate, emp, name, t, sn in rows:
        await database.execute(events.insert().values(
            gate=gate, event_type="AccessControllerEvent", person_name=name, employee_no=emp, serial_no=sn,
            matched=1, event_time=datetime.fromisoformat(t), raw_data="{}", created_at=datetime.utcnow()))


@pytest.fixture(scope="module")
def env():
    mp = pytest.MonkeyPatch()
    mp.setattr(telegram, "send_to", _fake_send_to)
    mp.setattr(telegram, "send_rich", _fake_send_to)
    mp.setattr(telegram, "notify", _fake_notify)
    create_all()
    loop = asyncio.new_event_loop()
    loop.run_until_complete(database.connect())
    loop.run_until_complete(_seed_events())
    service.seed_sync([], 900)
    yield loop
    loop.run_until_complete(database.disconnect())
    loop.close()
    mp.undo()


def run(loop, coro):
    return loop.run_until_complete(coro)


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _dev_token(c, uid):
    # В тесте DEV_LOGIN выключен — токен создаётся напрямую (проверка initData — в test_auth.py).
    from davomat.auth import make_token
    return {"Authorization": f"Bearer {make_token(uid, 'T')}"}


def test_full_flow(env):
    loop = env
    SENT.clear()

    # 1) Непривязанный человек нажимает /start.
    run(loop, database.execute("UPDATE settings SET value='901' WHERE key='link_admin_id'"))
    run(loop, bot.handle_update({"update_id": 1, "message": {"chat": {"type": "private", "id": 555},
                                  "from": {"id": 555, "first_name": "Dala", "username": "dala1"}, "text": "/start"}}))
    to_user = [m for m in SENT if m[0] == 555]
    to_admin = [m for m in SENT if m[0] == 901]
    assert to_user and "biriktirilmagansiz" in to_user[0][1]
    assert to_admin and "Yangi foydalanuvchi" in to_admin[0][1] and "555" in to_admin[0][1]

    async def scenario():
        async with await _client() as c:
            admin = await _dev_token(c, 900)
            # 2) Непривязанный пользователь не может войти в Mini App.
            r = await c.get("/api/davomat/me", headers=await _dev_token(c, 555))
            assert r.status_code == 200 and r.json()["level"] is None and r.json()["employee_no"] is None
            r = await c.get("/api/davomat/day", headers=await _dev_token(c, 555))
            assert r.status_code == 403
            r = await c.get("/api/davomat/admin/link-requests", headers=admin)
            assert [x["telegram_user_id"] for x in r.json()] == [555]

            # 3) Админ привязывает -> пользователю «вы привязаны» + логин/пароль.
            SENT.clear()
            r = await c.post("/api/davomat/admin/employees/00000007", headers=admin, json={"telegram_user_id": 555})
            assert r.status_code == 200, r.text
            msg = [m for m in SENT if m[0] == 555][-1]
            assert "Siz biriktirildingiz" in msg[1] and "Login:" in msg[1] and "Parol:" in msg[1]
            assert any("Ishni boshladim" in b["text"] for row in msg[2]["keyboard"] for b in row)
            login = msg[1].split("Login: <code>")[1].split("</code>")[0]
            password = msg[1].split("Parol: <code>")[1].split("</code>")[0]

            # 1 Telegram = 1 сотрудник.
            r = await c.post("/api/davomat/admin/employees/00000005", headers=admin, json={"telegram_user_id": 555})
            assert r.status_code == 400

            # 4) Web: вход по логину/паролю; неверный пароль отклоняется.
            assert (await c.post("/api/davomat/auth/password", json={"login": login, "password": "xato"})).status_code == 401
            r = await c.post("/api/davomat/auth/password", json={"login": login, "password": password})
            assert r.status_code == 200, r.text
            emp = {"Authorization": "Bearer " + r.json()["token"]}
            # Обычный сотрудник не видит общий отчёт, видит свой.
            assert (await c.get("/api/davomat/day", headers=emp)).status_code == 403
            r = await c.get("/api/davomat/my?from=2026-09-10&to=2026-09-10", headers=emp)
            assert r.status_code == 200 and r.json()["employee"]["employee_no"] == "00000007"

            # 5) Смена логина/пароля.
            r = await c.post("/api/davomat/auth/change-credentials", headers=emp,
                             json={"current_password": password, "new_login": "dala.ishchi", "new_password": "YangiParol7"})
            assert r.status_code == 200, r.text
            assert (await c.post("/api/davomat/auth/password", json={"login": login, "password": password})).status_code == 401
            r = await c.post("/api/davomat/auth/password", json={"login": "dala.ishchi", "password": "YangiParol7"})
            assert r.status_code == 200
            assert (await c.post("/api/davomat/auth/change-credentials", headers=emp,
                                 json={"current_password": "YangiParol7", "new_password": "123"})).status_code == 400

            # 6) Check-in: низкая точность геопозиции -> отказ; не фото -> отказ; корректный -> принят, вне территории.
            await c.put("/api/davomat/admin/settings", headers=admin, json={"farm_lat": "41.0", "farm_lon": "69.0", "farm_radius_m": "300"})
            form = {"direction": "in", "lat": "41.05", "lon": "69.0"}
            # Нельзя закончить не начатую работу.
            r = await c.post("/api/davomat/checkin", headers=emp, data={**form, "direction": "out", "accuracy": "20"},
                             files={"photo": ("p.jpg", _jpeg(), "image/jpeg")})
            assert r.status_code == 409 and "boshlanmagan" in r.json()["detail"]
            st = (await c.get("/api/davomat/checkin/state", headers=emp)).json()
            assert st["can_in"] and not st["can_out"]
            r = await c.post("/api/davomat/checkin", headers=emp, data={**form, "accuracy": "500"},
                             files={"photo": ("p.jpg", _jpeg(), "image/jpeg")})
            assert r.status_code == 400
            r = await c.post("/api/davomat/checkin", headers=emp, data={**form, "accuracy": "20"},
                             files={"photo": ("p.jpg", b"not an image" * 1000, "image/jpeg")})
            assert r.status_code == 400
            r = await c.post("/api/davomat/checkin", headers=emp, data={**form, "accuracy": "20"},
                             files={"photo": ("p.jpg", _jpeg(), "image/jpeg")})
            assert r.status_code == 200, r.text
            assert r.json()["outside"] is True and 5000 < r.json()["distance_m"] < 6000
            cid = r.json()["id"]
            r = await c.post("/api/davomat/checkin", headers=emp, data={**form, "accuracy": "20"},
                             files={"photo": ("p.jpg", _jpeg(), "image/jpeg")})
            assert r.status_code == 409 and "allaqachon boshlangan" in r.json()["detail"]
            st = (await c.get("/api/davomat/checkin/state", headers=emp)).json()
            assert st["can_out"] and not st["can_in"] and st["chat_location"] is None

            # Если GPS в приложении не работает: трансляция геопозиции в чате бота (координаты от клиента не берутся).
            r = await c.post("/api/davomat/checkin", headers=emp, data={"direction": "out", "loc_source": "chat"},
                             files={"photo": ("p.jpg", _jpeg(), "image/jpeg")})
            assert r.status_code == 400
            await bot.handle_update({"update_id": 50, "message": {"chat": {"type": "private", "id": 555}, "from": {"id": 555},
                                     "date": int(__import__("time").time()),
                                     "location": {"latitude": 41.0, "longitude": 69.0}}})
            assert (await c.get("/api/davomat/checkin/state", headers=emp)).json()["chat_location"] is None  # выбрана на карте — отказ
            await bot.handle_update({"update_id": 51, "message": {"chat": {"type": "private", "id": 555}, "from": {"id": 555},
                                     "date": int(__import__("time").time()),
                                     "location": {"latitude": 41.0, "longitude": 69.0005, "live_period": 900, "horizontal_accuracy": 12}}})
            st = (await c.get("/api/davomat/checkin/state", headers=emp)).json()
            assert st["chat_location"] and st["chat_location"]["live"] is True
            r = await c.post("/api/davomat/checkin", headers=emp, data={"direction": "out", "loc_source": "chat", "lat": "1", "lon": "1"},
                             files={"photo": ("p.jpg", _jpeg(), "image/jpeg")})
            assert r.status_code == 200, r.text
            assert r.json()["outside"] is False  # сервер взял геопозицию из чата (внутри фермы), а не 1,1 от клиента
            assert any(m[0] == "group" and "Ishni boshladi" in m[1] and "tashqarida" in m[1] for m in SENT)

            # Check-in виден в отчёте (источник: telegram, пометка: вне территории).
            today = service.now_local().date().isoformat()
            r = await c.get(f"/api/davomat/day?date={today}", headers=admin)
            row = next(x for x in r.json()["rows"] if x["employee_no"] == "00000007")
            assert "telegram" in row["sources"] and "hududdan tashqarida belgilangan" in row["flags"]
            r = await c.get(f"/api/davomat/checkins?from={today}&to={today}", headers=admin)
            assert {(x["direction"], x["outside"]) for x in r.json()["rows"]} == {("in", True), ("out", False)}
            assert (await c.get(f"/api/davomat/checkins/{cid}/photo", headers=emp)).status_code == 200
            r = await c.get(f"/api/davomat/checkins.xlsx?from={today}&to={today}", headers=admin)
            assert r.status_code == 200 and r.content[:2] == b"PK"

            # 7) Суперадмин выдаёт админа: админ видит других, но не может управлять пользователями.
            SENT.clear()
            r = await c.post("/api/davomat/admin/users", headers=admin, json={"telegram_user_id": 777, "name": "Rahbar", "level": "admin"})
            assert r.status_code == 200
            assert any(m[0] == 777 and "admin" in m[1] for m in SENT)
            rahbar = await _dev_token(c, 777)
            assert (await c.get("/api/davomat/day?date=2026-09-10", headers=rahbar)).status_code == 200
            assert (await c.get("/api/davomat/admin/users", headers=rahbar)).status_code == 403
            # Уровня «viewer» больше нет.
            assert (await c.post("/api/davomat/admin/users", headers=admin, json={"telegram_user_id": 778, "level": "viewer"})).status_code == 400

            # 8) Отвязка: сообщение приходит, после этого войти нельзя.
            SENT.clear()
            await c.post("/api/davomat/admin/employees/00000007", headers=admin, json={"clear_telegram": True})
            assert any(m[0] == 555 and "uzildi" in m[1] for m in SENT)
            assert (await c.post("/api/davomat/auth/password", json={"login": "dala.ishchi", "password": "YangiParol7"})).status_code == 401
            assert (await c.get("/api/davomat/my", headers=emp)).status_code == 403

            # 9) Аудит-лог записан.
            r = await c.get("/api/davomat/admin/audit", headers=admin)
            actions = {a["action"] for a in r.json()}
            assert {"update", "change_credentials", "upsert"} <= actions

    run(loop, scenario())


def test_guard_shift_never_asked(env):
    loop = env
    SENT.clear()
    # 00000020 в начальных данных — охранник; автоопределение охранников выключено.
    service.now_local = lambda: datetime(2026, 9, 11, 9, 0)
    service.reset_guard_cache()
    ctx = run(loop, service.load_context())
    assert not ctx.auto_guards
    assert ctx.role_code_at("00000020", datetime(2026, 9, 10).date()) == "qorovul"
    # Пришёл в 14:00 — теперь не спрашивается, тип смены выбирается сам (ближе к 09:00 -> дневная).
    run(loop, database.execute(notifications.insert().values(key="guard_type:eski", kind="guard_type", status="open",
                                                             created_at=datetime.utcnow())))
    run(loop, bot.job_guard_unknown(datetime(2026, 9, 11, 9, 0), run(loop, service.get_settings())))
    assert not [m for m in SENT if m[2] and "inline_keyboard" in m[2]]
    old = run(loop, database.fetch_one(notifications.select().where(notifications.c.key == "guard_type:eski")))
    assert old["status"] == "auto"  # старый открытый вопрос тихо закрыт
    _, shifts = run(loop, service.compute_range(date(2026, 9, 10), date(2026, 9, 10), only="00000020"))
    s14 = next(s for s in shifts if s.start == datetime(2026, 9, 10, 14, 0))
    assert s14.shift_type == "kunduzgi"


def test_bot_daily_summary_once(env):
    loop = env
    SENT.clear()
    s = run(loop, service.get_settings())
    run(loop, bot.job_daily(datetime(2026, 9, 11, 9, 5), s))
    run(loop, bot.job_daily(datetime(2026, 9, 11, 9, 6), s))
    summaries = [m for m in SENT if m[0] == -100500]
    assert len(summaries) == 1 and "10 sentabr" in summaries[0][1] and "<table" in summaries[0][1]
    assert summaries[0][2]["inline_keyboard"][0][0]["url"].endswith("#/day?date=2026-09-10")


def test_access_levels(env):
    loop = env

    async def scenario():
        async with await _client() as c:
            sup = await _dev_token(c, 900)  # conftest: ADMIN_TELEGRAM_IDS=900 -> первый — суперадмин
            assert (await c.get("/api/davomat/me", headers=sup)).json()["level"] == "superadmin"
            # Суперадмин добавляет админа.
            assert (await c.post("/api/davomat/admin/users", headers=sup, json={"telegram_user_id": 801, "name": "A1", "level": "admin"})).status_code == 200
            assert (await c.post("/api/davomat/admin/users", headers=sup, json={"telegram_user_id": 802, "name": "A2", "level": "admin"})).status_code == 200
            adm = await _dev_token(c, 801)
            # Админ: видит посещаемость других, но не может выдавать/снимать админа и менять настройки.
            assert (await c.get("/api/davomat/day?date=2026-09-10", headers=adm)).status_code == 200
            assert (await c.post("/api/davomat/admin/users", headers=adm, json={"telegram_user_id": 804, "name": "X", "level": "admin"})).status_code == 403
            assert (await c.delete("/api/davomat/admin/users/802", headers=adm)).status_code == 403
            assert (await c.delete("/api/davomat/admin/users/900", headers=sup)).status_code == 400
            assert (await c.put("/api/davomat/admin/settings", headers=adm, json={"farm_radius_m": "500"})).status_code == 403
            assert (await c.put("/api/davomat/admin/roles/standart", headers=adm, json={"params": {"mode": "day"}})).status_code == 403
            assert (await c.post("/api/davomat/admin/users/802/reset-password", headers=adm)).status_code == 403
            # Админ выдаёт рабочую роль (в том числе охранника) и возвращает на «avto».
            assert (await c.post("/api/davomat/admin/employees/00000005/role", headers=adm, json={"role": "soguvchi", "valid_from": "2026-09-01"})).status_code == 200
            ctx = await service.load_context()
            assert ctx.role_code_at("00000005", date(2026, 9, 5)) == "soguvchi"
            assert (await c.post("/api/davomat/admin/employees/00000005/role", headers=adm, json={"role": "avto", "valid_from": "2026-09-10"})).status_code == 200
            ctx = await service.load_context()
            assert ctx.role_code_at("00000005", date(2026, 9, 5)) == "soguvchi"   # старый период не ломается
            assert ctx.role_code_at("00000005", date(2026, 9, 12)) == "standart"
            # Суперадмин только из .env: его нельзя изменить через upsert, эндпоинта передачи нет.
            assert (await c.post("/api/davomat/admin/users", headers=sup, json={"telegram_user_id": 900, "name": "S", "level": "admin"})).status_code == 400
            assert (await c.post("/api/davomat/admin/users/801/make-superadmin", headers=sup)).status_code in (404, 405)
            # Обычный сотрудник (не админ) видит только себя.
            emp_only = await _dev_token(c, 555)
            assert (await c.get("/api/davomat/day", headers=emp_only)).status_code == 403

    run(loop, scenario())
    # И на уровне базы двух суперадминов быть не может.
    from sqlalchemy import create_engine, exc
    from database import sync_url
    engine = create_engine(sync_url())
    with pytest.raises(exc.IntegrityError), engine.begin() as con:
        con.exec_driver_sql("UPDATE app_users SET level='superadmin' WHERE telegram_user_id=802")
    engine.dispose()


def test_credentials_resent_on_start_and_parol(env):
    loop = env
    from davomat import auth

    async def scenario():
        async with await _client() as c:
            sup = {"Authorization": "Bearer " + auth.make_token(900, "S")}
            # Пользователь ещё не писал боту /start — сообщение о привязке не доходит.
            BLOCKED.add(4242)
            SENT.clear()
            r = await c.post("/api/davomat/admin/users", headers=sup, json={"telegram_user_id": 4242, "name": "Yangi Admin", "level": "admin"})
            assert r.status_code == 200
            assert not await service.credentials_delivered(4242)
            # /start — пароль автоматически отправляется повторно.
            BLOCKED.discard(4242)
            SENT.clear()
            await bot.handle_update({"update_id": 90, "message": {"chat": {"type": "private", "id": 4242},
                                     "from": {"id": 4242, "first_name": "Yangi"}, "text": "/start"}})
            assert any(m[0] == 4242 and "Parol:" in m[1] for m in SENT)
            assert await service.credentials_delivered(4242)
            # Второй /start — пароль повторно не отправляется, обычное приветствие.
            SENT.clear()
            await bot.handle_update({"update_id": 91, "message": {"chat": {"type": "private", "id": 4242},
                                     "from": {"id": 4242, "first_name": "Yangi"}, "text": "/start"}})
            assert SENT and "Parol:" not in SENT[-1][1] and "Assalomu alaykum" in SENT[-1][1]
            # /parol — новый пароль.
            SENT.clear()
            await bot.handle_update({"update_id": 92, "message": {"chat": {"type": "private", "id": 4242},
                                     "from": {"id": 4242, "first_name": "Yangi"}, "text": "/parol"}})
            assert any(m[0] == 4242 and "Parolingiz yangilandi" in m[1] and "Parol:" in m[1] for m in SENT)

    run(loop, scenario())
