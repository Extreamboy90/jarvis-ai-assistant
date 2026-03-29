from fastapi import FastAPI, File, UploadFile, HTTPException
from faster_whisper import WhisperModel
import tempfile
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="STT Service - Faster Whisper")

# Inizializza il modello Whisper
# Modelli disponibili: tiny, base, small, medium, large-v2
MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

logger.info(f"Loading Whisper model: {MODEL_SIZE} on {DEVICE}")
model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
logger.info("Model loaded successfully")

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "model": MODEL_SIZE, "device": DEVICE}

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Transcribe audio file to text

    Args:
        audio: Audio file (wav, mp3, ogg, m4a, etc.)

    Returns:
        JSON with transcribed text and metadata
    """
    try:
        # Salva il file audio temporaneamente
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio.filename)[1]) as tmp_file:
            content = await audio.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        logger.info(f"Transcribing audio file: {audio.filename}")

        # Trascrivi l'audio
        segments, info = model.transcribe(
            tmp_path,
            language="it",  # Italiano
            beam_size=5,
            vad_filter=True,  # Voice Activity Detection
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        # Combina tutti i segmenti
        transcription = " ".join([segment.text for segment in segments])

        # Rimuovi file temporaneo
        os.unlink(tmp_path)

        logger.info(f"Transcription completed: {transcription[:100]}...")

        return {
            "text": transcription.strip(),
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration
        }

    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
