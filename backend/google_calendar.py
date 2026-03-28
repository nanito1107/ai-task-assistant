"""
Integración con Google Calendar
OAuth2 via Telegram (sin navegador en el servidor)
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CREDENTIALS_FILE = "/app/credentials.json"

# Estado temporal para el flujo OAuth (en memoria)
_oauth_flow: Optional[Flow] = None
_credentials: Optional[Credentials] = None


# ─────────────────────────────────────────────────────────────
# GESTIÓN DE CREDENCIALES
# ─────────────────────────────────────────────────────────────

def credentials_file_exists() -> bool:
    return os.path.exists(CREDENTIALS_FILE)


async def get_credentials(db) -> Optional[Credentials]:
    """Obtiene credenciales válidas desde la BD, las renueva si expiró."""
    global _credentials

    # Intentar desde caché en memoria primero
    if _credentials and _credentials.valid:
        return _credentials

    # Cargar desde BD
    from sqlalchemy import select, text
    from database import GoogleToken
    try:
        result = await db.execute(select(GoogleToken).limit(1))
        token_row = result.scalar_one_or_none()
        if not token_row:
            return None

        creds = Credentials.from_authorized_user_info(token_row.token_data, SCOPES)

        # Renovar si expiró
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            await save_credentials(db, creds)

        _credentials = creds
        return creds if creds.valid else None

    except Exception as e:
        logger.error(f"Error cargando credenciales: {e}")
        return None


async def save_credentials(db, creds: Credentials):
    """Guarda el token en la BD."""
    global _credentials
    from sqlalchemy import select, delete
    from database import GoogleToken

    token_data = json.loads(creds.to_json())

    # Eliminar token anterior y guardar nuevo
    await db.execute(delete(GoogleToken))
    token_row = GoogleToken(token_data=token_data)
    db.add(token_row)
    await db.commit()
    _credentials = creds
    logger.info("Token de Google guardado en BD")


# ─────────────────────────────────────────────────────────────
# FLUJO OAUTH — Diseñado para autorizar via Telegram
# ─────────────────────────────────────────────────────────────

def start_oauth_flow() -> str:
    """
    Inicia el flujo OAuth y devuelve la URL de autorización.
    El usuario la abre en su teléfono, autoriza y Google le muestra
    un código que debe enviar de vuelta al bot.
    """
    global _oauth_flow

    if not credentials_file_exists():
        raise FileNotFoundError(
            "No se encontró credentials.json en /app/\n"
            "Descárgalo desde Google Cloud Console y cópialo al directorio backend/"
        )

    _oauth_flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob"  # Flujo de código manual
    )

    auth_url, _ = _oauth_flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return auth_url


async def exchange_code(code: str, db) -> bool:
    """
    Intercambia el código de autorización por un token y lo guarda.
    """
    global _oauth_flow
    if not _oauth_flow:
        raise ValueError("No hay flujo OAuth activo. Usa /autorizar_calendar primero.")

    try:
        _oauth_flow.fetch_token(code=code.strip())
        creds = _oauth_flow.credentials
        await save_credentials(db, creds)
        _oauth_flow = None
        return True
    except Exception as e:
        logger.error(f"Error intercambiando código OAuth: {e}")
        raise


# ─────────────────────────────────────────────────────────────
# OPERACIONES DE CALENDARIO
# ─────────────────────────────────────────────────────────────

async def create_event(
    db,
    title: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime = None,
) -> Optional[str]:
    """
    Crea un evento en Google Calendar.
    Devuelve el Google Event ID o None si falla.
    """
    creds = await get_credentials(db)
    if not creds:
        raise PermissionError("Google Calendar no autorizado. Usa /autorizar_calendar")

    if not end_dt:
        end_dt = start_dt + timedelta(hours=1)

    # Asegurar que end > start (evita timeRangeEmpty en Google Calendar)
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)

    # Formatear con offset de timezone de Santiago (-03:00 o -04:00 segun DST)
    import pytz
    tz = pytz.timezone("America/Santiago")

    def to_tz_str(dt):
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        else:
            dt = dt.astimezone(tz)
        return dt.isoformat()

    service = build("calendar", "v3", credentials=creds)

    event_body = {
        "summary":     title,
        "description": description or "",
        "start": {
            "dateTime": to_tz_str(start_dt),
            "timeZone": "America/Santiago",
        },
        "end": {
            "dateTime": to_tz_str(end_dt),
            "timeZone": "America/Santiago",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
            ]
        }
    }

    try:
        event = service.events().insert(calendarId="primary", body=event_body).execute()
        logger.info(f"Evento creado en Google Calendar: {event['id']}")
        return event["id"]
    except HttpError as e:
        logger.error(f"Error creando evento en Google Calendar: {e}")
        raise


async def list_upcoming_events(db, max_results: int = 5) -> list:
    """Lista los próximos eventos del calendario."""
    creds = await get_credentials(db)
    if not creds:
        raise PermissionError("Google Calendar no autorizado.")

    service = build("calendar", "v3", credentials=creds)
    now = datetime.utcnow().isoformat() + "Z"

    try:
        events_result = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        return events_result.get("items", [])
    except HttpError as e:
        logger.error(f"Error listando eventos: {e}")
        return []