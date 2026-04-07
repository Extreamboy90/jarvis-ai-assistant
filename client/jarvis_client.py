"""
Jarvis Native Client
Gira in background su Windows/Mac/Linux.

Flusso:
  1. In ascolto wake word ("Hey Jarvis")
  2. Wake word rilevata → "Dimmi" → registra comando
  3. Invia audio al server → ricevi trascrizione + risposta TTS
  4. Riproduci risposta
  5. Modalità conversazione (30s): ascolta direttamente senza wake word
  6. Dopo 30s inattività → torna a modalità wake word
"""

import asyncio
import io
import json
import logging
import os
import ssl
import sys
import threading
import time
import wave
from typing import Optional

import numpy as np
import pyaudio
import websockets

# ── Configurazione ────────────────────────────────────────────────────────────

SAMPLE_RATE           = 16000
CHANNELS              = 1
CHUNK                 = 1024
SILENCE_THRESHOLD     = 150    # RMS soglia voce (abbassato per microfono lontano)
SILENCE_AFTER_SPEECH  = 1.5    # secondi di silenzio dopo parlato → stop
MAX_RECORD_SECONDS    = 15     # stop massimo registrazione
CONVERSATION_TIMEOUT  = 30     # secondi inattività → torna a wake word
WAKE_WORD_SCORE       = 0.5    # soglia openwakeword

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


# ── SSL context (ignora self-signed) ─────────────────────────────────────────

def make_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ── Wake Word ─────────────────────────────────────────────────────────────────

def load_wake_word_detector():
    try:
        from openwakeword.model import Model
        model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        log.info("✅ openwakeword caricato")
        return model
    except Exception as e:
        log.warning(f"openwakeword non disponibile ({e}), uso fallback SpeechRecognition")
        return None


class KeywordSpotter:
    def __init__(self):
        try:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            log.info("✅ SpeechRecognition caricato (fallback wake word)")
        except ImportError:
            self.recognizer = None
            log.warning("SpeechRecognition non disponibile")

    def detect(self, audio_bytes: bytes) -> bool:
        if not self.recognizer:
            return False
        try:
            import speech_recognition as sr
            audio = sr.AudioData(audio_bytes, SAMPLE_RATE, 2)
            text = self.recognizer.recognize_google(audio, language="it-IT").lower()
            return "jarvis" in text or "alexa" in text
        except Exception:
            return False


# ── Audio Utils ───────────────────────────────────────────────────────────────

def rms(data: bytes) -> float:
    arr = np.frombuffer(data, dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(arr * arr))) if len(arr) > 0 else 0.0


def pcm_to_wav(pcm_data: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def play_audio_bytes(audio_bytes: bytes):
    try:
        import soundfile as sf
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype="int16")
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1 if data.ndim == 1 else data.shape[1],
            rate=sr,
            output=True
        )
        stream.write(data.tobytes())
        stream.stop_stream()
        stream.close()
        pa.terminate()
    except Exception as e:
        log.warning(f"play_audio_bytes fallita: {e}")


def say_tts(text: str, server_http: str):
    try:
        import urllib.request
        url = server_http.rstrip("/") + "/tts/speak"
        body = json.dumps({"text": text}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10, context=make_ssl_ctx()) as resp:
            audio_bytes = resp.read()
        play_audio_bytes(audio_bytes)
    except Exception as e:
        log.warning(f"TTS fallita: {e}")


# ── Jarvis Client ─────────────────────────────────────────────────────────────

