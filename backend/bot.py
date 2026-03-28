"""
Bot de Telegram - AI Task Assistant v2
"""
import os
import io
import logging
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
    ConversationHandler
)

logger = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID", "")
BACKEND_URL = "http://localhost:8000"
WHISPER_URL = os.getenv("WHISPER_URL", "http://whisper:9000")

_app: Application = None
WAITING_OAUTH_CODE = 1

PRIO_EMOJI   = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}
STATUS_EMOJI = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "cancelled": "❌"}


# ─────────────────────────────────────────────────────────────
# HELPER: enviar lista de tareas con botón de completar
# ─────────────────────────────────────────────────────────────

async def send_task_list_with_buttons(tasks: list):
    """
    Envía cada tarea como un mensaje separado con
    botón inline de ✅ Completar y 🗑 Cancelar.
    Así el usuario puede actuar sobre cada una individualmente.
    """
    if not _app or not CHAT_ID:
        return

    for task in tasks:
        prio    = task.priority if hasattr(task, 'priority') else task.get('priority', 'medium')
        title   = task.title if hasattr(task, 'title') else task.get('title', '')
        task_id = str(task.id if hasattr(task, 'id') else task.get('id', ''))
        due     = task.due_date if hasattr(task, 'due_date') else task.get('due_date')

        due_str = ""
        if due:
            due_str = f"\n📅 Vence: {str(due)[:16].replace('T',' ')}"

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Completar", callback_data=f"complete:{task_id}"),
            InlineKeyboardButton("🗑 Cancelar",  callback_data=f"cancel:{task_id}")
        ]])

        await _app.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"{PRIO_EMOJI.get(prio,'⚪')} *{title}*"
                f"{due_str}\n"
                f"🆔 `{task_id[:8]}`"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard
        )


# ─────────────────────────────────────────────────────────────
# COMANDOS
# ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *AI Task Assistant*\n\n"
        "📅 *Con fecha/hora* → agendo en Google Calendar\n"
        "   _'Ir al médico mañana a las 3 de la tarde'_\n"
        "   _'Llamar a mi hija mañana'_ → agenda a las 12:00\n\n"
        "📝 *Sin fecha* → guardo como tarea\n"
        "   _'Revisar el correo'_, _'Comprar leche'_\n\n"
        "🔔 Te aviso *3 horas antes* de cada evento.\n\n"
        "*Comandos:*\n"
        "• /tareas — listar tareas\n"
        "• /pendientes — tareas pendientes con opción de completar\n"
        "• /agenda — próximos eventos del calendario\n"
        "• /completar ID — marcar tarea completada\n"
        "• /autorizar\\_calendar — conectar Google Calendar\n"
        "• /ayuda — esta ayuda",
        parse_mode="Markdown"
    )


