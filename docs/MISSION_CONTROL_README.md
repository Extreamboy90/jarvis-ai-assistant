# Mission Control - Dashboard Contestuale Proattiva

## Panoramica

**Mission Control** è un sistema di briefing personalizzato stile Jarvis che genera automaticamente report mattutini combinando:

- 📅 **Calendario** (Google Calendar)
- 🌤️ **Meteo** (OpenWeatherMap API)
- 🏠 **Smart Home** (Tuya devices)
- 📰 **Notizie** (NewsAPI, personalizzate su interessi utente)
- 🚗 **Traffico** (Google Maps API o stime statiche)
- 🧠 **Routine apprese** (analisi pattern comportamentali)
- 💡 **Suggerimenti proattivi** (ottimizzazioni contestuali)

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                     Mission Control                          │
│                  (context_dashboard.py)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────▼────┐    ┌───▼────┐    ┌───▼────┐
   │Calendar │    │ Weather│    │  Home  │
   │Plugin   │    │  API   │    │ Plugin │
   └─────────┘    └────────┘    └────────┘
        │              │              │
   ┌────▼────┐    ┌───▼────┐    ┌───▼────┐
   │  News   │    │Traffic │    │Routine │
   │  API    │    │  API   │    │Analysis│
   └─────────┘    └────────┘    └────────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
                  ┌────▼─────┐
                  │   LLM    │
                  │(Gemini/  │
                  │ Ollama)  │
                  └──────────┘
                       │
              ┌────────┼────────┐
              │                 │
         ┌────▼─────┐     ┌────▼─────┐
         │ Briefing │     │   TTS    │
         │   JSON   │     │  Audio   │
         └──────────┘     └──────────┘
```

## File Implementati

### 1. Plugin Principale
- **`services/orchestrator/plugins/context_dashboard.py`** (770 righe)
  - `generate_morning_briefing()` - Briefing completo
  - `get_daily_context()` - Raccolta dati JSON
  - `analyze_routine_patterns()` - Analisi comportamentale
  - `get_personalized_news()` - Notizie personalizzate
  - `calculate_commute_time()` - Calcolo traffico
  - `suggest_daily_optimizations()` - Suggerimenti proattivi

### 2. Estensioni Plugin Esistenti
- **`services/orchestrator/plugins/calendar.py`**
  - `get_today_schedule_summary()` - Riassunto eventi giornalieri

- **`services/orchestrator/plugins/web_search.py`**
  - `get_weather_forecast()` - Meteo con OpenWeatherMap API + fallback web search

- **`services/orchestrator/plugins/tuya.py`**
  - `get_home_status_summary()` - Stato aggregato smart home (luci, temp, energia)

### 3. Endpoint FastAPI
- **`services/orchestrator/app.py`** (modifiche righe 94, 766-910)
  - `GET /dashboard/{user_id}/context` - Dati JSON grezzi
  - `GET /dashboard/{user_id}/briefing` - Briefing strutturato
  - `POST /dashboard/{user_id}/briefing/tts` - Briefing audio WAV

### 4. Configurazione
- **`.env.example`** - Template chiavi API con documentazione completa
- **`docs/MISSION_CONTROL_EXAMPLE.md`** - Esempi output e use cases

## Setup

### 1. Copia .env.example

```bash
cp .env.example .env
```

### 2. Configura API Keys (opzionali)

```bash
# Meteo (gratuito, 1000 call/day)
OPENWEATHER_API_KEY=your_key_here  # https://openweathermap.org/api

# Notizie (gratuito, 100 call/day)
NEWSAPI_KEY=your_key_here  # https://newsapi.org/