class JarvisClient:
    def __init__(self, server_ws: str, user_id: str):
        self.server_ws        = server_ws
        self.user_id          = user_id
        self.running          = False
        self.conversation_active = False
        self._last_interaction   = 0.0
        self.pa               = None
        self.oww_model        = None
        self.kw_spotter       = None

        self.server_http = server_ws.replace("wss://", "https://").replace("ws://", "https://")
        self.server_http = self.server_http.split("/ws/")[0]

    def setup(self):
        self.pa = pyaudio.PyAudio()
        self.oww_model = load_wake_word_detector()
        if not self.oww_model:
            self.kw_spotter = KeywordSpotter()
        log.info(f"🔌 Server: {self.server_ws} | User: {self.user_id}")

    def teardown(self):
        if self.pa:
            self.pa.terminate()

    # ── Loop principale ───────────────────────────────────────────────────────

    def run(self):
        self.running = True
        self.setup()
        log.info('🟢 Jarvis client avviato. Di\' "Hey Jarvis" per iniziare.')

        try:
            while self.running:
                try:
                    # Controlla se la conversazione è scaduta
                    if self.conversation_active:
                        elapsed = time.time() - self._last_interaction
                        if elapsed >= CONVERSATION_TIMEOUT:
                            log.info(f"⏱️ {CONVERSATION_TIMEOUT}s inattività, torno a wake word")
                            self.conversation_active = False

                    if self.conversation_active:
                        # Modalità conversazione: ascolta direttamente
                        log.info("👂 Conversazione attiva, ti ascolto...")
                        audio = self._record_command(wait_for_speech_timeout=10)
                        if audio:
                            self._last_interaction = time.time()
                            asyncio.run(self._send_and_play(audio))
                        else:
                            # Nessuna voce nel timeout → torna a wake word
                            log.info("💤 Nessuna voce, torno a wake word")
                            self.conversation_active = False
                    else:
                        # Modalità wake word
                        self._wait_for_wake_word()
                        if not self.running:
                            break
                        self.conversation_active = True
                        self._last_interaction = time.time()
                        say_tts("Dimmi", self.server_http)
                        audio = self._record_command()
                        if audio:
                            asyncio.run(self._send_and_play(audio))

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    log.error(f"Errore nel loop: {e}")
                    time.sleep(1)
        finally:
            self.teardown()
            log.info("🛑 Client fermato")

    # ── Wake word detection ───────────────────────────────────────────────────

    def _wait_for_wake_word(self):
        log.info('👂 In ascolto wake word...')
        oww_chunk = 1280
        stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=oww_chunk if self.oww_model else CHUNK
        )
        try:
            while self.running:
                if self.oww_model:
                    data = stream.read(oww_chunk, exception_on_overflow=False)
                    arr = np.frombuffer(data, dtype=np.int16)
                    prediction = self.oww_model.predict(arr)
                    for mdl, score in prediction.items():
                        if score > 0.3:
                            log.debug(f"Score {mdl}: {score:.3f}")
                        if score >= WAKE_WORD_SCORE:
                            log.info(f"🎯 Wake word rilevata (score={score:.2f})")
                            return
                else:
                    frames = []
                    for _ in range(int(SAMPLE_RATE / CHUNK * 2)):
                        frames.append(stream.read(CHUNK, exception_on_overflow=False))
                    audio_bytes = b"".join(frames)
                    if rms(audio_bytes) > SILENCE_THRESHOLD:
                        wav = pcm_to_wav(audio_bytes)
                        if self.kw_spotter and self.kw_spotter.detect(wav):
                            log.info("🎯 Wake word rilevata (keyword spotter)")
                            return
        finally:
            stream.stop_stream()
            stream.close()

    # ── Registrazione comando ─────────────────────────────────────────────────

    def _record_command(self, wait_for_speech_timeout: float = MAX_RECORD_SECONDS) -> Optional[bytes]:
        """
        Registra finché c'è voce + silenzio finale.
        wait_for_speech_timeout: secondi massimi ad aspettare che inizi il parlato.
        """
        log.info("🎤 Registrazione in corso...")
        stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK
        )

        frames = []
        has_speech = False
        silence_start = None
        speech_wait_start = time.time()
        start_time = time.time()

        try:
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                level = rms(data)

                if level > SILENCE_THRESHOLD:
                    has_speech = True
                    silence_start = None
                elif has_speech:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= SILENCE_AFTER_SPEECH:
                        log.info("🛑 Silenzio rilevato, stop registrazione")
                        break
                else:
                    # Nessuna voce ancora: controlla timeout di attesa
                    if time.time() - speech_wait_start >= wait_for_speech_timeout:
                        break

                if time.time() - start_time >= MAX_RECORD_SECONDS:
                    log.info("⏱️ Timeout registrazione")
                    break

        finally:
            stream.stop_stream()
            stream.close()

        if not has_speech:
            return None

        pcm = b"".join(frames)
        wav = pcm_to_wav(pcm)
        log.info(f"✅ Registrato {len(wav)} bytes ({len(frames) * CHUNK / SAMPLE_RATE:.1f}s)")
        return wav

    # ── Invia al server e riproduci risposta ──────────────────────────────────

    async def _send_and_play(self, wav_audio: bytes):
        log.info(f"📤 Invio audio al server...")
        ssl_ctx = make_ssl_ctx()

        try:
            async with websockets.connect(
                f"{self.server_ws}?user_id={self.user_id}",
                ping_interval=20,
                ping_timeout=10,
                open_timeout=10,
                ssl=ssl_ctx if self.server_ws.startswith("wss://") else None,
            ) as ws:
                await ws.send(json.dumps({"type": "audio_start"}))
                chunk_size = 4096
                for i in range(0, len(wav_audio), chunk_size):
                    await ws.send(wav_audio[i:i+chunk_size])
                await ws.send(json.dumps({"type": "audio_end"}))
                log.info("📤 Audio inviato, attendo risposta...")

                async for message in ws:
                    if isinstance(message, bytes):
                        log.info(f"🔊 Audio risposta ({len(message)} bytes), riproduco...")
                        # Riproduci in un thread bloccante così aspettiamo la fine
                        t = threading.Thread(target=play_audio_bytes, args=(message,), daemon=True)
                        t.start()
                        t.join()
                        self._last_interaction = time.time()
                        break
                    else:
                        data = json.loads(message)
                        t = data.get("type")
                        if t == "transcription":
                            log.info(f"📝 Trascrizione: {data.get('text')}")
                        elif t == "response":
                            log.info(f"💬 Risposta: {data.get('text')}")
                        elif t == "error":
                            log.error(f"❌ Errore server: {data.get('message')}")
                            break

        except Exception as e:
            log.error(f"❌ WebSocket error: {e}")


# ── Avvio ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Jarvis Native Client")
    parser.add_argument("--server", default=os.getenv("JARVIS_SERVER", "wss://192.168.1.131/ws/voice"))
    parser.add_argument("--user",   default=os.getenv("JARVIS_USER",   "pc_client"))
    args = parser.parse_args()

    client = JarvisClient(server_ws=args.server, user_id=args.user)
    try:
        client.run()
    except KeyboardInterrupt:
        client.running = False
        log.info("Interrupted")
