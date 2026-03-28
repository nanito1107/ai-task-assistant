"""
Servicio de transcripción de audio con Faster-Whisper
Expone una API REST para recibir archivos de audio y devolver texto
"""
import os
import tempfile
import logging
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Whisper Transcription Service", version="1.0.0")

# Configuración desde variables de entorno
MODEL_NAME  = os.getenv("WHISPER_MODEL", "base")
LANGUAGE    = os.getenv("WHISPER_LANGUAGE", "es")
MODELS_DIR  = "/app/models"

logger.info(f"Cargando modelo Whisper: {MODEL_NAME}")
model = WhisperModel(
    MODEL_NAME,
    device="cpu",
    compute_type="int8",
    download_root=MODELS_DIR
)
logger.info("Modelo cargado correctamente")


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME, "language": LANGUAGE}


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = None
):
    """
    Recibe un archivo de audio (ogg, mp3, wav, m4a, etc.)
    y devuelve la transcripción en texto.
    """
    lang = language or LANGUAGE
    suffix = Path(file.filename).suffix if file.filename else ".ogg"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        logger.info(f"Transcribiendo: {file.filename} ({len(content)} bytes)")
        segments, info = model.transcribe(
            tmp_path,
            language=lang,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}
        )

        transcript = " ".join(seg.text.strip() for seg in segments)
        logger.info(f"Transcripción completada: {transcript[:100]}...")

        return JSONResponse({
            "transcript": transcript,
            "language": info.language,
            "duration": round(info.duration, 2),
            "model": MODEL_NAME
        })

    except Exception as e:
        logger.error(f"Error transcribiendo: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)


@app.post("/transcribe/text")
async def transcribe_and_return_text(file: UploadFile = File(...)):
    """Versión simplificada que devuelve solo el texto."""
    result = await transcribe(file)
    data = result.body
    import json
    parsed = json.loads(data)
    return {"text": parsed["transcript"]}