# Traffico (opzionale, richiede carta)
GOOGLE_MAPS_API_KEY=your_key_here  # https://console.cloud.google.com
```

**NOTA:** Il sistema funziona anche SENZA queste API (usa fallback automatici).

### 3. Rebuild Orchestrator

```bash
docker-compose up -d --build orchestrator
```

### 4. Verifica Plugin Caricato

```bash
docker-compose logs orchestrator | grep context_dashboard
```

Output atteso:
```
✅ Plugin loaded: context_dashboard
Registered function: context_dashboard_generate_morning_briefing
Registered function: context_dashboard_get_daily_context
...
```

## Usage

### 1. Briefing JSON

```bash
curl "http://localhost:8000/dashboard/test_user/briefing?time=morning&location=Cagliari"
```

**Output:** JSON strutturato con tutte le sezioni (vedi `MISSION_CONTROL_EXAMPLE.md`)

### 2. Briefing Audio

```bash
curl -X POST "http://localhost:8000/dashboard/test_user/briefing/tts?time=morning" \
  --output briefing.wav

# Riproduci
aplay briefing.wav  # Linux
# o
afplay briefing.wav  # macOS
```

### 3. Solo Dati Grezzi

```bash
curl "http://localhost:8000/dashboard/test_user/context?location=Milan"
```

**Output:** JSON con dati non processati (calendario, meteo, casa, routine, news)

### 4. Via Chat LLM

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user","message":"dammi il briefing mattutino"}'
```

L'LLM chiamerà automaticamente `context_dashboard_generate_morning_briefing()` e formattera la risposta in linguaggio naturale.

## Componenti

### Cache Layer

Sistema di cache intelligente per ridurre chiamate API:

| Risorsa | TTL | Motivo |
|---------|-----|--------|
| Meteo | 1 ora | Dati stabili, limiti API |
| Notizie | 30 min | Aggiornamento medio-frequente |
| Traffico | 15 min | Dati dinamici |
| Routine | 24 ore | Pattern stabili |

**Vantaggi:**
- Latenza: da 3s → <500ms (richieste successive)
- Risparmio: -80% chiamate API
- Fallback automatico se API offline

### Routine Analysis

Analizza pattern comportamentali da:
- **Interactions** (ultimi 30 giorni)
  - Orari di picco attività
  - Giorni più attivi
  - Azioni comuni

- **Memory Snippets**
  - Preferenze personali
  - Interessi
  - Fatti importanti

**Output:**
```json
{
  "peak_hours": [8, 18, 21],
  "most_active_day": "Lunedi",
  "total_interactions_30d": 247,
  "preferences": [
    {"text": "Tifoso del Cagliari", "importance": 8},
    {"text": "Lavora in energia", "importance": 9}
  ]
}
```

### Personalized News

Filtra notizie basandosi su:
1. **Keyword extraction** dalle memorie utente
2. **NewsAPI query** con interessi
3. **Fallback** a notizie generali Italia se nessun interesse

**Esempio:**
- Memoria: "Tifoso del Cagliari", "Lavora in energia"
- Query NewsAPI: `calcio OR energia`
- Risultato: Articoli rilevanti personalizzati

### Suggerimenti Proattivi

Sistema di recommendation basato su contesto:

| Condizione | Suggerimento |
|------------|--------------|
| Evento tra <1h | ⏰ Hai '{evento}' tra {minuti} minuti |
| Evento con location | 📍 Ricorda: l'evento è a {luogo} |
| Temp < 10°C | 🧥 Porta giacca pesante |
| Temp < 15°C | 🧥 Fa freschetto - porta giacca |
| Temp > 30°C | ☀️ Caldo intenso - idratati |
| Pioggia prevista | ☔ Porta ombrello |
| Luci accese (9-18h) | 💡 {N} luci accese di giorno |
| Peak hour corrente | 📊 Sei più produttivo ora |
| Interesse calcio | ⚽ Verifica partita squadra |

## Integrations

### Telegram Bot

```python
@bot.message_handler(commands=['briefing'])
def send_briefing(message):
    user_id = str(message.from_user.id)

    response = requests.get(
        f"http://orchestrator:8000/dashboard/{user_id}/briefing",
        params={"time": "morning"}
    )

    briefing = response.json()
    bot.send_message(message.chat.id, briefing["voice_text"])
```

