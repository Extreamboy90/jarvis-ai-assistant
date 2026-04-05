"""
WebSocket endpoint for browser-based voice loop
Handles audio streaming from browser → STT → LLM → TTS → browser
"""

import asyncio
import io
import logging
import os
import tempfile
from typing import Optional

import requests
from fastapi import WebSocket, WebSocketDisconnect
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Configuration
STT_SERVICE_URL = os.getenv("STT_SERVICE_URL", "http://stt:8001")
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://tts:8002")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")

# Optional: Local Whisper for low-latency STT
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

class VoiceWebSocketHandler:
    def __init__(self):
        self.whisper = None
        self.load_whisper()

    def load_whisper(self):
        """Load Whisper model for local STT"""
        try:
            logger.info(f"Loading Whisper model: {WHISPER_MODEL}")
            self.whisper = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE
            )
            logger.info("✅ Whisper model loaded")
        except Exception as e:
            logger.error(f"❌ Failed to load Whisper: {e}")
            self.whisper = None

    async def handle_voice_loop(self, websocket: WebSocket, user_id: str):
        """
        Handle WebSocket connection for voice loop

        Flow:
        1. Client sends audio chunks (Int16 PCM data)
        2. Server accumulates and transcribes with Whisper
        3. Server sends transcription to LLM
        4. Server generates TTS audio
        5. Server sends audio back to client
        6. Loop restarts
        """
        await websocket.accept()
        logger.info(f"🔌 Voice WebSocket connected: {user_id}")

        audio_buffer = bytearray()
        is_recording = False

        try:
            while True:
                # Receive data from client
                data = await websocket.receive()

                # Handle binary audio data
                if 'bytes' in data:
                    audio_chunk = data['bytes']

                    if not is_recording:
                        is_recording = True
                        audio_buffer = bytearray()
                        logger.info("🎤 Recording started")

                    audio_buffer.extend(audio_chunk)

                # Handle JSON control messages
                elif 'text' in data:
                    import json
                    message = json.loads(data['text'])

                    if message.get('type') == 'audio_start':
                        is_recording = True
                        audio_buffer = bytearray()
                        logger.info("🎤 Recording started (explicit)")

                    elif message.get('type') == 'audio_end':
                        is_recording = False

                        if len(audio_buffer) > 0:
                            logger.info(f"🎙️ Processing {len(audio_buffer)} bytes of audio")

                            # Process the complete audio
                            await self.process_voice_command(
                                websocket,
                                bytes(audio_buffer),
                                user_id
                            )

                            audio_buffer = bytearray()
                        else:
                            logger.warning("No audio data received")

                    elif message.get('type') == 'ping':
                        await websocket.send_json({"type": "pong"})

        except WebSocketDisconnect:
            logger.info(f"🔌 Voice WebSocket disconnected: {user_id}")
        except Exception as e:
            logger.error(f"❌ Voice WebSocket error: {e}")
            await websocket.close()

    async def process_voice_command(
        self,
        websocket: WebSocket,
        audio_data: bytes,
        user_id: str
    ):
        """Process complete voice command: STT → LLM → TTS"""

        try:
            # 1. Transcribe audio to text
            logger.info("📝 Transcribing audio...")
            text = await self.transcribe_audio(audio_data)

            if not text or not text.strip():
                logger.warning("Empty transcription")
                await websocket.send_json({
                    "type": "error",
                    "message": "Non ho capito, puoi ripetere?"
                })
                return

            logger.info(f"✅ Transcription: {text}")

            # Send transcription to client
            await websocket.send_json({
                "type": "transcription",
                "text": text
            })

            # 2. Send to LLM via orchestrator
            logger.info("🤖 Processing with LLM...")
            response_text = await self.get_llm_response(text, user_id)

            if not response_text:
                response_text = "Scusa, ho avuto un problema."

            logger.info(f"💬 LLM Response: {response_text[:100]}...")

            # Send text response to client
            await websocket.send_json({
                "type": "response",
                "text": response_text
            })

            # 3. Generate TTS audio
            logger.info("🔊 Generating speech...")
            audio_response = await self.generate_tts(response_text)

            if audio_response:
                # Send audio back to client
                await websocket.send_bytes(audio_response)
                logger.info("✅ Audio sent to client")
            else:
                logger.warning("TTS generation failed")

        except Exception as e:
            logger.error(f"❌ Error processing voice command: {e}")
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })

    async def transcribe_audio(self, audio_data: bytes) -> Optional[str]:
        """Transcribe audio using local Whisper or STT service"""

        # Try local Whisper first (faster)
        if self.whisper:
            try:
                # Save to temp WAV file
                with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp:
                    tmp.write(audio_data)
                    tmp_path = tmp.name

                # Transcribe
                segments, info = self.whisper.transcribe(
                    tmp_path,
                    language="it",
                    beam_size=5,
                    vad_filter=True
                )

                text = " ".join([seg.text for seg in segments]).strip()
                os.unlink(tmp_path)

                return text

            except Exception as e:
                logger.error(f"Local Whisper failed: {e}")

        # Fallback to STT service
        try:
            files = {'audio': ('recording.raw', io.BytesIO(audio_data), 'audio/raw')}
            response = requests.post(
                f"{STT_SERVICE_URL}/transcribe",
                files=files,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get('text', '')

        except Exception as e:
            logger.error(f"STT service failed: {e}")
            return None

    async def get_llm_response(self, text: str, user_id: str) -> Optional[str]:
        """Get response from LLM via orchestrator"""

        try:
            response = requests.post(
                f"{ORCHESTRATOR_URL}/chat",
                json={"message": text, "user_id": user_id},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get('response', '')

        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            return None

    async def generate_tts(self, text: str) -> Optional[bytes]:
        """Generate TTS audio"""

        try:
            response = requests.post(
                f"{TTS_SERVICE_URL}/speak",
                json={"text": text, "speed": 1.0},
                timeout=30
            )
            response.raise_for_status()
            return response.content

        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return None


# Global handler instance
voice_handler = VoiceWebSocketHandler()
