"""
Servicio de transcripción de audio con Faster-Whisper
Carga el modelo de forma lazy (al primer uso) para arrancar rápido
"""
import os
import tempfile
import logging
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Whisper Transcription Service", version="1.0.0")

MODEL_NAME = os.getenv("WHISPER_MODEL", "base")
LANGUAGE   = os.getenv("WHISPER_LANGUAGE", "es")
MODELS_DIR = "/app/models"

# Modelo cargado de forma lazy (None hasta el primer uso)
_model = None


def get_model():
    """Carga el modelo solo cuando se necesita por primera vez."""
    global _model
    if _model is None:
        logger.info(f"Cargando modelo Whisper '{MODEL_NAME}' (puede tardar en el primer inicio)...")
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            MODEL_NAME,
            device="cpu",
            compute_type="int8",
            download_root=MODELS_DIR
        )
        logger.info("Modelo cargado correctamente")
    return _model


@app.get("/health")
async def health():
    """
    Health check liviano — responde de inmediato sin cargar el modelo.
    El modelo se carga al primer /transcribe.
    """
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "language": LANGUAGE,
        "model_loaded": _model is not None
    }


@app.get("/ready")
async def ready():
    """
    Verifica que el modelo esté cargado y listo.
    Útil para saber si el primer transcribe será lento o no.
    """
    loaded = _model is not None
    return {"ready": loaded, "model": MODEL_NAME}


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = None
):
    lang   = language or LANGUAGE
    suffix = Path(file.filename).suffix if file.filename else ".ogg"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        logger.info(f"Transcribiendo: {file.filename} ({len(content)} bytes)")
        model = get_model()  # carga lazy aquí

        segments, info = model.transcribe(
            tmp_path,
            language=lang,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}
        )

        transcript = " ".join(seg.text.strip() for seg in segments)
        logger.info(f"Resultado: {transcript[:100]}")

        return JSONResponse({
            "transcript": transcript,
            "language": info.language,
            "duration": round(info.duration, 2),
            "model": MODEL_NAME
        })

    except Exception as e:
        logger.error(f"Error transcribiendo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp_path)
