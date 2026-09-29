# -*- coding: utf-8 -*-
"""
Ferma — 2 ta Hikvision Face ID terminal (KIRISH + CHIQISH) uchun standalone
FastAPI xizmat. Har bir kamera o'zining HTTP Listening (Port 80, HTTP,
URL: /event/kirish yoki /event/chiqish) orqali shu serverga POST qiladi.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import ADMIN_TELEGRAM_IDS, DATABASE_URL, SUPERADMIN_TELEGRAM_ID
from database import create_all, database
from davomat import service
from davomat.api import router as davomat_router
from events import handle_event

logging.basicConfig(level=logging.INFO)
# httpx INFO darajasida so'rov URL'ini yozadi — Telegram bot tokeni logga tushmasligi uchun.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    new_admins = service.seed_sync(DATABASE_URL.split("///", 1)[1], ADMIN_TELEGRAM_IDS, SUPERADMIN_TELEGRAM_ID)
    await database.connect()
    await database.execute("PRAGMA journal_mode=WAL")
    await database.execute("PRAGMA busy_timeout=5000")
    for uid in new_admins:
        await service.notify_linked(uid)
    logger.info("✅ Ma'lumotlar bazasiga ulanish hosil qilindi.")
    yield
    await database.disconnect()
    logger.info("Tizim to'xtatildi.")


# Production'da /docs, /redoc, /openapi.json tashqi dunyoga ochiq
# bo'lmasligi kerak — shuning uchun o'chirilgan.
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
    # Frontend fayllari ?v= bilan versiyalangan — brauzer ularni qayta so'ramasin
    # (sekin tarmoqda sahifa ochilishi shu so'rovlar hisobiga tezlashadi).
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
