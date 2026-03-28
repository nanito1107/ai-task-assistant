"""
Router de IA - Integración con Ollama
Pasa la fecha/hora actual para resolver referencias relativas como "mañana", "el viernes"
"""
import os
import json
import logging
import httpx
from fastapi import APIRouter
from time_parser import extract_datetime
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import pytz

router = APIRouter()
logger = logging.getLogger(__name__)

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
TZ           = pytz.timezone("America/Santiago")

SYSTEM_PROMPT = """Eres un asistente de agenda personal.
Fecha y hora actual: {now}
Fechas de referencia esta semana:
- Hoy ({weekday}): {today}
- Mañana ({tomorrow_weekday}): {tomorrow}
- Pasado mañana: {day_after}
- Lunes: {monday}
- Martes: {tuesday}
- Miércoles: {wednesday}
- Jueves: {thursday}
- Viernes: {friday}
- Sábado: {saturday}
- Domingo: {sunday}

Analiza el mensaje y responde SOLO con un JSON válido:
{{
  "type": "calendar" o "task",
  "title": "título corto (máx 120 chars)",
  "description": "descripción completa con todos los detalles",
  "priority": "low|medium|high|urgent",
  "start_datetime": "YYYY-MM-DDTHH:MM:SS o null",
  "end_datetime": "YYYY-MM-DDTHH:MM:SS o null",
  "due_date": "YYYY-MM-DDTHH:MM:SS o null"
}}

Reglas de clasificación:
- type "calendar": si el mensaje menciona una fecha (aunque no tenga hora)
- type "task": si NO menciona ninguna fecha ni referencia temporal

Reglas de fecha y hora:
- Usa SIEMPRE las fechas de referencia de arriba para calcular días de la semana
- "este jueves" o "el jueves" = {thursday}
- "el viernes" = {friday}
- "mañana a las 3 de la tarde" → start_datetime = {tomorrow}T15:00:00
- "mañana a las 10" → start_datetime = {tomorrow}T10:00:00
- "mañana" sin hora → start_datetime = {tomorrow}T12:00:00
- "hoy a las X" → start_datetime = {today}THH:MM:00
- "a medio día" o "al mediodía" → hora 12:00:00
- "en la mañana" → hora 09:00:00
- "en la tarde" → hora 15:00:00
- "en la noche" → hora 20:00:00
- "7:20 am" = 07:20:00, "7:20 pm" = 19:20:00
- "X de la noche" o "X pm" cuando X >= 1 y X <= 11 → sumar 12: "11 de la noche" = 23:00:00, "9 de la noche" = 21:00:00, "8 de la noche" = 20:00:00
- "12 de la noche" o "medianoche" = 00:00:00
- "X de la mañana" o "X am" → hora literal: "7 de la mañana" = 07:00:00, "11 de la mañana" = 11:00:00
- "mediodía" o "12 del día" = 12:00:00
- Si dice solo "las 11" sin am/pm/mañana/noche → asumir la hora más próxima futura desde ahora
- end_datetime = start_datetime + 1 hora si no se especifica duración
- due_date solo para tareas sin fecha de inicio

Reglas de prioridad:
- urgente/hoy/ASAP/inmediato → urgent
- importante/crítico → high
- sin indicador → medium

Responde SOLO el JSON, sin texto adicional, sin markdown, sin explicaciones."""


class ParseRequest(BaseModel):
    text: str


class ParsedMessage(BaseModel):
    type: str = "task"
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None
    due_date: Optional[str] = None


@router.post("/parse-task", response_model=ParsedMessage)
async def parse_task(body: ParseRequest):
    # Calcular fechas actuales para el prompt
    from datetime import timedelta
    now = datetime.now(TZ)

    # Calcular todos los dias de la semana actual
    weekday_num = now.weekday()  # 0=lunes, 6=domingo
    monday    = now - timedelta(days=weekday_num)

    week_dates = {
        "monday":    monday,
        "tuesday":   monday + timedelta(days=1),
        "wednesday": monday + timedelta(days=2),
        "thursday":  monday + timedelta(days=3),
        "friday":    monday + timedelta(days=4),
        "saturday":  monday + timedelta(days=5),
        "sunday":    monday + timedelta(days=6),
    }

    # Si el dia de la semana ya paso, apuntar a la proxima semana
    next_week = {}
    for day, date in week_dates.items():
        if date.date() < now.date():
            next_week[day] = (date + timedelta(days=7)).strftime("%Y-%m-%d")
        else:
            next_week[day] = date.strftime("%Y-%m-%d")

    weekday_names = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    tomorrow = now + timedelta(days=1)

    prompt_system = SYSTEM_PROMPT.format(
        now=now.strftime("%Y-%m-%d %H:%M"),
        today=now.strftime("%Y-%m-%d"),
        tomorrow=tomorrow.strftime("%Y-%m-%d"),
        day_after=(now + timedelta(days=2)).strftime("%Y-%m-%d"),
        weekday=weekday_names[weekday_num],
        tomorrow_weekday=weekday_names[tomorrow.weekday()],
        monday=next_week["monday"],
        tuesday=next_week["tuesday"],
        wednesday=next_week["wednesday"],
        thursday=next_week["thursday"],
        friday=next_week["friday"],
        saturday=next_week["saturday"],
        sunday=next_week["sunday"],
    )

    payload = {
        "model":   OLLAMA_MODEL,
        "stream":  False,
        "system":  prompt_system,
        "prompt":  body.text,
        "options": {"temperature": 0.1, "top_p": 0.9}
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()

        raw = data.get("response", "").strip()
        # Limpiar markdown si lo pone igual
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)

        # Corregir start_datetime con parser local — más preciso que el modelo pequeño
        corrected_start = extract_datetime(body.text, parsed.get("start_datetime"))
        if corrected_start:
            parsed["start_datetime"] = corrected_start
            # Si ahora tenemos fecha, asegurar end_datetime
            if not parsed.get("end_datetime"):
                start_dt = datetime.fromisoformat(corrected_start)
                parsed["end_datetime"] = (start_dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        logger.info(f"IA clasificó [{parsed.get('type')}]: {parsed.get('title')} | start: {parsed.get('start_datetime')}")
        return ParsedMessage(**parsed)

    except json.JSONDecodeError:
        logger.warning(f"Ollama no devolvió JSON válido: {raw[:200]}")
        # Intentar extraer fecha/hora con parser local aunque falle el JSON
        start = extract_datetime(body.text)
        return ParsedMessage(title=body.text[:120], description=body.text,
                             type="task", start_datetime=start)
    except Exception as e:
        logger.error(f"Error consultando Ollama: {e}")
        start = extract_datetime(body.text)
        return ParsedMessage(title=body.text[:120], description=body.text,
                             type="task", start_datetime=start)


@router.get("/status")
async def ai_status():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            models = resp.json().get("models", [])
        return {"status": "ok", "active_model": OLLAMA_MODEL,
                "available_models": [m["name"] for m in models]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}