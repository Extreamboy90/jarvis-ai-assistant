# Mission Control - Esempio Briefing Output

## Endpoint API

### 1. GET /dashboard/{user_id}/briefing

**Request:**
```bash
GET http://localhost:8000/dashboard/alessandro/briefing?time=morning&location=Cagliari&work_location=Assemini
```

**Response JSON (esempio):**

```json
{
  "success": true,
  "timestamp": "2026-03-30T07:30:00.123456",
  "user_id": "alessandro",
  "greeting": "Buongiorno, Alessandro",
  "datetime": "Domenica 30 Marzo 2026, ore 07:30",

  "weather": {
    "summary": "18°C, cielo sereno",
    "details": {
      "success": true,
      "location": "Cagliari",
      "temperature": 18,
      "feels_like": 17,
      "description": "cielo sereno",
      "humidity": 65,
      "wind_speed": 12,
      "icon": "01d"
    }
  },

  "calendar": {
    "success": true,
    "events": [
      {
        "summary": "Riunione Team Energia",
        "start": "2026-03-30T10:00:00+01:00",
        "location": "Ufficio Assemini",
        "description": "Revisione progetti Q1"
      },
      {
        "summary": "Pranzo con Marco",
        "start": "2026-03-30T13:30:00+01:00",
        "location": "Ristorante Su Nuraxi",
        "description": ""
      }
    ],
    "total_events": 2,
    "summary": "2 eventi oggi"
  },

  "home": {
    "success": true,
    "total_devices": 8,
    "lights_on": 2,
    "lights_off": 4,
    "temperature": 21.5,
    "energy_consumption": 245.3,
    "devices": [
      {"name": "Luce Cucina", "type": "light", "status": "on"},
      {"name": "Luce Salotto", "type": "light", "status": "on"},
      {"name": "Termostato", "type": "temperature", "value": 21.5}
    ],
    "summary": "2 luci accese, temperatura 21.5°C, consumo 245W"
  },

  "commute": {
    "success": true,
    "from": "Cagliari",
    "to": "Assemini",
    "duration_minutes": 28,
    "duration_text": "28 min",
    "distance_km": 15,
    "distance_text": "15 km",
    "traffic_delay": 8,
    "traffic_note": "traffico moderato"
  },

  "news": {
    "success": true,
    "total": 3,
    "articles": [
      {
        "title": "Nuovo impianto eolico in Sardegna: 50MW di potenza pulita",
        "description": "Il progetto prevede l'installazione di 15 turbine eoliche nella zona di Santadi...",
        "source": "La Nuova Sardegna",
        "url": "https://..."
      },
      {
        "title": "Cagliari Calcio vince 2-1 contro il Cosenza",
        "description": "Doppietta di Lapadula porta i rossoblù alla quinta vittoria consecutiva...",
        "source": "Unione Sarda",
        "url": "https://..."
      }
    ],
    "interests": ["energia", "calcio", "Sardegna"]
  },

  "suggestions": [
    "⏰ Hai 'Riunione Team Energia' tra 150 minuti",
    "📍 Ricorda: l'evento è a Ufficio Assemini",
    "🧥 Fa freschetto - meglio portare una giacca",
    "💡 Hai 2 luci accese in pieno giorno - considera di spegnerle",
    "⚽ Verifica se oggi gioca la tua squadra del cuore"
  ],

  "routine_insights": {
    "peak_hours": [8, 18, 21],
    "most_active_day": "Lunedi",
    "total_interactions_30d": 247,
    "common_actions": ["chat", "device_control", "calendar_check", "web_search"],
    "preferences": [
      {"text": "L'utente si chiama Alessandro", "importance": 10},
      {"text": "Lavora nel settore energia in Sardegna", "importance": 9},
      {"text": "Tifoso del Cagliari Calcio", "importance": 8},
      {"text": "Preferisce risposte concise", "importance": 7}
    ]
  },

  "voice_text": "Buongiorno, Alessandro. Domenica 30 Marzo 2026, ore 07:30. Attualmente 18 gradi, cielo sereno, percepiti 17. Hai 2 eventi in agenda oggi. Il primo è 'Riunione Team Energia' alle 10:00. Tempo di percorrenza stimato: 28 minuti, traffico moderato. In casa hai 2 luci accese. Temperatura interna: 21 gradi. Alcuni suggerimenti: Hai 'Riunione Team Energia' tra 150 minuti. Ricorda: l'evento è a Ufficio Assemini. Fa freschetto - meglio portare una giaccia. Nelle notizie: Nuovo impianto eolico in Sardegna: 50MW di potenza pulita. Buona giornata!"
}
```

---

## Versione Vocale (Text)

