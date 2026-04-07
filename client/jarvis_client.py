"""
Jarvis Native Client
Gira in background su Windows/Mac/Linux.
Flusso: wake word → registra → invia a /ws/voice → riproduce risposta TTS → ripete
"""

import asyncio
import io
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import time
import wave

import numpy as np
import pyaudio
import websockets

# ── Configurazione ────────────────────────────────────────────────────────────

SERVER_URL  = os.getenv("JARVIS_SERVER", "ws://192.168.1.131/ws/voice")
USER_ID     = os.getenv("JARVIS_USER",   "pc_client")
SAMPLE_RATE = 16000
CHANNELS    = 1
CHUNK       = 1024

# Soglia RMS per silence detection (0-32767, più basso = più sensibile)
SILENCE_THRESHOLD = 300
# Secondi di silenzio dopo il parlato per fermare la registrazione
SILENCE_AFTER_SPEECH = 1.5
# Secondi massimi di registrazione
MAX_RECORD_SECONDS = 15

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)


# ── Wake Word ─────────────────────────────────────────────────────────────────

def load_wake_word_detector():
    """Carica openwakeword se disponibile, altrimenti usa keyword spotting semplice."""
    try:
        from openwakeword.model import Model
        model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        log.info("✅ openwakeword caricato")
        return model
    except Exception as e:
        log.warning(f"openwakeword non disponibile ({e}), uso keyword VAD semplice")
        return None


class KeywordSpotter:
    """Fallback: speech_recognition offline per wake word detection."""
    def __init__(self):
        try:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            self.sr = sr
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
            log.debug(f"Keyword check: '{text}'")
            return "jarvis" in text or "alexa" in text
        except Exception:
            return False


# ── Audio Utils ───────────────────────────────────────────────────────────────

def rms(data: bytes) -> float:
    arr = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(arr ** 2))) if len(arr) > 0 else 0.0


def pcm_to_wav(pcm_data: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def play_audio_bytes(audio_bytes: bytes):
    """Riproduce audio WAV/PCM tramite PyAudio."""
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
    """Chiede al server TTS e riproduce la risposta (fallback se WS non porta audio)."""
    try:
        import urllib.request
        url = server_http.rstrip("/") + "/tts/speak"
        body = json.dumps({"text": text}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            audio_bytes = resp.read()
        play_audio_bytes(audio_bytes)
    except Exception as e:
        log.warning(f"TTS fallita: {e}")


# ── Jarvis Client ─────────────────────────────────────────────────────────────

class JarvisClient:
    def __init__(self, server_ws: str, user_id: str):
        self.server_ws   = server_ws
        self.user_id     = user_id
        self.running     = False
        self.pa          = None
        self.oww_model   = None
        self.kw_spotter  = None

        # URL HTTP ricavato dal WS
        self.server_http = server_ws.replace("wss://", "https://").replace("ws://", "http://")
        self.server_http = self.server_http.split("/ws/")[0]

    def setup(self):
        self.pa = pyaudio.PyAudio()
        self.oww_model  = load_wake_word_detector()
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
                    self._wait_for_wake_word()
                    if not self.running:
                        break
                    self._say_confirm()
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
        stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        # openwakeword lavora con chunk da 1280 campioni @ 16kHz
        oww_chunk = 1280

        try:
            while self.running:
                if self.oww_model:
                    data = stream.read(oww_chunk, exception_on_overflow=False)
                    arr = np.frombuffer(data, dtype=np.int16)
                    prediction = self.oww_model.predict(arr)
                    for mdl, score in prediction.items():
                        if score > 0.5:
                            log.info(f"🎯 Wake word rilevata (score={score:.2f})")
                            return
                else:
                    # Fallback: accumula 2 secondi e controlla keyword
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

    def _say_confirm(self):
        """Dice 'Dimmi' tramite TTS server."""
        log.info("🗣️ Dico Dimmi...")
        say_tts("Dimmi", self.server_http)

    # ── Registrazione comando ─────────────────────────────────────────────────

    def _record_command(self) -> bytes | None:
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
                        log.info(f"🛑 Silenzio rilevato, stop registrazione")
                        break

                if time.time() - start_time >= MAX_RECORD_SECONDS:
                    log.info("⏱️ Timeout registrazione")
                    break

        finally:
            stream.stop_stream()
            stream.close()

        if not has_speech:
            log.warning("⚠️ Nessuna voce registrata")
            return None

        pcm = b"".join(frames)
        wav = pcm_to_wav(pcm)
        log.info(f"✅ Registrato {len(wav)} bytes ({len(frames) * CHUNK / SAMPLE_RATE:.1f}s)")
        return wav

    # ── Invia al server e riproduci risposta ──────────────────────────────────

    async def _send_and_play(self, wav_audio: bytes):
        log.info(f"📤 Invio audio al server ({self.server_ws})...")
        try:
            async with websockets.connect(
                f"{self.server_ws}?user_id={self.user_id}",
                ping_interval=20,
                ping_timeout=10,
                open_timeout=10,
            ) as ws:
                # Protocollo: audio_start → bytes → audio_end
                await ws.send(json.dumps({"type": "audio_start"}))
                # Invia in chunk
                chunk_size = 4096
                for i in range(0, len(wav_audio), chunk_size):
                    await ws.send(wav_audio[i:i+chunk_size])
                await ws.send(json.dumps({"type": "audio_end"}))
                log.info("📤 Audio inviato, attendo risposta...")

                # Ricevi risposta
                async for message in ws:
                    if isinstance(message, bytes):
                        log.info(f"🔊 Audio risposta ricevuto ({len(message)} bytes), riproduco...")
                        threading.Thread(
                            target=play_audio_bytes, args=(message,), daemon=True
                        ).start()
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
    parser.add_argument("--server",  default=os.getenv("JARVIS_SERVER", "ws://192.168.1.131/ws/voice"))
    parser.add_argument("--user",    default=os.getenv("JARVIS_USER",   "pc_client"))
    args = parser.parse_args()

    client = JarvisClient(server_ws=args.server, user_id=args.user)
    try:
        client.run()
    except KeyboardInterrupt:
        client.running = False
        log.info("Interrupted")
