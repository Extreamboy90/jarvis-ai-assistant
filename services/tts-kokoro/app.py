from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import tempfile
import os
import logging
import soundfile as sf
import torch
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TTS Service - Meta MMS")

# Inizializzazione lazy del modello MMS
mms_model = None
mms_tokenizer = None

def get_mms_model():
    """Lazy initialization del modello Meta MMS-TTS"""
    global mms_model, mms_tokenizer
    if mms_model is None:
        try:
            from transformers import VitsModel, VitsTokenizer

            # MMS-TTS repository principale con codice lingua italiano
            model_name = "facebook/mms-tts"
            language = "ita"  # Codice ISO 639-3 per italiano

            logger.info(f"Initializing Meta MMS-TTS model: {model_name} (language: {language})")

            # Carica tokenizer e modello per italiano
            mms_tokenizer = VitsTokenizer.from_pretrained(model_name, language=language)
            mms_model = VitsModel.from_pretrained(model_name)

            # Usa CPU
            mms_model = mms_model.to("cpu")

            logger.info("Meta MMS-TTS model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MMS-TTS: {e}")
            raise
    return mms_model, mms_tokenizer

class TTSRequest(BaseModel):
    text: str
    speed: float = 1.0

@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Verifica che il modello sia inizializzabile
        get_mms_model()
        model_loaded = True
    except:
        model_loaded = False

    return {
        "status": "healthy" if model_loaded else "unhealthy",
        "engine": "meta-mms",
        "model": "facebook/mms-tts",
        "language": "italian (ita)",
        "model_loaded": model_loaded
    }

@app.get("/voices")
async def list_voices():
    """Lista delle voci disponibili"""
    return {
        "available_voices": [
            {"code": "ita", "name": "Italian (Meta MMS)", "language": "Italian"}
        ],
        "current": "ita",
        "note": "Meta MMS-TTS optimized for Italian"
    }

@app.post("/speak")
async def speak(request: TTSRequest):
    """
    Convert text to speech using Meta MMS-TTS

    Args:
        text: Il testo da convertire in audio
        speed: Velocità di parlato (default: 1.0)

    Returns:
        Audio file in formato WAV
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        logger.info(f"Generating speech with MMS-TTS: {request.text[:50]}...")

        # Ottieni modello e tokenizer
        model, tokenizer = get_mms_model()

        # Tokenizza il testo
        inputs = tokenizer(request.text, return_tensors="pt")

        # Genera audio
        with torch.no_grad():
            output = model(**inputs)
            audio = output.waveform.squeeze().cpu().numpy()

        # Applica speed (resample)
        if request.speed != 1.0:
            # Semplice time stretching via resampling
            import scipy.signal as signal
            num_samples = int(len(audio) / request.speed)
            audio = signal.resample(audio, num_samples)

        # Sample rate del modello MMS
        sample_rate = model.config.sampling_rate

        # Salva temporaneamente
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            sf.write(tmp_file.name, audio, sample_rate)
            output_path = tmp_file.name

        # Leggi il file audio generato
        with open(output_path, "rb") as f:
            audio_data = f.read()

        # Rimuovi file temporaneo
        os.unlink(output_path)

        logger.info(f"Speech generated successfully ({len(audio_data)} bytes)")

        return Response(
            content=audio_data,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav"
            }
        )

    except Exception as e:
        logger.error(f"Error during TTS generation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
