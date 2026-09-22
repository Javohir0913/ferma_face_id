# -*- coding: utf-8 -*-
"""
Ferma — 2 ta Hikvision Face ID terminal (KIRISH + CHIQISH) uchun standalone
FastAPI xizmat. Har bir kamera o'zining HTTP Listening (Port 80, HTTP,
URL: /event/kirish yoki /event/chiqish) orqali shu serverga POST qiladi.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from database import create_all, database
from events import handle_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    await database.connect()
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
