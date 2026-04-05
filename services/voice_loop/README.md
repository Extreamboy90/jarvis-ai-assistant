# JARVIS Voice Loop

Loop vocale continuo per assistente vocale in stile Jarvis/Iron Man.

## Funzionalità

**Pipeline completa in un unico processo:**

```
Microfono
    ↓
VAD (Voice Activity Detection) - WebRTC VAD
    ↓
Wake Word Detection - OpenWakeWord ("Jarvis")
    ↓
Speech-to-Text - Faster Whisper
    ↓
LLM Processing - Orchestrator (Gemini/Ollama)
    ↓
Text-to-Speech - Piper TTS
    ↓
Altoparlante
    ↓
Loop automatico (torna ad ascoltare)
```

## Componenti

### 1. VAD (Voice Activity Detection)
- **WebRTC VAD** - Rileva automaticamente quando l'utente parla
- Riduce elaborazione quando c'è silenzio
- Modalità aggressiva (3) per ridurre falsi positivi

### 2. Wake Word Detection
- **OpenWakeWord** con modello "jarvis"
- Attivazione solo quando sente "Jarvis"
- Soglia di confidenza: 0.5 (configurabile)

### 3. Speech-to-Text (STT)
- **Faster Whisper** (small model)
- Ottimizzato per italiano
- VAD integrato per migliorare accuratezza

### 4. LLM Processing
- Comunica con Orchestrator via HTTP
- Supporta Gemini API e Ollama locale
- Function calling disponibile

### 5. Text-to-Speech (TTS)
- **Piper TTS** con voce italiana (Paola)
- Generazione locale, nessuna API cloud
- Bassa latenza

### 6. Audio I/O
- **sounddevice** per riproduzione
- **pyaudio** per registrazione
- Supporto ALSA per Linux

## Utilizzo

### Avvio del servizio

```bash
# Build e avvio
docker-compose up -d --build voice-loop

# Verifica logs
docker-compose logs -f voice-loop
```

### Flusso di utilizzo

1. Il servizio parte in ascolto continuo
2. Dire **"Jarvis"** per attivare
3. Il sistema emette un beep (feedback)
4. Pronunciare il comando (es: "che ore sono?")
5. Aspettare la risposta vocale
6. Il sistema torna automaticamente in ascolto

### Esempio di conversazione

```
[Sistema in ascolto...]
Utente: "Jarvis"
[Sistema attivato - beep]
Utente: "Dimmi le ultime notizie sulla Formula 1"
Jarvis: [ricerca web e risponde vocalmente]
[Sistema torna in ascolto automaticamente]
```

## Configurazione

Variabili d'ambiente in `docker-compose.yml`:

```yaml
environment:
  - ORCHESTRATOR_URL=http://orchestrator:8000  # URL orchestrator
  - USER_ID=jarvis_voice_user                   # User ID per memoria
  - WHISPER_MODEL=small                         # tiny/base/small/medium
  - WHISPER_DEVICE=cpu                          # cpu/cuda
  - WHISPER_COMPUTE_TYPE=int8                   # int8/float16
  - PIPER_VOICE=it_IT-paola-medium              # Voce italiana
```

### Parametri VAD (in jarvis_loop.py)

```python
VAD_MODE = 3                    # Aggressività (0-3)
SPEECH_PADDING_MS = 300         # Padding audio
SILENCE_DURATION_MS = 900       # Silenzio per fine comando
```

### Parametri Wake Word

```python
WAKE_WORD = "jarvis"            # Wake word
WAKE_WORD_THRESHOLD = 0.5       # Soglia confidenza (0-1)
```

## Requisiti Hardware

### Audio
- Microfono funzionante
- Altoparlante/cuffie
- Accesso a `/dev/snd` (device audio Linux)

### Risorse
- CPU: 2+ core (per Whisper + VAD)
- RAM: 2GB+ (modello small Whisper ~500MB)
- Disco: ~1GB (modelli + dipendenze)

## Troubleshooting

### Nessun audio in input/output

```bash
# Verifica dispositivi audio sul host
aplay -l
arecord -l

# Testa microfono
arecord -d 5 test.wav
aplay test.wav

# Verifica permessi Docker
docker exec -it jarvis-voice-loop arecord -l
```

### Wake word non rilevato

- Aumenta volume microfono
- Abbassa `WAKE_WORD_THRESHOLD` a 0.3
- Parla più chiaramente e lentamente
- Verifica logs: `docker logs jarvis-voice-loop`

### VAD troppo sensibile

- Aumenta `VAD_MODE` a 3 (max aggressività)
- Aumenta `SILENCE_DURATION_MS` a 1200ms
- Riduci rumore ambientale

### Whisper troppo lento

- Usa modello `tiny` invece di `small`
- Cambia `WHISPER_COMPUTE_TYPE` a `int8`
- Considera GPU se disponibile (`WHISPER_DEVICE=cuda`)

### TTS non funziona

```bash
# Verifica modello Piper scaricato
docker exec jarvis-voice-loop ls -lh /models/

# Testa Piper manualmente
docker exec -it jarvis-voice-loop piper --model /models/it_IT-paola-medium.onnx <<< "Test audio"
```

## Personalizzazione

### Cambiare wake word

OpenWakeWord supporta varie wake word pre-addestrate:
- `alexa`
- `hey_jarvis`
- `hey_mycroft`
- `hey_rhasspy`

Modifica `WAKE_WORD` in `jarvis_loop.py`.

### Cambiare voce TTS

Voci italiane disponibili:
- `it_IT-paola-medium` (donna, qualità media)
- `it_IT-riccardo-x_low` (uomo, veloce ma bassa qualità)

Modifica `PIPER_VOICE` in docker-compose.

### Aggiungere beep di feedback

Nel metodo `listen_for_wake_word()`, dopo rilevamento:

```python
if self.detect_wake_word(audio_buffer):
    # Riproduci beep
    beep = np.sin(2 * np.pi * 800 * np.arange(0, 0.2, 1/SAMPLE_RATE))
    sd.play(beep, SAMPLE_RATE)
    sd.wait()
    return True
```

## Performance

Latenze tipiche (CPU):
- Wake word detection: ~50ms/chunk
- VAD: ~5ms/chunk
- STT (3s audio): ~500ms
- LLM: 1-3s (Gemini) / 5-30s (Ollama locale)
- TTS: ~200ms

**Latenza totale**: ~2-5s per risposta completa (con Gemini).

## Architettura

**Vantaggi rispetto a 3 servizi separati:**

✅ Nessun overhead HTTP tra STT/TTS
✅ Memoria condivisa per audio
✅ Loop automatico senza polling
✅ VAD integrato riduce CPU usage
✅ Wake word evita elaborazione continua
✅ Un solo container da gestire

## Prossimi miglioramenti

- [ ] Streaming STT (real-time)
- [ ] Streaming TTS (parlare mentre genera)
- [ ] Wake word personalizzabile (training custom)
- [ ] Supporto multi-lingua
- [ ] Barge-in (interrompere Jarvis mentre parla)
- [ ] Noise cancellation avanzata
- [ ] Riconoscimento speaker (multi-utente)
