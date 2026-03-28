"""
Scheduler de alertas con resumen diario interactivo
"""
import logging
from datetime import datetime, timedelta, timezone
import pytz

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_
from database import AsyncSessionLocal, Task, CalendarEvent, Notification
import uuid

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="America/Santiago")
TZ = pytz.timezone("America/Santiago")


async def check_due_tasks():
    from bot import send_notification
    now = datetime.now(TZ)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Task).where(and_(
                Task.status.in_(["pending", "in_progress"]),
                Task.due_date.isnot(None),
                Task.due_date > now,
                Task.due_date <= now + timedelta(hours=25)
            ))
        )
        tasks = result.scalars().all()

    ALERT_INTERVALS = [(24*60, "24 horas"), (60, "1 hora"), (15, "15 minutos")]
    for task in tasks:
        due_aware = task.due_date.replace(tzinfo=timezone.utc).astimezone(TZ)
        minutes_left = (due_aware - now).total_seconds() / 60
        for threshold_min, label in ALERT_INTERVALS:
            if abs(minutes_left - threshold_min) < 5:
                msg = (
                    f"⏰ *Recordatorio de tarea*\n\n"
                    f"📝 *{task.title}*\n"
                    f"🕐 Vence en: {label}\n"
                    f"📅 {due_aware.strftime('%d/%m/%Y %H:%M')}\n"
                    f"🎯 Prioridad: {task.priority}"
                )
                await send_notification(msg, str(task.id))
                async with AsyncSessionLocal() as session:
                    session.add(Notification(
                        id=uuid.uuid4(), task_id=task.id,
                        type=f"due_alert_{label.replace(' ','_')}", message=msg
                    ))
                    await session.commit()
                break


async def check_overdue_tasks():
    from bot import send_notification
    now = datetime.now(TZ)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Task).where(and_(
                Task.status.in_(["pending", "in_progress"]),
                Task.due_date.isnot(None),
                Task.due_date < now,
                Task.due_date > now - timedelta(hours=24),
                Task.notified_at.is_(None)
            ))
        )
        tasks = result.scalars().all()

    for task in tasks:
        msg = (
            f"🚨 *¡Tarea vencida!*\n\n"
            f"📝 *{task.title}*\n"
            f"🔴 Esta tarea ya venció. ¿Pudiste completarla?"
        )
        await send_notification(msg, str(task.id))
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Task).where(Task.id == task.id))
            t = result.scalar_one()
            t.notified_at = now
            await session.commit()


async def check_calendar_alerts():
    from bot import send_notification
    now = datetime.now(TZ)
    window_start = now + timedelta(hours=2, minutes=55)
    window_end   = now + timedelta(hours=3, minutes=5)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CalendarEvent).where(and_(
                CalendarEvent.status == "created",
                CalendarEvent.alert_sent == False,
                CalendarEvent.start_datetime >= window_start,
                CalendarEvent.start_datetime <= window_end
            ))
        )
        events = result.scalars().all()

    for event in events:
        start_local = event.start_datetime.replace(tzinfo=timezone.utc).astimezone(TZ)
        msg = (
            f"⏰ *Recordatorio — en 3 horas*\n\n"
            f"📅 *{event.title}*\n"
            f"🕐 {start_local.strftime('%d/%m/%Y a las %H:%M')}\n"
        )
        if event.description:
            msg += f"📝 _{event.description[:100]}_"
        await send_notification(msg, None, str(event.id), is_calendar=True)
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(CalendarEvent).where(CalendarEvent.id == event.id))
            ev = result.scalar_one()
            ev.alert_sent = True
            await session.commit()
        logger.info(f"Alerta calendario (3hrs antes): {event.title}")


async def check_calendar_followup():
    from bot import send_notification
    now = datetime.now(TZ)
    window_start = now - timedelta(minutes=65)
    window_end   = now - timedelta(minutes=55)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CalendarEvent).where(and_(
                CalendarEvent.status == "created",
                CalendarEvent.end_datetime >= window_start,
                CalendarEvent.end_datetime <= window_end
            ))
        )
        events = result.scalars().all()

    for event in events:
        start_local = event.start_datetime.replace(tzinfo=timezone.utc).astimezone(TZ)
        msg = (
            f"✅ *¿Completaste este evento?*\n\n"
            f"📅 *{event.title}*\n"
            f"🕐 Era el {start_local.strftime('%d/%m/%Y a las %H:%M')}"
        )
        await send_notification(msg, None, str(event.id), is_calendar=True)
        logger.info(f"Seguimiento post-evento: {event.title}")


async def daily_summary():
    """
    Resumen diario con lista de tareas pendientes
    y botón de completar para cada una.
    """
    from bot import send_task_list_with_buttons
    now = datetime.now(TZ)

    async with AsyncSessionLocal() as session:
        pending_r  = await session.execute(
            select(Task).where(Task.status == "pending").order_by(
                Task.created_at.desc()
            ).limit(10)
        )
        progress_r = await session.execute(select(Task).where(Task.status == "in_progress"))
        done_r     = await session.execute(
            select(Task).where(and_(
                Task.status == "completed",
                Task.completed_at >= now - timedelta(hours=24)
            ))
        )
        today_start = now.replace(hour=0, minute=0, second=0)
        today_end   = now.replace(hour=23, minute=59, second=59)
        events_r = await session.execute(
            select(CalendarEvent).where(and_(
                CalendarEvent.status == "created",
                CalendarEvent.start_datetime >= today_start,
                CalendarEvent.start_datetime <= today_end
            )).order_by(CalendarEvent.start_datetime)
        )

    pending_tasks = pending_r.scalars().all()
    progress      = len(progress_r.scalars().all())
    done          = len(done_r.scalars().all())
    events        = events_r.scalars().all()

    # Mensaje de resumen
    msg = (
        f"🌅 *Buenos días — Resumen del día*\n\n"
        f"⏳ Tareas pendientes: {len(pending_tasks)}\n"
        f"🔄 En progreso: {progress}\n"
        f"✅ Completadas ayer: {done}\n"
    )
    if events:
        msg += f"\n📅 *Eventos de hoy:*\n"
        for ev in events:
            start_local = ev.start_datetime.replace(tzinfo=timezone.utc).astimezone(TZ)
            msg += f"  • {start_local.strftime('%H:%M')} — {ev.title}\n"

    # Enviar resumen general primero
    from bot import send_notification
    await send_notification(msg)

    # Luego enviar cada tarea pendiente con botón de completar
    if pending_tasks:
        await send_notification("📋 *Tus tareas pendientes:*")
        await send_task_list_with_buttons(pending_tasks)


async def start_scheduler():
    scheduler.add_job(check_due_tasks,        "interval", minutes=5,  id="due_tasks")
    scheduler.add_job(check_overdue_tasks,     "interval", minutes=30, id="overdue")
    scheduler.add_job(check_calendar_alerts,   "interval", minutes=10, id="cal_alerts")
    scheduler.add_job(check_calendar_followup, "interval", minutes=10, id="cal_followup")
    scheduler.add_job(daily_summary,           "cron", hour=9, minute=0, id="daily")
    scheduler.start()
    logger.info("Scheduler iniciado")


async def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
