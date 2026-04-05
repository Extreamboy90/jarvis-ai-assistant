"""
JARVIS Voice Loop - Continuous voice assistant with wake word detection

Flow:
1. Listen for audio (VAD to detect speech)
2. Detect wake word "Jarvis" (OpenWakeWord)
3. Capture user command (Faster Whisper STT)
4. Send to Orchestrator LLM
5. Speak response (Piper TTS)
6. Loop back to listening
"""

import asyncio
import logging
import os
import time
from collections import deque
from io import BytesIO

import numpy as np
import requests
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel
from openwakeword.model import Model as WakeWordModel
from scipy.io import wavfile
import subprocess
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000  # Hz
CHANNELS = 1
CHUNK_DURATION_MS = 30  # WebRTC VAD usa frame da 10, 20 o 30ms
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)  # 480 samples

# VAD settings
VAD_MODE = 3  # Aggressività (0-3, 3 = più aggressivo nel rilevare silenzio)
SPEECH_PADDING_MS = 300  # Padding prima/dopo speech
SILENCE_DURATION_MS = 900  # Silenzio necessario per considerare fine frase

# Wake word
# Modelli disponibili in OpenWakeWord: "alexa", "hey_mycroft", "ok_naomi", etc.
# "hey_jarvis" richiede download manuale, usiamo "alexa" per ora (pre-installato)
WAKE_WORD = "alexa"  # Temporaneo - usa "Alexa" come wake word
WAKE_WORD_THRESHOLD = 0.5  # Soglia di confidenza

# Services
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
USER_ID = os.getenv("USER_ID", "jarvis_voice_loop")

# Models
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
PIPER_VOICE = os.getenv("PIPER_VOICE", "it_IT-paola-medium")
PIPER_MODEL_PATH = f"/models/{PIPER_VOICE}.onnx"

# ─────────────────────────────────────────────────────────────────────────────
# CLASSI
# ─────────────────────────────────────────────────────────────────────────────

