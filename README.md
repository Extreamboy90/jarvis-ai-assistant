# Jarvis AI Assistant

Assistente AI vocale personale offline, simile a Jarvis di Iron Man.

## Caratteristiche

- 🎤 **Speech-to-Text** con Faster Whisper (italiano)
- 🔊 **Text-to-Speech** con Piper TTS (voci italiane)
- 🧠 **LLM** con Ollama (llama3.1 o mistral)
- 🔌 **Function Calling** - Sistema plugin modulare
- 💬 **Telegram Bot** - Interfaccia utente comoda
- 🏠 **Integrazione Tuya** - Controllo domotica
- 🔒 **Completamente Offline** - Nessuna dipendenza cloud

## Architettura

```
┌─────────────┐
│ Telegram    │
│ Bot         │
└──────┬──────┘
       │
┌──────▼──────────┐
│ Orchestrator    │
│ + Plugins       │◄──────┐
└────┬───┬────────┘       │
     │   │                │
 ┌───▼───▼────┐      ┌────▼────┐
 │ STT | TTS  │      │ Ollama  │
 │ Service    │      │ LLM     │
 └────────────┘      └─────────┘
```

### Componenti:

1. **STT Service** (porta 8001)
   - Faster Whisper per trascrizione vocale
   - Supporto italiano ottimizzato

2. **TTS Service** (porta 8002)
   - Piper TTS per sintesi vocale
   - Voce italiana naturale

3. **Orchestrator** (porta 8000)
   - Core dell'assistente
   - Gestione conversazioni
   - Function calling con plugins
   - API REST

4. **Telegram Bot**
   - Interfaccia utente principale
   - Supporto messaggi testuali e vocali
   - Comandi per gestione assistente

## Setup

### 1. Prerequisiti

- Docker e Docker Compose
- Ollama installato e in esecuzione
- Token bot Telegram (da @BotFather)

### 2. Configurazione Ollama

```bash
# Scarica il modello (se non già presente)
docker exec ollama ollama pull llama3.1:8b
```

### 3. Configurazione Telegram Bot

1. Apri Telegram e cerca @BotFather
2. Crea un nuovo bot con `/newbot`
3. Copia il token fornito
4. Modifica il file `.env` e inserisci il token:

```bash
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 4. Avvio servizi

```bash
cd ai-assistant
docker-compose up -d --build
```

### 5. Verifica stato

```bash
# Controlla i container
docker-compose ps

# Verifica logs
docker-compose logs -f

# Test API orchestrator
curl http://localhost:8000/health
```

## Utilizzo

### Telegram Bot

1. Cerca il tuo bot su Telegram
2. Invia `/start` per iniziare
3. Invia messaggi testuali o vocali

**Comandi disponibili:**
- `/start` - Messaggio di benvenuto
- `/help` - Aiuto
- `/clear` - Cancella cronologia conversazione
- `/functions` - Mostra funzioni disponibili

**Esempi:**
- "Che ore sono?"
- "Accendi la luce del salotto"
- "Quali dispositivi smart ho?"
- "Dammi informazioni sul sistema"

### API REST

```bash
# Chat testuale
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Ciao, come stai?",
    "user_id": "test_user"
  }'

# Trascrivi audio
curl -X POST http://localhost:8001/transcribe \
  -F "audio=@messaggio.ogg"

# Genera audio
curl -X POST http://localhost:8002/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Ciao, sono Jarvis!"}' \
  --output risposta.wav
```

## Plugins

Il sistema supporta plugins per estendere le funzionalità.

### Plugin esistenti:

**system.py** - Funzioni di sistema
- `get_current_time` - Data e ora corrente
- `execute_command` - Esegui comandi sicuri
- `get_system_info` - Info sistema (CPU, RAM, disco)

**tuya.py** - Controllo domotica
- `get_devices` - Lista dispositivi
- `get_device_status` - Stato dispositivo
- `control_device` - Controlla dispositivo
- `turn_on_light` / `turn_off_light` - Accendi/spegni luci

### Creare un plugin:

```python
# services/orchestrator/plugins/myplugin.py

from plugins import function

@function(
    name="my_function",
    description="Descrizione della funzione",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Parametro 1"}
        },
        "required": ["param1"]
    }
)
def my_function(param1: str):
    """La tua funzione"""
    return {"result": f"Hai passato: {param1}"}
```

Poi aggiungi il plugin in `services/orchestrator/app.py`:

```python
PLUGINS_TO_LOAD = ["system", "tuya", "myplugin"]
```

## Configurazione

Variabili d'ambiente disponibili (`.env`):

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_token

# Ollama
OLLAMA_MODEL=llama3.1:8b  # o mistral:7b

# Whisper STT
WHISPER_MODEL=small       # tiny, base, small, medium, large-v2
WHISPER_DEVICE=cpu        # cpu o cuda
WHISPER_COMPUTE_TYPE=int8 # int8, float16, float32

# Piper TTS
PIPER_VOICE=it_IT-riccardo-x_low

# Tuya
TUYA_API_URL=http://tuya-api:5000
```

## Troubleshooting

### Il bot non risponde
```bash
# Controlla i logs
docker-compose logs telegram-bot

# Verifica il token
echo $TELEGRAM_BOT_TOKEN
```

### STT/TTS lento
- Usa modelli più leggeri (tiny, base per Whisper)
- Considera GPU per Whisper (WHISPER_DEVICE=cuda)

### Ollama non raggiungibile
```bash
# Verifica che Ollama sia in esecuzione
docker ps | grep ollama

# Verifica che il modello sia scaricato
docker exec ollama ollama list
```

### Plugin non caricato
```bash
# Controlla logs orchestrator
docker-compose logs orchestrator | grep Plugin
```

## Sviluppo

### Struttura directory

```
ai-assistant/
├── services/
│   ├── stt/              # Faster Whisper
│   │   ├── Dockerfile
│   │   ├── app.py
│   │   └── requirements.txt
│   ├── tts/              # Piper TTS
│   │   ├── Dockerfile
│   │   ├── app.py
│   │   └── requirements.txt
│   └── orchestrator/     # Core + Telegram Bot
│       ├── Dockerfile
│       ├── app.py
│       ├── telegram_bot.py
│       ├── plugins/
│       │   ├── __init__.py
│       │   ├── tuya.py
│       │   └── system.py
│       └── requirements.txt
├── docker-compose.yml
├── .env
└── README.md
```

### Rebuild dopo modifiche

```bash
# Rebuild singolo servizio
docker-compose up -d --build orchestrator

# Rebuild tutto
docker-compose up -d --build
```

### Test manuale componenti

```bash
# Test STT
curl -X POST http://localhost:8001/health

# Test TTS
curl -X POST http://localhost:8002/health

# Test Orchestrator
curl http://localhost:8000/health
curl http://localhost:8000/functions
```

## Roadmap

- [ ] Supporto GPU per Whisper
- [ ] Più voci Piper (femminili/maschili)
- [ ] Web UI oltre a Telegram
- [ ] Plugin per Home Assistant
- [ ] Plugin per calendario/promemoria
- [ ] Streaming audio real-time
- [ ] Multi-utente con autenticazione

## Licenza

MIT

## Credits

- [Faster Whisper](https://github.com/guillaumekln/faster-whisper)
- [Piper TTS](https://github.com/rhasspy/piper)
- [Ollama](https://ollama.ai/)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
