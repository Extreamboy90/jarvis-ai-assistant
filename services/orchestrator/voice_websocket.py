"""
WebSocket endpoint for browser-based voice loop
Flow: Browser audio → STT service → LLM → TTS service → Browser audio
"""

import asyncio
import io
import json
import logging
import os
from typing import Optional

import requests
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

STT_SERVICE_URL = os.getenv("STT_SERVICE_URL", "http://stt:8001")
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://tts:8002")


class VoiceWebSocketHandler:

    async def handle_voice_loop(self, websocket: WebSocket, user_id: str):
        """
        Handle WebSocket connection for voice loop.

        Protocol:
        - Client → Server: binary audio chunks
        - Client → Server: JSON {"type": "audio_start"} / {"type": "audio_end"}
        - Server → Client: JSON {"type": "transcription", "text": "..."}
        - Server → Client: JSON {"type": "response", "text": "..."}
        - Server → Client: binary WAV audio (TTS)
        """
        await websocket.accept()
        logger.info(f"🔌 Voice WebSocket connected: {user_id}")

        audio_buffer = bytearray()
        is_recording = False

        try:
            while True:
                data = await websocket.receive()

                if "bytes" in data:
                    if not is_recording:
                        is_recording = True
                        audio_buffer = bytearray()
                    audio_buffer.extend(data["bytes"])

                elif "text" in data:
                    message = json.loads(data["text"])
                    msg_type = message.get("type")

                    if msg_type == "audio_start":
                        is_recording = True
                        audio_buffer = bytearray()
                        logger.info("🎤 Recording started")

                    elif msg_type == "audio_end":
                        is_recording = False
                        if len(audio_buffer) > 0:
                            logger.info(f"🎙️ Processing {len(audio_buffer)} bytes")
                            await self._process(websocket, bytes(audio_buffer), user_id)
                            audio_buffer = bytearray()
                        else:
                            logger.warning("No audio received")

                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

        except WebSocketDisconnect:
            logger.info(f"🔌 Voice WebSocket disconnected: {user_id}")
        except Exception as e:
            logger.error(f"❌ Voice WebSocket error: {e}")
            try:
                await websocket.close()
            except Exception:
                pass

    async def _process(self, websocket: WebSocket, audio_data: bytes, user_id: str):
        """STT → LLM → TTS pipeline"""
        try:
            # 1. STT
            text = await asyncio.get_event_loop().run_in_executor(
                None, self._transcribe, audio_data
            )
            if not text or not text.strip():
                await websocket.send_json({"type": "error", "message": "Non ho capito, riprova."})
                return

            logger.info(f"📝 Transcription: {text}")
            await websocket.send_json({"type": "transcription", "text": text})

            # 2. LLM
            response_text = await asyncio.get_event_loop().run_in_executor(
                None, self._chat, text, user_id
            )
            if not response_text:
                response_text = "Scusa, ho avuto un problema."

            logger.info(f"💬 Response: {response_text[:80]}...")
            await websocket.send_json({"type": "response", "text": response_text})

            # 3. TTS
            audio = await asyncio.get_event_loop().run_in_executor(
                None, self._tts, response_text
            )
            if audio:
                await websocket.send_bytes(audio)
                logger.info("✅ Audio sent to client")

        except Exception as e:
            logger.error(f"❌ Pipeline error: {e}")
            await websocket.send_json({"type": "error", "message": str(e)})

    def _transcribe(self, audio_data: bytes) -> Optional[str]:
        """Send audio to STT service"""
        try:
            # Rileva formato: WAV inizia con b'RIFF', WebM con b'\x1a\x45'
            if audio_data[:4] == b"RIFF":
                fname, mime = "recording.wav", "audio/wav"
            else:
                fname, mime = "recording.webm", "audio/webm"
            files = {"audio": (fname, io.BytesIO(audio_data), mime)}
            resp = requests.post(f"{STT_SERVICE_URL}/transcribe", files=files, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("text", "") or data.get("transcription", "")
        except Exception as e:
            logger.error(f"STT failed: {e}")
            return None

    def _chat(self, text: str, user_id: str) -> Optional[str]:
        """Send message to orchestrator chat endpoint"""
        try:
            resp = requests.post(
                "http://localhost:8000/chat",
                json={"message": text, "user_id": user_id, "max_history": 3},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"LLM failed: {e}")
            return None

    def _tts(self, text: str) -> Optional[bytes]:
        """Generate speech from TTS service"""
        try:
            resp = requests.post(
                f"{TTS_SERVICE_URL}/speak",
                json={"text": text, "speed": 1.0},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return None


voice_handler = VoiceWebSocketHandler()