class JarvisVoiceLoop:
    def __init__(self):
        logger.info("🚀 Initializing JARVIS Voice Loop...")

        # VAD
        self.vad = webrtcvad.Vad(VAD_MODE)

        # Wake word detection
        logger.info(f"Loading wake word model for '{WAKE_WORD}'...")
        # OpenWakeWord scarica automaticamente i modelli pre-trained
        self.wake_word_model = WakeWordModel(
            wakeword_models=[WAKE_WORD],
            inference_framework="onnx"
        )

        # STT (Faster Whisper)
        logger.info(f"Loading Whisper model: {WHISPER_MODEL}")
        self.whisper = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE
        )

        # Audio buffers
        self.audio_buffer = deque(maxlen=int(SAMPLE_RATE * 10))  # 10 secondi max
        self.is_speaking = False
        self.silence_chunks = 0

        logger.info("✅ JARVIS Voice Loop initialized")

    def is_speech(self, audio_chunk):
        """Detect if audio chunk contains speech using VAD"""
        # WebRTC VAD richiede audio in formato int16
        audio_int16 = (audio_chunk * 32767).astype(np.int16)
        return self.vad.is_speech(audio_int16.tobytes(), SAMPLE_RATE)

    def detect_wake_word(self, audio_chunk):
        """Detect wake word in audio chunk"""
        # OpenWakeWord richiede audio normalizzato float32
        prediction = self.wake_word_model.predict(audio_chunk)

        if WAKE_WORD in prediction:
            confidence = prediction[WAKE_WORD]
            if confidence >= WAKE_WORD_THRESHOLD:
                logger.info(f"🎯 Wake word detected! Confidence: {confidence:.2f}")
                return True
        return False

    def transcribe_audio(self, audio_data):
        """Transcribe audio to text using Faster Whisper"""
        try:
            # Salva audio in file temporaneo
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wavfile.write(tmp.name, SAMPLE_RATE, audio_data)
                tmp_path = tmp.name

            # Trascrivi
            segments, info = self.whisper.transcribe(
                tmp_path,
                language="it",
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            text = " ".join([segment.text for segment in segments]).strip()
            os.unlink(tmp_path)

            logger.info(f"📝 Transcribed: {text}")
            return text

        except Exception as e:
            logger.error(f"❌ Transcription error: {e}")
            return ""

    def send_to_llm(self, text):
        """Send text to orchestrator LLM and get response"""
        try:
            response = requests.post(
                f"{ORCHESTRATOR_URL}/chat",
                json={"message": text, "user_id": USER_ID},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

        except Exception as e:
            logger.error(f"❌ LLM error: {e}")
            return "Scusa, ho avuto un problema nel processare la richiesta."

    def speak(self, text):
        """Convert text to speech using Piper and play it"""
        try:
            logger.info(f"🔊 Speaking: {text[:50]}...")

            # Genera audio con Piper
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                output_path = tmp.name

            cmd = [
                "piper",
                "--model", PIPER_MODEL_PATH,
                "--output_file", output_path
            ]

            subprocess.run(
                cmd,
                input=text.encode('utf-8'),
                capture_output=True,
                check=True
            )

            # Riproduci audio
            sample_rate, audio_data = wavfile.read(output_path)
            sd.play(audio_data, sample_rate)
            sd.wait()  # Attendi fine riproduzione

            os.unlink(output_path)
            logger.info("✅ Speech completed")

        except Exception as e:
            logger.error(f"❌ TTS error: {e}")

    def listen_for_wake_word(self):
        """Listen continuously for wake word"""
        logger.info("👂 Listening for wake word...")

        buffer_size = int(SAMPLE_RATE * 1.28)  # 1.28s buffer per OpenWakeWord
        audio_buffer = np.zeros(buffer_size, dtype=np.float32)

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='float32',
            blocksize=CHUNK_SIZE
        ) as stream:
            while True:
                # Leggi chunk audio
                chunk, _ = stream.read(CHUNK_SIZE)
                chunk = chunk.flatten()

                # Aggiorna buffer circolare
                audio_buffer = np.roll(audio_buffer, -len(chunk))
                audio_buffer[-len(chunk):] = chunk

                # Controlla wake word
                if self.detect_wake_word(audio_buffer):
                    return True

    def record_command(self):
        """Record audio command after wake word detection"""
        logger.info("🎤 Recording command...")

        self.audio_buffer.clear()
        self.is_speaking = False
        self.silence_chunks = 0

        silence_threshold = int(SILENCE_DURATION_MS / CHUNK_DURATION_MS)

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='float32',
            blocksize=CHUNK_SIZE
        ) as stream:
            while True:
                chunk, _ = stream.read(CHUNK_SIZE)
                chunk = chunk.flatten()

                # Controlla se c'è speech
                if self.is_speech(chunk):
                    self.is_speaking = True
                    self.silence_chunks = 0
                    self.audio_buffer.extend(chunk)
                else:
                    if self.is_speaking:
                        self.silence_chunks += 1
                        self.audio_buffer.extend(chunk)

                        # Fine comando se silenzio prolungato
                        if self.silence_chunks >= silence_threshold:
                            logger.info("✅ Command recorded")
                            # Converti buffer in numpy array
                            audio_array = np.array(self.audio_buffer, dtype=np.float32)
                            # Converti in int16 per Whisper
                            audio_int16 = (audio_array * 32767).astype(np.int16)
                            return audio_int16

                # Timeout dopo 10 secondi
                if len(self.audio_buffer) >= SAMPLE_RATE * 10:
                    logger.warning("⏱️ Recording timeout")
                    if len(self.audio_buffer) > 0:
                        audio_array = np.array(self.audio_buffer, dtype=np.float32)
                        audio_int16 = (audio_array * 32767).astype(np.int16)
                        return audio_int16
                    return None

    def run(self):
        """Main loop"""
        logger.info("🎙️ JARVIS Voice Loop started!")

        while True:
            try:
                # 1. Ascolta wake word
                self.listen_for_wake_word()

                # Feedback audio (beep)
                logger.info("🔔 Wake word activated!")

                # 2. Registra comando
                audio_command = self.record_command()

                if audio_command is None or len(audio_command) == 0:
                    logger.warning("No audio recorded, restarting loop...")
                    continue

                # 3. Trascrivi
                text = self.transcribe_audio(audio_command)

                if not text:
                    logger.warning("No transcription, restarting loop...")
                    continue

                # 4. Invia a LLM
                response = self.send_to_llm(text)

                if not response:
                    continue

                # 5. Parla risposta
                self.speak(response)

                # 6. Torna ad ascoltare (loop automatico)
                logger.info("🔄 Restarting loop...\n")

            except KeyboardInterrupt:
                logger.info("👋 Shutting down JARVIS...")
                break
            except Exception as e:
                logger.error(f"❌ Loop error: {e}")
                time.sleep(1)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    jarvis = JarvisVoiceLoop()
    jarvis.run()
