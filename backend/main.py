"""
AI Task Assistant - Backend Principal
Fase 2: Google Calendar integrado
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import tasks, transcribe, ai_router, calendar_router
from bot import start_bot, stop_bot
from scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando AI Task Assistant...")
    await init_db()
    logger.info("Base de datos inicializada")
    await start_bot()
    logger.info("Bot de Telegram iniciado")
    await start_scheduler()
    logger.info("Scheduler iniciado")
    yield
    logger.info("Apagando servicios...")
    await stop_scheduler()
    await stop_bot()


app = FastAPI(
    title="AI Task Assistant",
    description="Asistente de tareas local con IA, Telegram y Google Calendar",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(tasks.router,            prefix="/api/tasks",     tags=["Tasks"])
app.include_router(transcribe.router,       prefix="/api/transcribe",tags=["Transcribe"])
app.include_router(ai_router.router,        prefix="/api/ai",        tags=["AI"])
app.include_router(calendar_router.router,  prefix="/api/calendar",  tags=["Calendar"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
