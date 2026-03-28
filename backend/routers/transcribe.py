"""
Router de transcripción - Proxy hacia el servicio Whisper
"""
import os
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()
WHISPER_URL = os.getenv("WHISPER_URL", "http://whisper:9000")


@router.post("/audio")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe un archivo de audio usando Whisper."""
    content = await file.read()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{WHISPER_URL}/transcribe",
                files={"file": (file.filename, content, file.content_type)}
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.RequestError as e:
        raise HTTPException(503, f"Servicio Whisper no disponible: {e}")
