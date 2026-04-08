import asyncio
import tempfile
import os
import logging
import re

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TTS Service - Edge TTS")

VOICE = os.getenv("EDGE_TTS_VOICE", "it-IT-DiegoNeural")


def preprocess_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[-*•]\s+', '. ', text)
    text = re.sub(r'\n+', '. ', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    # "J" italiana suona come "I", fix pronuncia nomi inglesi
    text = re.sub(r'\bJarvis\b', 'Giarvis', text, flags=re.IGNORECASE)
    return text.strip()


class TTSRequest(BaseModel):
    text: str
    speed: float = 1.0


@app.get("/health")
async def health():
    return {"status": "healthy", "voice": VOICE, "engine": "edge-tts"}


@app.get("/voices")
async def list_voices():
    voices = await edge_tts.list_voices()
    italian = [v for v in voices if v["Locale"].startswith("it-IT")]
    return {
        "available_voices": [v["ShortName"] for v in italian],
        "current": VOICE,
    }


@app.post("/speak")
async def speak(request: TTSRequest):
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    text = preprocess_text(request.text)
    logger.info(f"Generating speech: {text[:60]}...")

    # Edge TTS rate: "+0%" normal, "+20%" faster, "-20%" slower
    rate_pct = int((request.speed - 1.0) * 100)
    rate_str = f"{rate_pct:+d}%"

    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            output_path = tmp.name

        communicate = edge_tts.Communicate(text, VOICE, rate=rate_str)
        await communicate.save(output_path)

        with open(output_path, "rb") as f:
            audio_data = f.read()

        os.unlink(output_path)
        logger.info("Speech generated successfully")

        return Response(
            content=audio_data,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "attachment; filename=speech.mp3"},
        )

    except Exception as e:
        logger.error(f"Edge TTS error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