```
Buongiorno, Alessandro.

Domenica 30 Marzo 2026, ore 07:30.

Attualmente 18 gradi, cielo sereno, percepiti 17.

Hai 2 eventi in agenda oggi. Il primo è 'Riunione Team Energia' alle 10:00.

Tempo di percorrenza stimato: 28 minuti, traffico moderato.

In casa hai 2 luci accese. Temperatura interna: 21 gradi.

Alcuni suggerimenti: Hai 'Riunione Team Energia' tra 150 minuti. Ricorda: l'evento è a Ufficio Assemini. Fa freschetto - meglio portare una giaccia. Hai 2 luci accese in pieno giorno - considera di spegnerle.

Nelle notizie: Nuovo impianto eolico in Sardegna: 50MW di potenza pulita.

Buona giornata!
```

**Durata lettura:** ~45 secondi
**Stile:** Conciso, naturale, informativo (stile Jarvis)

---

## Endpoint TTS (Audio)

### 2. POST /dashboard/{user_id}/briefing/tts

**Request:**
```bash
POST http://localhost:8000/dashboard/alessandro/briefing/tts?time=morning
```

**Response:**
- **Content-Type:** `audio/wav`
- **Filename:** `briefing_alessandro_morning.wav`
- **Duration:** ~45 secondi
- **Voice:** Paola (Piper TTS, italiano)

**Test con curl:**
```bash
curl -X POST "http://localhost:8000/dashboard/alessandro/briefing/tts?time=morning" \
  --output briefing.wav && aplay briefing.wav
```

---

## Endpoint Context (Raw Data)

### 3. GET /dashboard/{user_id}/context

**Request:**
```bash
GET http://localhost:8000/dashboard/alessandro/context?location=Cagliari
```

**Response JSON (dati grezzi):**

```json
{
  "timestamp": "2026-03-30T07:30:00.123456",
  "user_id": "alessandro",
  "location": "Cagliari",

  "calendar": {
    "success": true,
    "events": [...],
    "total_events": 2,
    "summary": "2 eventi oggi"
  },

  "weather": {
    "success": true,
    "location": "Cagliari",
    "temperature": 18,
    "feels_like": 17,
    "description": "cielo sereno",
    "humidity": 65,
    "wind_speed": 12,
    "icon": "01d"
  },

  "home": {
    "success": true,
    "total_devices": 8,
    "lights_on": 2,
    "lights_off": 4,
    "temperature": 21.5,
    "energy_consumption": 245.3,
    "devices": [...],
    "summary": "2 luci accese, temperatura 21.5°C, consumo 245W"
  },

  "routine": {
    "peak_hours": [8, 18, 21],
    "most_active_day": "Lunedi",
    "total_interactions_30d": 247,
    "common_actions": ["chat", "device_control", "calendar_check", "web_search"],
    "preferences": [...]
  },

  "news": {
    "success": true,
    "total": 3,
    "articles": [...],
    "interests": ["energia", "calcio", "Sardegna"]
  }
}
```

---

## Use Cases

### 1. Morning Routine Automation

**Scenario:** Utente si sveglia, attiva routine mattutina tramite automazione (Google Home, Alexa, automazione custom)

```python
# Pseudo-codice automazione
def morning_routine(user_id):
    # 1. Genera briefing
    briefing = requests.get(f"http://jarvis:8000/dashboard/{user_id}/briefing?time=morning")

    # 2. Ottieni audio TTS
    audio = requests.post(f"http://jarvis:8000/dashboard/{user_id}/briefing/tts?time=morning")

    # 3. Riproduci su speaker
    play_audio(audio.content)

    # 4. Accendi luci cucina (se spente)
    if briefing["home"]["lights_on"] < 2:
        requests.post("http://jarvis:8000/chat", json={
            "user_id": user_id,
            "message": "accendi luce cucina"
        })
```

### 2. PWA Dashboard

**Scenario:** Utente apre PWA su smartphone, visualizza dashboard interattivo

```javascript
// Frontend React/Vue/Vanilla JS
async function loadDashboard(userId) {
    const context = await fetch(`/dashboard/${userId}/context`);
    const data = await context.json();

    // Render dashboard UI
    displayWeather(data.weather);
    displayCalendar(data.calendar);
    displayHomeStatus(data.home);
    displayNews(data.news);

    // Voice briefing button
    document.getElementById('play-briefing').onclick = async () => {
        const audio = await fetch(`/dashboard/${userId}/briefing/tts?time=morning`);
        const blob = await audio.blob();
        const audioUrl = URL.createObjectURL(blob);
        new Audio(audioUrl).play();
    };
}
```

### 3. Telegram Bot Integration

**Scenario:** Comando `/briefing` su Telegram bot

```python
# telegram_bot.py
@bot.message_handler(commands=['briefing'])
def send_briefing(message):
    user_id = str(message.from_user.id)

    # Ottieni briefing
    response = requests.get(
        f"http://orchestrator:8000/dashboard/{user_id}/briefing",
        params={"time": "morning"}
    )

    briefing = response.json()

    # Invia testo
    bot.send_message(message.chat.id, briefing["voice_text"])

    # Opzionale: invia anche audio
    audio = requests.post(
        f"http://orchestrator:8000/dashboard/{user_id}/briefing/tts"
    )
    bot.send_voice(message.chat.id, audio.content)
```