async def cmd_tareas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BACKEND_URL}/api/tasks?limit=10")
            tasks = resp.json()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return

    if not tasks:
        await update.message.reply_text("📋 No hay tareas registradas.")
        return

    msg = "📋 *Tus últimas tareas:*\n\n"
    for t in tasks:
        msg += (
            f"{STATUS_EMOJI.get(t['status'],'❓')} {PRIO_EMOJI.get(t['priority'],'⚪')} "
            f"*{t['title'][:60]}*\n   ID: `{str(t['id'])[:8]}`\n\n"
        )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_pendientes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Muestra tareas pendientes Y eventos del calendario pendientes,
    cada uno con botones de acción.
    """
    tasks = []
    events = []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Tareas sin fecha
            resp_tasks = await client.get(f"{BACKEND_URL}/api/tasks?status=pending&limit=15")
            tasks = resp_tasks.json()
            # Eventos del calendario pendientes
            resp_events = await client.get(f"{BACKEND_URL}/api/calendar?limit=15")
            events = resp_events.json() if resp_events.status_code == 200 else []
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return

    if not tasks and not events:
        await update.message.reply_text("✅ No tienes tareas ni eventos pendientes.")
        return

    total = len(tasks) + len(events)
    await update.message.reply_text(
        f"📋 *{total} pendiente(s):* ⏳ {len(tasks)} tarea(s) · 📅 {len(events)} evento(s)",
        parse_mode="Markdown"
    )

    # Tareas sin fecha
    for t in tasks:
        due_str = ""
        if t.get("due_date"):
            due_str = " | 📅 " + t["due_date"][:16].replace("T", " ")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Completar", callback_data="complete:" + t["id"]),
            InlineKeyboardButton("🗑 Cancelar",  callback_data="cancel:" + t["id"])
        ]])
        msg = PRIO_EMOJI.get(t["priority"], "o") + " *" + t["title"][:80] + "*" + due_str + "\n" + "ID: `" + str(t["id"])[:8] + "`"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)

    # Eventos del calendario
    for ev in events:
        start = ev.get("start_datetime", "")
        start_str = start[:16].replace("T", " a las ") if start else ""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Completado", callback_data="cal_complete:" + ev["id"]),
            InlineKeyboardButton("⏭ Pendiente",  callback_data="cal_pending:" + ev["id"])
        ]])
        msg = "Cal: *" + ev["title"][:80] + "*\n" + start_str + "\nID: `" + str(ev["id"])[:8] + "`"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)


async def cmd_agenda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{BACKEND_URL}/api/calendar/upcoming")
            if resp.status_code == 403:
                await update.message.reply_text(
                    "❌ Google Calendar no autorizado.\n"
                    "Usa /autorizar\\_calendar para conectarlo.",
                    parse_mode="Markdown"
                )
                return
            events = resp.json()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return

    if not events:
        await update.message.reply_text("📅 No tienes eventos próximos.")
        return

    msg = "📅 *Próximos eventos:*\n\n"
    for ev in events:
        start = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date", ""))
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            start_str = dt.strftime("%d/%m/%Y %H:%M")
        except:
            start_str = start[:16]
        msg += f"🗓 *{ev.get('summary','Sin título')}*\n   📅 {start_str}\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_completar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text("Uso: /completar <ID_TAREA>")
        return
    task_id = args[0]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                f"{BACKEND_URL}/api/tasks/{task_id}",
                json={"status": "completed"}
            )
        if resp.status_code == 200:
            await update.message.reply_text(f"✅ Tarea `{task_id[:8]}` completada.")
        else:
            await update.message.reply_text(f"❌ No se encontró la tarea.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


# ─────────────────────────────────────────────────────────────
# AUTORIZACIÓN GOOGLE CALENDAR
# ─────────────────────────────────────────────────────────────

async def cmd_autorizar_calendar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        from google_calendar import start_oauth_flow
        auth_url = start_oauth_flow()
        await update.message.reply_text(
            "🔐 *Autorizar Google Calendar*\n\n"
            "1️⃣ Abre este enlace:\n\n"
            f"`{auth_url}`\n\n"
            "2️⃣ Inicia sesión con tu Gmail personal\n"
            "3️⃣ Acepta los permisos\n"
            "4️⃣ Copia el código que te muestra Google\n"
            "5️⃣ Envíamelo aquí\n\n"
            "_Tienes 5 minutos._",
            parse_mode="Markdown"
        )
        return WAITING_OAUTH_CODE
    except FileNotFoundError:
        await update.message.reply_text(
            "❌ *Falta credentials.json*\n\n"
            "Descárgalo desde Google Cloud Console y cópialo a:\n"
            "`backend/credentials.json`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return ConversationHandler.END


async def receive_oauth_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    processing = await update.message.reply_text("🔄 Verificando código...")
    try:
        from google_calendar import exchange_code
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await exchange_code(code, db)
        await processing.edit_text(
            "✅ *¡Google Calendar autorizado!*\n\n"
            "Ahora cuando menciones una fecha en tu mensaje,\n"
            "lo agendaré y te avisaré 3 horas antes.\n\n"
            "Prueba: _'Ir al médico mañana a las 3 de la tarde'_",
            parse_mode="Markdown"
        )
    except Exception as e:
        await processing.edit_text(
            f"❌ Código inválido: {e}\n\nUsa /autorizar\\_calendar nuevamente.",
            parse_mode="Markdown"
        )
    return ConversationHandler.END


async def cancel_oauth(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Autorización cancelada.")
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────
# FUNCIÓN CENTRAL — crear tarea o evento
# ─────────────────────────────────────────────────────────────

async def crear_desde_texto(text: str, msg_id: int, reply_msg):
    parsed = {
        "type": "task", "title": text[:120], "description": text,
        "priority": "medium", "start_datetime": None,
        "end_datetime": None, "due_date": None
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            ai_resp = await client.post(
                f"{BACKEND_URL}/api/ai/parse-task",
                json={"text": text}
            )
            if ai_resp.status_code == 200:
                parsed = ai_resp.json()
                logger.info(f"IA [{parsed.get('type')}]: {parsed.get('title')} | start: {parsed.get('start_datetime')}")
    except Exception as e:
        logger.warning(f"IA no disponible: {e}")

    # ── EVENTO DE CALENDARIO ─────────────────────────────────
    # Si hay start_datetime → siempre va al calendario (no dependemos del type)
    if parsed.get("start_datetime"):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                event_resp = await client.post(
                    f"{BACKEND_URL}/api/calendar",
                    json={
                        "title":          parsed.get("title", text[:120]),
                        "description":    parsed.get("description") or text,
                        "start_datetime": parsed.get("start_datetime"),
                        "end_datetime":   parsed.get("end_datetime"),
                        "telegram_message_id": msg_id
                    }
                )

            if event_resp.status_code == 403:
                await reply_msg.edit_text(
                    "⚠️ *Google Calendar no autorizado*\n\n"
                    "Guardé el mensaje como tarea. Para agendarlo usa /autorizar\\_calendar",
                    parse_mode="Markdown"
                )
                parsed["type"] = "task"
            elif event_resp.status_code == 201:
                event = event_resp.json()
                start_str = parsed.get("start_datetime", "")[:16].replace("T", " a las ")
                await reply_msg.edit_text(
                    f"📅 *Agendado en Google Calendar:*\n\n"
                    f"🗓 *{parsed.get('title')}*\n"
                    f"⏰ {start_str}\n\n"
                    f"🔔 _Te avisaré 3 horas antes._\n"
                    f"🆔 `{str(event['id'])[:8]}`",
                    parse_mode="Markdown"
                )
                return event
            else:
                logger.error(f"Error calendar: {event_resp.status_code} - {event_resp.text}")
                raise Exception(f"Error {event_resp.status_code}: {event_resp.text}")

        except Exception as e:
            logger.error(f"Error creando evento en calendar: {e}", exc_info=True)
            if "403" not in str(e):
                await reply_msg.edit_text(
                    f"⚠️ No pude crear el evento en Google Calendar: {e}. Guardando como tarea con fecha..."
                )

    # ── TAREA NORMAL ─────────────────────────────────────────
    # Si tenia fecha (start_datetime) pero fallo el calendario,
    # usar start_datetime como due_date para no perder la fecha
    due_date = parsed.get("due_date") or parsed.get("start_datetime")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            task_resp = await client.post(
                f"{BACKEND_URL}/api/tasks",
                json={
                    "title":       parsed.get("title", text[:120]),
                    "description": parsed.get("description") or text,
                    "priority":    parsed.get("priority", "medium"),
                    "due_date":    due_date,
                    "source":      "telegram",
                    "telegram_message_id": msg_id
                }
            )
            task = task_resp.json()

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Completar", callback_data=f"complete:{task['id']}"),
            InlineKeyboardButton("🗑 Cancelar",  callback_data=f"cancel:{task['id']}")
        ]])
        prio = parsed.get("priority", "medium")
        desc = parsed.get("description") or text
        desc_preview = desc[:200] + ("..." if len(desc) > 200 else "")

        await reply_msg.edit_text(
            f"✅ *Tarea guardada:*\n\n"
            f"📝 *{parsed.get('title', text[:80])}*\n"
            f"📄 _{desc_preview}_\n"
            f"🎯 Prioridad: {PRIO_EMOJI.get(prio,'🟡')} {prio}\n"
            f"🆔 `{str(task['id'])[:8]}`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return task

    except Exception as e:
        logger.error(f"Error creando tarea: {e}", exc_info=True)
        await reply_msg.edit_text(f"❌ Error al guardar: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# HANDLERS DE MENSAJES
# ─────────────────────────────────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    processing_msg = await update.message.reply_text("🤔 Analizando tu mensaje...")
    try:
        await crear_desde_texto(update.message.text, update.message.message_id, processing_msg)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await processing_msg.edit_text(f"❌ Error: {e}")


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    processing_msg = await update.message.reply_text("🎤 Transcribiendo tu audio...")
    try:
        voice = update.message.voice or update.message.audio
        file  = await ctx.bot.get_file(voice.file_id)
        audio_bytes = io.BytesIO()
        await file.download_to_memory(audio_bytes)
        audio_bytes.seek(0)

        async with httpx.AsyncClient(timeout=120) as client:
            whisper_resp = await client.post(
                f"{WHISPER_URL}/transcribe",
                files={"file": ("audio.ogg", audio_bytes, "audio/ogg")}
            )
            transcript = whisper_resp.json().get("transcript", "").strip()

        if not transcript:
            await processing_msg.edit_text("❌ No pude transcribir el audio.")
            return

        await processing_msg.edit_text(
            f"📝 *Transcripción:* _{transcript}_\n\n🤔 Analizando...",
            parse_mode="Markdown"
        )
        await crear_desde_texto(transcript, update.message.message_id, processing_msg)

    except Exception as e:
        logger.error(f"Error en audio: {e}", exc_info=True)
        await processing_msg.edit_text(f"❌ Error: {e}")


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 1)
    action, item_id = parts[0], parts[1]

    # ── Callbacks de eventos de calendario ───────────────────
    if action in ("cal_complete", "cal_pending"):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if action == "cal_complete":
                    await client.patch(
                        f"{BACKEND_URL}/api/calendar/{item_id}",
                        json={"status": "completed"}
                    )
                    await query.edit_message_text(
                        f"✅ *Evento completado*\n`{item_id[:8]}`",
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(
                        f"⏭ *Quedó pendiente*\n`{item_id[:8]}`",
                        parse_mode="Markdown"
                    )
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {e}")
        return

    # ── Callbacks de tareas normales ─────────────────────────
    new_status = "completed" if action == "complete" else "cancelled"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.patch(
                f"{BACKEND_URL}/api/tasks/{item_id}",
                json={"status": new_status}
            )
        emoji = "✅" if new_status == "completed" else "❌"
        await query.edit_message_text(
            f"{emoji} *{new_status.capitalize()}*\n"
            f"_{query.message.text.split(chr(10))[0].replace('*','')}_\n"
            f"`{item_id[:8]}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {e}")


# ─────────────────────────────────────────────────────────────
# NOTIFICACIONES EXTERNAS (usadas por scheduler)
# ─────────────────────────────────────────────────────────────

async def send_notification(message: str, task_id: str = None, event_id: str = None, is_calendar: bool = False):
    if not _app or not CHAT_ID:
        return
    keyboard = None
    if task_id and not is_calendar:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Completar", callback_data=f"complete:{task_id}"),
            InlineKeyboardButton("🗑 Cancelar",  callback_data=f"cancel:{task_id}")
        ]])
    elif event_id and is_calendar:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Sí, completado", callback_data=f"cal_complete:{event_id}"),
            InlineKeyboardButton("⏭ Pendiente",      callback_data=f"cal_pending:{event_id}")
        ]])
    await _app.bot.send_message(
        chat_id=CHAT_ID, text=message,
        parse_mode="Markdown", reply_markup=keyboard
    )


# ─────────────────────────────────────────────────────────────
# CICLO DE VIDA
# ─────────────────────────────────────────────────────────────

async def start_bot():
    global _app
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN no configurado.")
        return

    _app = Application.builder().token(BOT_TOKEN).build()

    oauth_handler = ConversationHandler(
        entry_points=[CommandHandler("autorizar_calendar", cmd_autorizar_calendar)],
        states={WAITING_OAUTH_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_oauth_code)]},
        fallbacks=[CommandHandler("cancelar", cancel_oauth)],
        conversation_timeout=300
    )

    _app.add_handler(oauth_handler)
    _app.add_handler(CommandHandler("start",      cmd_start))
    _app.add_handler(CommandHandler("tareas",     cmd_tareas))
    _app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    _app.add_handler(CommandHandler("agenda",     cmd_agenda))
    _app.add_handler(CommandHandler("completar",  cmd_completar))
    _app.add_handler(CommandHandler("ayuda",      cmd_ayuda))
    _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    _app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO,   handle_voice))
    _app.add_handler(CallbackQueryHandler(handle_callback))

    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot de Telegram iniciado")


async def stop_bot():
    global _app
    if _app:
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()