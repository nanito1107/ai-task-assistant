"""
Configuración de la base de datos con SQLAlchemy async + retry
"""
import os
import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://taskuser:taskpass123@postgres:5432/taskdb"
)

engine = create_async_engine(
    DATABASE_URL, echo=False, pool_pre_ping=True, pool_size=5, max_overflow=10
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"
    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title        = Column(Text, nullable=False)
    description  = Column(Text)
    status       = Column(String(20), default="pending")
    priority     = Column(String(10), default="medium")
    source       = Column(String(20), default="telegram")
    due_date     = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at   = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    notified_at  = Column(DateTime(timezone=True))
    telegram_message_id = Column(Integer)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title            = Column(Text, nullable=False)
    description      = Column(Text)
    start_datetime   = Column(DateTime(timezone=True), nullable=False)
    end_datetime     = Column(DateTime(timezone=True), nullable=False)
    google_event_id  = Column(Text)
    status           = Column(String(20), default="created")
    source           = Column(String(20), default="telegram")
    alert_sent       = Column(Boolean, default=False)
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at       = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    telegram_message_id = Column(Integer)


class GoogleToken(Base):
    __tablename__ = "google_tokens"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    token_data = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True))
    type    = Column(String(30))
    message = Column(Text)
    sent_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    success = Column(Boolean, default=True)


class AiLog(Base):
    __tablename__ = "ai_logs"
    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id     = Column(UUID(as_uuid=True))
    input       = Column(Text)
    output      = Column(Text)
    model       = Column(String(50))
    tokens_used = Column(Integer)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)


async def init_db(retries: int = 10, delay: int = 3):
    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Base de datos inicializada correctamente")
            return
        except Exception as e:
            if attempt == retries:
                raise
            logger.warning(f"BD no disponible (intento {attempt}/{retries}): {e}. Reintentando en {delay}s...")
            await asyncio.sleep(delay)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