### PWA Dashboard

```javascript
async function loadDashboard(userId) {
    const context = await fetch(`/dashboard/${userId}/context`);
    const data = await context.json();

    renderWeatherWidget(data.weather);
    renderCalendarWidget(data.calendar);
    renderHomeWidget(data.home);
    renderNewsWidget(data.news);
}

async function playBriefing(userId) {
    const audio = await fetch(`/dashboard/${userId}/briefing/tts?time=morning`, {
        method: 'POST'
    });
    const blob = await audio.blob();
    new Audio(URL.createObjectURL(blob)).play();
}
```

### Home Automation

```yaml
# Home Assistant automation.yaml
automation:
  - alias: "Morning Briefing"
    trigger:
      platform: time
      at: "07:30:00"
    action:
      - service: shell_command.jarvis_briefing
      - service: media_player.play_media
        data:
          entity_id: media_player.bedroom_speaker
          media_content_id: "/tmp/briefing.wav"
```

## API Reference

### GET /dashboard/{user_id}/context

Recupera dati grezzi contestuali.

**Query Params:**
- `location` (string, optional): Città per meteo/notizie. Default: "Cagliari"

**Response:**
```json
{
  "timestamp": "ISO 8601",
  "user_id": "string",
  "location": "string",
  "calendar": {...},
  "weather": {...},
  "home": {...},
  "routine": {...},
  "news": {...}
}
```

### GET /dashboard/{user_id}/briefing

Genera briefing strutturato.

**Query Params:**
- `time` (string): "morning" | "evening". Default: "morning"
- `location` (string, optional): Città. Default: "Cagliari"
- `work_location` (string, optional): Destinazione per calcolo traffico

**Response:**
```json
{
  "success": true,
  "timestamp": "ISO 8601",
  "user_id": "string",
  "greeting": "string",
  "datetime": "string",
  "weather": {...},
  "calendar": {...},
  "home": {...},
  "news": {...},
  "commute": {...},
  "suggestions": ["string"],
  "routine_insights": {...},
  "voice_text": "string"
}
```

### POST /dashboard/{user_id}/briefing/tts

Genera briefing e converte in audio.

**Query Params:**
- `time` (string): "morning" | "evening"

**Response:**
- `Content-Type: audio/wav`
- File WAV con sintesi vocale del briefing

## Performance

### Benchmark (sistema completo)

| Scenario | Latenza | Note |
|----------|---------|------|
| Prima chiamata (cold) | ~3.5s | Tutte le API + LLM |
| Cache hit | <500ms | Dati cached |
| Solo JSON (no TTS) | ~800ms | Include LLM reasoning |
| Solo TTS | ~2s | Piper synthesis |

### Ottimizzazioni Applicate

1. **Cache multi-layer** (Redis-like in-memory)
2. **Async operations** (chiamate API parallele)
3. **Smart fallback** (dati mock se API offline)
4. **Lazy loading** (carica solo dati richiesti)
5. **Pre-check routine** (evita analisi inutili)

## Fallback Strategy

Il sistema è progettato per **graceful degradation**:

| API Mancante | Fallback |
|--------------|----------|
| OpenWeatherMap | Dati mock (20°C, "non disponibile") |
| NewsAPI | Array vuoto, nessuna notizia |
| Google Maps | Stima statica basata su ora |
| Google Calendar | "Nessun evento oggi" |
| Tuya API | "Nessun dispositivo configurato" |

**Risultato:** Il briefing viene sempre generato, anche con 0 API configurate.

## Security & Privacy

### Dati Sensibili
- **API Keys:** Memorizzate SOLO in `.env` locale
- **Non inviate** a servizi esterni (tranne le API stesse)
- **Cache:** In-memory, cancellata al restart

