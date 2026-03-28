"""
Router de Google Calendar
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

from database import get_db, CalendarEvent
from google_calendar import create_event, list_upcoming_events, get_credentials

router = APIRouter()


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    telegram_message_id: Optional[int] = None


class EventOut(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    start_datetime: datetime
    end_datetime: datetime
    google_event_id: Optional[str]
    status: str
    alert_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=EventOut, status_code=201)
async def create_calendar_event(body: EventCreate, db: AsyncSession = Depends(get_db)):
    """Crea evento en Google Calendar y lo guarda en la BD."""
    # Crear en Google Calendar
    google_id = None
    try:
        google_id = await create_event(
            db,
            title=body.title,
            description=body.description or "",
            start_dt=body.start_datetime,
            end_dt=body.end_datetime
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error en Google Calendar: {e}")

    # Calcular end_datetime si no se proporcionó
    from datetime import timedelta
    end_dt = body.end_datetime or (body.start_datetime + timedelta(hours=1))

    # Guardar en BD local
    event = CalendarEvent(
        id=uuid.uuid4(),
        title=body.title,
        description=body.description,
        start_datetime=body.start_datetime,
        end_datetime=end_dt,
        google_event_id=google_id,
        telegram_message_id=body.telegram_message_id
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("", response_model=list[EventOut])
async def list_events(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.status == "created")
        .order_by(CalendarEvent.start_datetime)
        .limit(20)
    )
    return result.scalars().all()


@router.get("/upcoming")
async def upcoming_google_events(db: AsyncSession = Depends(get_db)):
    """Lista próximos eventos directamente desde Google Calendar."""
    try:
        events = await list_upcoming_events(db, max_results=5)
        return events
    except PermissionError as e:
        raise HTTPException(403, str(e))




@router.patch("/{event_id}")
async def update_event(event_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db)):
    """Actualizar estado de un evento de calendario."""
    from sqlalchemy import select
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Evento no encontrado")
    for k, v in body.items():
        if hasattr(event, k):
            setattr(event, k, v)
    await db.commit()
    await db.refresh(event)
    return {"id": str(event.id), "status": event.status, "title": event.title}

@router.get("/status")
async def calendar_status(db: AsyncSession = Depends(get_db)):
    creds = await get_credentials(db)
    return {
        "authorized": creds is not None and creds.valid,
        "message": "Autorizado" if (creds and creds.valid) else "No autorizado — usa /autorizar_calendar en Telegram"
    }
