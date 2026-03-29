from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import subprocess
import tempfile
import os
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TTS Service - Piper")

# Configurazione modello vocale
VOICE_MODEL = os.getenv("PIPER_VOICE", "it_IT-riccardo-x_low")
MODEL_PATH = f"/models/{VOICE_MODEL}.onnx"

def preprocess_text_for_tts(text: str) -> str:
    """
    Preprocessa il testo per migliorare la pronuncia in Piper TTS.
    Migliora le pause per elenchi puntati e punteggiatura.
    """
    # Normalizza spazi multipli
    text = re.sub(r'\s+', ' ', text)

    # Converti markdown/elenchi in pause naturali
    # Elenchi numerati: "1. ", "2. " -> aggiunge pausa
    text = re.sub(r'(\d+)\.\s+', r'\1. ', text)

    # Elenchi puntati: "- ", "* ", "• " -> sostituisce con pausa
    text = re.sub(r'[-*•]\s+', '. ', text)

    # Aggiungi pausa dopo i due punti se seguiti da elenco
    text = re.sub(r':\s*\n', ': ', text)

    # Normalizza punti elenco consecutivi
    text = re.sub(r'\.\s*\.', '.', text)

    # Aggiungi pause dopo virgole per migliorare ritmo
    text = re.sub(r',\s*', ', ', text)

    # Rimuovi newline multipli e sostituisci con pause
    text = re.sub(r'\n+', '. ', text)

    # Pulisci spazi prima della punteggiatura
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)

    return text.strip()

class TTSRequest(BaseModel):
    text: str
    speed: float = 1.0  # Velocità di parlato (0.5 - 2.0)

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "voice": VOICE_MODEL,
        "model_exists": os.path.exists(MODEL_PATH)
    }

@app.get("/voices")
async def list_voices():
    """Lista delle voci disponibili"""
    return {
        "available_voices": [
            "it_IT-riccardo-x_low",
            "it_IT-paola-medium",
        ],
        "current": VOICE_MODEL
    }

@app.post("/speak")
async def speak(request: TTSRequest):
    """
    Convert text to speech

    Args:
        text: Il testo da convertire in audio
        speed: Velocità di parlato (default: 1.0)

    Returns:
        Audio file in formato WAV
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        # Preprocessa il testo per migliorare pause e pronuncia
        processed_text = preprocess_text_for_tts(request.text)

        logger.info(f"Generating speech for: {request.text[:50]}...")
        logger.debug(f"Processed text: {processed_text[:100]}...")

        # Crea file temporaneo per l'audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            output_path = tmp_file.name

        # Esegui Piper TTS con parametri per velocità costante
        cmd = [
            "piper",
            "--model", MODEL_PATH,
            "--output_file", output_path,
            "--length_scale", str(1.0 / request.speed),  # Inverso della velocità
            "--noise_scale", "0.667",  # Riduce variabilità
            "--noise_w", "0.8"  # Stabilizza durata fonemi
        ]

        # Passa il testo preprocessato via stdin
        process = subprocess.run(
            cmd,
            input=processed_text.encode('utf-8'),
            capture_output=True,
            check=True
        )

        # Leggi il file audio generato
        with open(output_path, "rb") as f:
            audio_data = f.read()

        # Rimuovi file temporaneo
        os.unlink(output_path)

        logger.info("Speech generated successfully")

        return Response(
            content=audio_data,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav"
            }
        )

    except subprocess.CalledProcessError as e:
        logger.error(f"Piper TTS error: {e.stderr.decode()}")
        raise HTTPException(status_code=500, detail=f"TTS generation error: {e.stderr.decode()}")
    except Exception as e:
        logger.error(f"Error during TTS: {str(e)}")
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