### GDPR Compliance
- Dati meteo/notizie: **Pubblici**, nessun dato personale
- Traffico: **Anonimo**, solo coordinate geo
- Calendario: **Privato**, OAuth2 con permessi read-only
- Smart Home: **Locale**, nessun dato inviato a cloud (se Tuya locale)

### Audit Trail
Tutte le chiamate loggato in `interactions` table:
```sql
SELECT * FROM interactions
WHERE user_id = 'test_user'
  AND action = 'dashboard_briefing'
ORDER BY created_at DESC;
```

## Troubleshooting

### Plugin non caricato
```bash
# Verifica PLUGINS_TO_LOAD in app.py
grep "context_dashboard" services/orchestrator/app.py

# Rebuild
docker-compose up -d --build orchestrator

# Check logs
docker-compose logs orchestrator | grep -i error
```

### Meteo non funziona
```bash
# Verifica chiave API
docker exec jarvis-orchestrator printenv | grep OPENWEATHER

# Test manuale API
curl "http://api.openweathermap.org/data/2.5/weather?q=Rome&appid=YOUR_KEY&units=metric"

# Fallback: usa web search
# (automatico se OPENWEATHER_API_KEY non configurata)
```

### Calendario vuoto
```bash
# Verifica OAuth token
docker exec jarvis-orchestrator ls -la /app/calendar_token.pickle

# Riautorizza
docker exec -it jarvis-orchestrator python3 -c "
from plugins.calendar import list_events
print(list_events(days_ahead=1))
"
```

### Briefing audio non generato
```bash
# Verifica TTS service
curl http://localhost:8002/health

# Test TTS manuale
curl -X POST http://localhost:8002/speak \
  -H "Content-Type: application/json" \
  -d '{"text":"Test audio"}' \
  --output test.wav
```

## Roadmap

### Implementato ✅
- [x] Morning briefing completo
- [x] Integrazione calendario
- [x] Meteo con fallback
- [x] Smart home status
- [x] Routine analysis
- [x] Notizie personalizzate
- [x] Calcolo traffico (statico + API)
- [x] Suggerimenti proattivi
- [x] Cache layer
- [x] TTS audio output

### Prossimi Step 📝
- [ ] Evening briefing (recap giornata)
- [ ] Weekend briefing (suggerimenti svago/tempo libero)
- [ ] Integrazione fitness tracker (Strava, Garmin, Apple Health)
- [ ] Integrazione email (Gmail API, inbox summary)
- [ ] Integrazione finanza (crypto prices, stock alerts)
- [ ] Multi-language support (EN, ES, FR)
- [ ] Voice shortcuts ("Hey Jarvis, briefing")
- [ ] Push notifications (FCM, APNs)
- [ ] Dashboard web frontend (React/Vue)
- [ ] Mobile app (Flutter/React Native)

### Future Enhancements 💡
- [ ] ML-based routine prediction
- [ ] Anomaly detection (pattern irregolari)
- [ ] Sentiment analysis su notizie
- [ ] Natural language time parsing ("domani mattina alle 8")
- [ ] Context-aware automation triggers
- [ ] Integration con task manager (Todoist, Notion)
- [ ] Social media summary (Twitter, LinkedIn)
- [ ] Podcast briefing personalizzato

## Credits

**Developed by:** Alessandro (AI Assistant Project)
**Framework:** FastAPI + Ollama/Gemini
**Voice:** Piper TTS (Italian - Paola voice)
**Inspired by:** Jarvis (Iron Man) - Mission Control concept

## License

Part of Jarvis AI Assistant - Private Project

---

**Need Help?**
- 📖 Vedi esempi completi: `docs/MISSION_CONTROL_EXAMPLE.md`
- 🔧 Configurazione API: `.env.example`
- 🐛 Issues: Check orchestrator logs
- 💬 Telegram: Usa comando `/briefing` per test rapido
