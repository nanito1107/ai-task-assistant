"""
Parser de fechas y horas desde texto en español
Fallback cuando el modelo de IA no extrae correctamente la hora
"""
import re
from datetime import datetime, timedelta
import pytz

TZ = pytz.timezone("America/Santiago")

# Mapeo de días de la semana en español
DIAS = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
}

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}


def parse_hour_from_text(text: str) -> str | None:
    """
    Extrae la hora de un texto en español.
    Retorna string HH:MM:SS o None si no encuentra hora.
    """
    text_lower = text.lower()

    # Patrones de hora con am/pm explícito
    # "7:20 am", "11:30 pm", "7 am", "11 pm"
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text_lower)
    if match:
        h = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        period = match.group(3)
        if period == "pm" and h != 12:
            h += 12
        elif period == "am" and h == 12:
            h = 0
        return f"{h:02d}:{m:02d}:00"

    # "X de la noche" → PM (sumar 12 si h < 12)
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*de la noche', text_lower)
    if match:
        h = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        if h != 12:
            h += 12
        if h >= 24:
            h = 0
        return f"{h:02d}:{m:02d}:00"

    # "medianoche" o "12 de la noche"
    if "medianoche" in text_lower or re.search(r'12\s*de la noche', text_lower):
        return "00:00:00"

    # "X de la mañana" → AM
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*de la ma[ñn]ana', text_lower)
    if match:
        h = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        return f"{h:02d}:{m:02d}:00"

    # "mediodía" o "12 del día"
    if "mediodía" in text_lower or "mediodia" in text_lower or re.search(r'12\s*del?\s*día', text_lower):
        return "12:00:00"

    # "en la tarde" → 15:00
    if "en la tarde" in text_lower or "por la tarde" in text_lower:
        return "15:00:00"

    # "en la mañana" → 09:00
    if "en la mañana" in text_lower or "por la mañana" in text_lower:
        return "09:00:00"

    # "en la noche" → 20:00
    if "en la noche" in text_lower or "por la noche" in text_lower:
        return "20:00:00"

    # Hora sola "a las X" sin indicador → si X <= 7 asumir PM, sino AM
    match = re.search(r'a las (\d{1,2})(?::(\d{2}))?(?!\s*(?:am|pm|de|del))', text_lower)
    if match:
        h = int(match.group(1))
        m = int(match.group(2)) if match.group(2) else 0
        # Heurística: horas 1-7 sin contexto → probablemente PM
        if 1 <= h <= 7:
            h += 12
        return f"{h:02d}:{m:02d}:00"

    return None


def parse_date_from_text(text: str) -> str | None:
    """
    Extrae la fecha de un texto en español.
    Retorna string YYYY-MM-DD o None.
    """
    text_lower = text.lower()
    now = datetime.now(TZ)

    # Hoy
    if "hoy" in text_lower:
        return now.strftime("%Y-%m-%d")

    # Mañana
    if "mañana" in text_lower or "manana" in text_lower:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")

    # Pasado mañana
    if "pasado mañana" in text_lower or "pasado manana" in text_lower:
        return (now + timedelta(days=2)).strftime("%Y-%m-%d")

    # Día de la semana: "el lunes", "este jueves", "el próximo viernes"
    for dia, num in DIAS.items():
        if dia in text_lower:
            days_ahead = (num - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Si es hoy, ir al próximo
            return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # Fecha con mes: "el 26 de marzo", "el 5 de abril"
    match = re.search(r'el (\d{1,2}) de (\w+)', text_lower)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        month = MESES.get(month_str)
        if month:
            year = now.year
            # Si el mes ya pasó este año, usar el próximo año
            candidate = datetime(year, month, day, tzinfo=TZ)
            if candidate.date() < now.date():
                year += 1
            return f"{year}-{month:02d}-{day:02d}"

    # Solo número de día: "el 26", "el día 15"
    match = re.search(r'el (?:día )?(\d{1,2})(?!\s*de)', text_lower)
    if match:
        day = int(match.group(1))
        # Asumir mes actual o próximo
        try:
            candidate = datetime(now.year, now.month, day, tzinfo=TZ)
            if candidate.date() < now.date():
                # Pasar al mes siguiente
                if now.month == 12:
                    candidate = datetime(now.year + 1, 1, day, tzinfo=TZ)
                else:
                    candidate = datetime(now.year, now.month + 1, day, tzinfo=TZ)
            return candidate.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def extract_datetime(text: str, ai_start: str | None = None) -> str | None:
    """
    Combina la fecha del AI con la hora parseada localmente.
    Si el AI no extrajo fecha o hora, las calcula desde el texto.

    Retorna ISO datetime string o None.
    """
    # Parsear hora del texto (más confiable que el modelo pequeño)
    local_hour = parse_hour_from_text(text)

    # Si el AI ya tiene un start_datetime válido, solo corregir la hora
    if ai_start:
        try:
            date_part = ai_start[:10]  # YYYY-MM-DD
            if local_hour:
                # Usar la fecha del AI pero la hora parseada localmente
                return f"{date_part}T{local_hour}"
            return ai_start
        except Exception:
            pass

    # Si el AI no tiene fecha, parsear también la fecha del texto
    local_date = parse_date_from_text(text)
    if local_date:
        hour = local_hour or "12:00:00"
        return f"{local_date}T{hour}"

    return None