---

## Plugin Functions (callable dal LLM)

Il sistema espone anche funzioni individuali chiamabili dal LLM:

```json
{
  "functions": [
    {
      "name": "context_dashboard_get_daily_context",
      "description": "Recupera tutti i dati contestuali giornalieri",
      "parameters": {
        "user_id": "string (required)",
        "location": "string (optional, default: Cagliari)"
      }
    },
    {
      "name": "context_dashboard_generate_morning_briefing",
      "description": "Genera briefing completo mattutino personalizzato",
      "parameters": {
        "user_id": "string (required)",
        "location": "string (optional)",
        "work_location": "string (optional)"
      }
    },
    {
      "name": "context_dashboard_calculate_commute_time",
      "description": "Calcola tempo di percorrenza con traffico",
      "parameters": {
        "location_from": "string (required)",
        "location_to": "string (required)"
      }
    },
    {
      "name": "context_dashboard_get_personalized_news",
      "description": "Recupera notizie personalizzate basate su interessi",
      "parameters": {
        "user_id": "string (required)",
        "max_results": "integer (optional, default: 5)"
      }
    },
    {
      "name": "context_dashboard_analyze_routine_patterns",
      "description": "Analizza pattern comportamentali e routine",
      "parameters": {
        "user_id": "string (required)"
      }
    },
    {
      "name": "context_dashboard_suggest_daily_optimizations",
      "description": "Genera suggerimenti proattivi per la giornata",
      "parameters": {
        "user_id": "string (required)",
        "location": "string (optional)"
      }
    }
  ]
}
```

**Esempio conversazione con LLM:**

```
User: "Dammi il briefing mattutino"

LLM: {"function": "context_dashboard_generate_morning_briefing", "parameters": {"user_id": "alessandro"}}

System: [Executes function, returns briefing data]

LLM: "Buongiorno Alessandro! Oggi hai 2 eventi in calendario. Il primo è 'Riunione Team Energia' alle 10:00 ad Assemini. Il meteo prevede 18 gradi con cielo sereno. In casa hai 2 luci accese e la temperatura è di 21 gradi. Tempo di percorrenza stimato verso Assemini: 28 minuti con traffico moderato. Nelle notizie: nuovo impianto eolico da 50MW in Sardegna. Vuoi che ti dia altri dettagli?"
```

---

## Performance & Caching

Il sistema implementa un layer di cache intelligente:

- **Meteo:** Cache 1 ora (evita chiamate API ripetute)
- **Notizie:** Cache 30 minuti
- **Traffico:** Cache 15 minuti
- **Routine:** Cache 24 ore

**Vantaggi:**
- Riduce latenza (da ~3s a <500ms per briefing successivi)
- Risparmia chiamate API (limite free tier)
- Fallback automatico se API non disponibile

---

## Configurazione Minima (senza API esterne)

Il sistema funziona anche SENZA configurare le API esterne:

**.env minimo:**
```bash
TELEGRAM_BOT_TOKEN=...
GOOGLE_API_KEY=...
# Tutto il resto opzionale!
```

**Comportamento con API mancanti:**
- **Meteo:** Ritorna dati mock (20°C, "dati non disponibili")
- **Notizie:** Array vuoto
- **Traffico:** Stima statica basata su ora del giorno
- **Calendario:** "Nessun evento" (se non configurato)
- **Smart Home:** "Nessun dispositivo" (se Tuya non attivo)

**Briefing esempio senza API:**
```
Buongiorno, Alessandro.

Domenica 30 Marzo 2026, ore 07:30.

Dati meteo non disponibili (configura OPENWEATHER_API_KEY).

Nessun impegno in calendario oggi.

Nessun dispositivo smart home configurato.

Buona giornata!
```

---

## Testing

```bash
# Test context endpoint
curl http://localhost:8000/dashboard/test_user/context

# Test briefing JSON
curl http://localhost:8000/dashboard/test_user/briefing?time=morning

# Test briefing audio
curl -X POST http://localhost:8000/dashboard/test_user/briefing/tts?time=morning --output briefing.wav

# Test singole funzioni via chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user","message":"dammi il briefing mattutino"}'
```

---

## Next Steps / Future Improvements

**Già implementato:**
- ✅ Morning briefing completo
- ✅ Integrazione calendario
- ✅ Meteo con fallback
- ✅ Smart home status
- ✅ Routine analysis
- ✅ Notizie personalizzate
- ✅ Calcolo traffico (statico + API opzionale)
- ✅ Suggerimenti proattivi
- ✅ Cache layer
- ✅ TTS audio output

**TODO (future):**
- 📝 Evening briefing (recap giornata)
- 📝 Weekend briefing (suggerimenti svago)
- 📝 Integrazione fitness tracker (Strava, Garmin)
- 📝 Integrazione email (riassunto inbox)
- 📝 Integrazione finanza (crypto prices, stock alerts)
- 📝 Multi-language support
- 📝 Voice shortcuts ("Hey Jarvis, briefing")
