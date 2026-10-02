# -*- coding: utf-8 -*-
"""
Ферма — standalone-сервис на FastAPI для 2 терминалов Hikvision Face ID
(ВХОД + ВЫХОД). Каждая камера делает POST на этот сервер через свой HTTP Listening (Port 80, HTTP,
URL: /event/kirish или /event/chiqish).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import ADMIN_TELEGRAM_IDS, SUPERADMIN_TELEGRAM_ID
from database import IS_SQLITE, create_all, database
from davomat import service
from davomat.api import router as davomat_router
from events import handle_event

logging.basicConfig(level=logging.INFO)
# httpx на уровне INFO пишет URL запроса — чтобы токен Telegram-бота не попал в лог.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    new_admins = service.seed_sync(ADMIN_TELEGRAM_IDS, SUPERADMIN_TELEGRAM_ID)
    await database.connect()
    if IS_SQLITE:
        await database.execute("PRAGMA journal_mode=WAL")
        await database.execute("PRAGMA busy_timeout=5000")
    for uid in new_admins:
        await service.notify_linked(uid)
    logger.info("✅ Ma'lumotlar bazasiga ulanish hosil qilindi.")
    yield
    await database.disconnect()
    logger.info("Tizim to'xtatildi.")


# В production /docs, /redoc, /openapi.json не должны быть открыты
# наружу — поэтому отключены.
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/event/kirish")
async def event_kirish(request: Request):
    return await handle_event("kirish", request)


@app.post("/event/chiqish")
async def event_chiqish(request: Request):
    return await handle_event("chiqish", request)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(davomat_router)


@app.middleware("http")
async def cache_static(request: Request, call_next):
    # Файлы фронтенда версионируются через ?v= — браузер не должен запрашивать их повторно
    # (на медленной сети страница за счёт этого открывается быстрее).
    response = await call_next(request)
    if request.url.path.startswith("/static/davomat/") and request.url.query.startswith("v="):
        response.headers["Cache-Control"] = "public, max-age=2592000, immutable"
    return response

_NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/davomat")
async def davomat_redirect():
    return RedirectResponse("/davomat/")


@app.get("/davomat/")
async def davomat_index():
    return FileResponse("static/davomat/index.html", headers=_NO_CACHE)


@app.get("/davomat/checkin")
async def davomat_checkin():
    return FileResponse("static/davomat/checkin.html", headers=_NO_CACHE)
