# Neuralink Health Plugin - Documentation

Integrazione completa con fitness tracker e smartwatch per monitoraggio salute, coaching AI, e correlazioni con memoria/comportamento.

## Indice

- [Setup e Configurazione](#setup-e-configurazione)
- [API Endpoints](#api-endpoints)
- [Funzioni Plugin](#funzioni-plugin)
- [Formati File Supportati](#formati-file-supportati)
- [Esempi di Utilizzo](#esempi-di-utilizzo)
- [Google Fit OAuth Setup](#google-fit-oauth-setup)
- [Sicurezza e Privacy](#sicurezza-e-privacy)

---

## Setup e Configurazione

### 1. Eseguire la Migration del Database

```bash
# Accedi al container PostgreSQL
docker exec -it jarvis-postgres psql -U jarvis -d jarvis

# Esegui la migration
\i /docker-entrypoint-initdb.d/health_migration.sql

# Verifica che le tabelle siano create
\dt
```

### 2. Configurare Google Fit (opzionale)

Vedi sezione [Google Fit OAuth Setup](#google-fit-oauth-setup)

### 3. Riavviare l'Orchestrator

```bash
docker-compose up -d --build orchestrator
```

### 4. Verificare che il Plugin sia Caricato

```bash
curl http://localhost:8000/health
# Dovrebbe rispondere con: {"status": "healthy", "plugins": [..., "health", ...]}
```

---

## API Endpoints

### POST /health/{user_id}/sync

Sincronizza dati da Google Fit.

**Query Parameters:**
- `source`: `google_fit` (default) o `file`
- `days`: Numero di giorni da sincronizzare (default: 7)

**Esempio:**
```bash
curl -X POST "http://localhost:8000/health/user123/sync?source=google_fit&days=7"
```

**Response:**
```json
{
  "success": true,
  "message": "Sincronizzati 142 dati da Google Fit (ultimi 7 giorni)",
  "data_points": 142,
  "source": "google_fit"
}
```

---

### POST /health/{user_id}/import

Importa dati da file CSV/JSON.

**Body:**
```json
{
  "user_id": "user123",
  "source": "fitbit",
  "file_content": "Date,Steps,Calories Burned\n2026-03-30,8523,2100\n..."
}
```

**Fonti supportate:**
- `fitbit` - Export CSV da Fitbit
- `apple_health` - Export JSON da Apple Health
- `garmin` - Export CSV da Garmin Connect
- `generic` - CSV generico (date, metric_type, value)

**Esempio:**
```bash
curl -X POST "http://localhost:8000/health/user123/import" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "source": "fitbit",
    "file_content": "Date,Steps,Calories Burned\n2026-03-30,8523,2100\n2026-03-29,10234,2300"
  }'
```

**Response:**
```json
{
  "success": true,
  "source": "fitbit",
  "data_points_imported": 4,
  "message": "Successfully imported 4 data points from fitbit"
}
```

---

### GET /health/{user_id}/summary

Riepilogo salute per periodo.

**Query Parameters:**
- `period`: `today`, `week`, `month` (default: `today`)

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/summary?period=week"
```

**Response:**
```json
{
  "success": true,
  "period": "week",
  "days": 7,
  "generated_at": "2026-03-30T10:30:00",
  "metrics": {
    "sleep": {
      "average_hours": 7.2,
      "quality_score": "buona"
    },
    "activity": {
      "steps": 8234,
      "calories": 2100
    },
    "heart_rate": {
      "average_bpm": 68,
      "resting_bpm": 62
    }
  },
  "goals_progress": [
    {
      "goal_type": "steps",
      "progress_pct": 82,
      "current_value": 8200,
      "target_value": 10000
    }
  ],
  "ai_summary": "La tua settimana è stata buona! Sonno nella norma (7.2h/notte), attività fisica discreta ma sotto l'obiettivo di 10k passi. Consiglio: prova a fare una passeggiata extra di 15 minuti al giorno.",
  "overall_score": 78
}
```

---

### GET /health/{user_id}/sleep

Analisi qualità sonno con insights AI.

**Query Parameters:**
- `days`: Giorni da analizzare (default: 7)

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/sleep?days=7"
```

**Response:**
```json
{
  "success": true,
  "period_days": 7,
  "nights_tracked": 7,
  "average_hours": 7.2,
  "min_hours": 6.1,
  "max_hours": 8.5,
  "quality_score": "buona",
  "ai_analysis": "Il tuo sonno è nella norma (7-9h). Pattern regolare con lieve deficit venerdì (6.1h). Suggerimenti: mantieni orari costanti, evita caffeina dopo le 16, spegni schermi 30 min prima di dormire.",
  "raw_data": [
    {"timestamp": "2026-03-30T00:00:00", "value": 7.5},
    {"timestamp": "2026-03-29T00:00:00", "value": 6.9}
  ]
}
```

---

### GET /health/{user_id}/activity

Riepilogo attività giornaliera.

**Query Parameters:**
- `date`: Data in formato YYYY-MM-DD (default: oggi)

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/activity?date=2026-03-30"
```

**Response:**
```json
{
  "success": true,
  "date": "2026-03-30",
  "steps": 8234,
  "calories": 2100,
  "workouts": [
    {
      "type": "running",
      "duration_minutes": 30,
      "calories": 350,
      "intensity": "medium"
    }
  ],
  "total_workouts": 1,
  "active": true
}
```

---

### GET /health/{user_id}/heart-rate

Trend battito cardiaco.

**Query Parameters:**
- `days`: Giorni da analizzare (default: 30)

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/heart-rate?days=30"
```

**Response:**
```json
{
  "success": true,
  "period_days": 30,
  "measurements": 450,
  "average_bpm": 68.4,
  "resting_bpm": 62.1,
  "min_bpm": 48.0,
  "max_bpm": 165.0,
  "trend": "normale",
  "recent_readings": [
    {"time": "2026-03-30T09:15:00", "bpm": 72},
    {"time": "2026-03-30T08:45:00", "bpm": 65}
  ]
}
```

---

### GET /health/{user_id}/goals

Recupera obiettivi salute con progressi.

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/goals"
```

**Response:**
```json
{
  "success": true,
  "user_id": "user123",
  "goals": [
    {
      "goal_type": "steps",
      "target_value": 10000,
      "current_value": 8200,
      "progress_pct": 82,
      "deadline": null
    },
    {
      "goal_type": "sleep",
      "target_value": 8.0,
      "current_value": 7.2,
      "progress_pct": 90,
      "deadline": null
    }
  ]
}
```

---

### POST /health/{user_id}/goals

Imposta o aggiorna obiettivi.

**Body:**
```json
{
  "steps": 10000,
  "sleep": 8,
  "workouts_per_week": 3,
  "weight": 75.0
}
```

**Esempio:**
```bash
curl -X POST "http://localhost:8000/health/user123/goals" \
  -H "Content-Type: application/json" \
  -d '{"steps": 10000, "sleep": 8, "workouts_per_week": 3}'
```

**Response:**
```json
{
  "success": true,
  "message": "Obiettivi impostati: steps, sleep, workouts_per_week",
  "goals": {
    "steps": 10000,
    "sleep": 8,
    "workouts_per_week": 3
  }
}
```

---

### GET /health/{user_id}/wellness-report

Report benessere completo con AI.

**Query Parameters:**
- `period`: `today`, `week`, `month` (default: `week`)

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/wellness-report?period=week"
```

**Response:**
```json
{
  "success": true,
  "period": "week",
  "days": 7,
  "generated_at": "2026-03-30T10:30:00",
  "metrics": { ... },
  "goals_progress": [ ... ],
  "ai_summary": "**Settimana Positiva!** 🌟\n\nPunti di forza:\n- Sonno regolare (7.2h media)\n- Allenamenti costanti (4/7 giorni)\n\nAree da migliorare:\n- Passi sotto obiettivo (-18%)\n- Idratazione insufficiente\n\nRaccomandazioni:\n1. Aggiungi 2000 passi/giorno (20 min camminata)\n2. Bevi 2L acqua al giorno\n3. Mantieni la routine sonno\n\nMotivazione: Sei sulla strada giusta! Piccoli aggiustamenti porteranno grandi risultati.",
  "overall_score": 78
}
```

---

### POST /health/{user_id}/nutrition

Traccia pasto con stima AI.

**Query Parameters:**
- `meal_description`: Descrizione del pasto

**Esempio:**
```bash
curl -X POST "http://localhost:8000/health/user123/nutrition?meal_description=pasta+al+pomodoro+150g+petto+di+pollo+100g+insalata"
```

**Response:**
```json
{
  "success": true,
  "meal": "pasta al pomodoro 150g, petto di pollo 100g, insalata",
  "calories": 520,
  "protein_g": 35,
  "carbs_g": 65,
  "fat_g": 8,
  "meal_type": "pranzo",
  "healthiness_score": 8,
  "notes": "Pasto bilanciato con buon apporto proteico. Carboidrati nella norma. Basso contenuto di grassi. Ottimo!",
  "disclaimer": "Stima approssimativa. Non sostituisce consulenza nutrizionale professionale."
}
```

---

### GET /health/{user_id}/workout-suggestion

Suggerimento allenamento personalizzato.

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/workout-suggestion"
```

**Response:**
```json
{
  "success": true,
  "current_state": {
    "steps_today": 3200,
    "workouts_today": 0,
    "sleep_quality": "buona"
  },
  "suggestion": "**Allenamento Consigliato: Corsa Leggera**\n\nDurata: 30 minuti\nIntensità: Media-Bassa\n\nProgramma:\n- 5 min riscaldamento (camminata veloce)\n- 20 min corsa leggera (conversazione possibile)\n- 5 min defaticamento (camminata lenta)\n\nMotivazione: Hai dormito bene e non hai ancora fatto allenamenti oggi. Perfetto momento per una corsa leggera che ti darà energia senza affaticarti troppo. Obiettivo: completare i 10k passi giornalieri!\n\nAvvertenza: Se ti senti stanco o hai dolori, riduci intensità o sostituisci con camminata veloce.",
  "goals": [
    {"goal_type": "steps", "target_value": 10000}
  ]
}
```

---

### GET /health/{user_id}/anomalies

Rileva anomalie nei dati salute.

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/anomalies"
```

**Response (con anomalie):**
```json
{
  "success": true,
  "anomalies_detected": true,
  "count": 2,
  "anomalies": [
    {
      "type": "sleep_deficit",
      "severity": "high",
      "message": "Sonno insufficiente: media 5.8h/notte (raccomandato: 7-9h)",
      "recommendation": "Prioritizza il sonno. Vai a letto prima e mantieni orari regolari."
    },
    {
      "type": "low_activity",
      "severity": "medium",
      "message": "Attività fisica molto bassa oggi: 1234 passi",
      "recommendation": "Prova a fare una passeggiata di 15-20 minuti."
    }
  ],
  "disclaimer": "Queste sono solo osservazioni automatiche. Consulta un medico per valutazioni mediche."
}
```

**Response (nessuna anomalia):**
```json
{
  "success": true,
  "anomalies_detected": false,
  "message": "Nessuna anomalia rilevata. I tuoi dati di salute sembrano nella norma!"
}
```

---

### GET /health/{user_id}/correlations

Correla salute con memoria/stati emotivi.

**Query Parameters:**
- `metric`: Metrica da correlare (`sleep`, `heart_rate`, `activity`, `all`)
- `days`: Giorni da analizzare (default: 14)

**Esempio:**
```bash
curl "http://localhost:8000/health/user123/correlations?metric=all&days=14"
```

**Response:**
```json
{
  "success": true,
  "period_days": 14,
  "health_metrics_analyzed": ["sleep", "heart_rate", "activity"],
  "memories_count": 23,
  "correlation_analysis": "**Correlazioni Interessanti Trovate:**\n\n1. **Sonno e Stress Lavorativo**\n   - Nelle giornate con deadline o riunioni importanti (memorie: 'presentazione cliente', 'scadenza progetto'), il sonno è ridotto del 15% (media 6.2h vs 7.3h normale)\n   - Suggerimento: Pianifica meglio le giornate intense, prevedi buffer time\n\n2. **Attività Fisica e Umore**\n   - Giorni con allenamento mattutino correlano con memorie positive ('giornata produttiva', 'buon umore')\n   - L'attività fisica sembra migliorare lo stato emotivo del 40%\n\n3. **Battito Cardiaco a Riposo**\n   - Elevato nei periodi di 'ansia per esame' (memoria) e 'preoccupazione lavoro'\n   - Normalizzato dopo 'weekend rilassante' e 'vacanza'\n\n**Raccomandazioni:**\n- Aumenta attività fisica nei periodi stressanti\n- Pratica tecniche rilassamento prima di eventi importanti\n- Monitora pattern sonno quando hai deadline",
  "sample_health_data": { ... },
  "sample_memories": [ ... ]
}
```

---

### DELETE /health/{user_id}/disconnect

Disconnetti account salute.

**Query Parameters:**
- `source`: Fonte da disconnettere (`google_fit`, etc.)

**Esempio:**
```bash
curl -X DELETE "http://localhost:8000/health/user123/disconnect?source=google_fit"
```

**Response:**
```json
{
  "success": true,
  "message": "google_fit account disconnected successfully",
  "note": "Health data has been preserved. Use DELETE /health/{user_id}/data to remove all data."
}
```

---

### DELETE /health/{user_id}/data

Elimina TUTTI i dati salute (GDPR).

**Query Parameters:**
- `confirm`: DEVE essere `true` per procedere

**Esempio:**
```bash
curl -X DELETE "http://localhost:8000/health/user123/data?confirm=true"
```

**Response:**
```json
{
  "success": true,
  "message": "All health data and connections deleted permanently"
}
```

---

## Funzioni Plugin

Il plugin health espone le seguenti funzioni al LLM:

### health_sync_health_data
Sincronizza dati da Google Fit

### health_get_sleep_analysis
Analisi qualità sonno con AI

### health_get_activity_summary
Riepilogo attività giornaliera

### health_get_heart_rate_trends
Trend battito cardiaco

### health_suggest_workout
Suggerimento allenamento personalizzato

### health_track_nutrition
Traccia pasto con stima AI

### health_set_health_goals
Imposta obiettivi salute

### health_generate_wellness_report
Report benessere completo

### health_detect_anomalies
Rileva anomalie

### health_correlate_with_memory
Correla salute con memoria

---

## Formati File Supportati

### Fitbit CSV

```csv
Date,Steps,Calories Burned,Minutes Asleep
2026-03-30,8523,2100,420
2026-03-29,10234,2300,456
2026-03-28,7891,1980,402
```

### Apple Health JSON

```json
{
  "records": [
    {
      "type": "HKQuantityTypeIdentifierStepCount",
      "startDate": "2026-03-30T00:00:00Z",
      "value": 8523,
      "unit": "count"
    },
    {
      "type": "HKCategoryTypeIdentifierSleepAnalysis",
      "startDate": "2026-03-29T23:00:00Z",
      "endDate": "2026-03-30T07:00:00Z",
      "value": 8
    }
  ]
}
```

### Garmin CSV

```csv
Date,Steps,Calories,Sleep Time
2026-03-30,8523,2100,7:45
2026-03-29,10234,2300,8:12
```

### Generic CSV

```csv
date,metric_type,value
2026-03-30,steps,8523
2026-03-30,calories,2100
2026-03-30,sleep,7.5
2026-03-30,heart_rate,68
```

---

## Esempi di Utilizzo

### Scenario 1: Sincronizzazione Automatica Google Fit

```bash
# Prima sincronizzazione (richiede OAuth browser)
curl -X POST "http://localhost:8000/health/user123/sync?source=google_fit&days=30"

# Le sincronizzazioni successive usano il token salvato
curl -X POST "http://localhost:8000/health/user123/sync?source=google_fit&days=7"
```

### Scenario 2: Import Manuale da Fitbit

```bash
# Esporta dati da Fitbit web (https://www.fitbit.com/settings/data/export)
# Carica il file CSV

curl -X POST "http://localhost:8000/health/user123/import" \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{
  "user_id": "user123",
  "source": "fitbit",
  "file_content": "Date,Steps,Calories Burned,Minutes Asleep\n2026-03-30,8523,2100,420\n2026-03-29,10234,2300,456"
}
EOF
```

### Scenario 3: Workflow Mattutino Completo

```bash
#!/bin/bash
USER_ID="user123"

# 1. Sincronizza dati overnight
curl -X POST "http://localhost:8000/health/$USER_ID/sync?days=1"

# 2. Analisi sonno
curl "http://localhost:8000/health/$USER_ID/sleep?days=1"

# 3. Rileva anomalie
curl "http://localhost:8000/health/$USER_ID/anomalies"

# 4. Suggerimento allenamento
curl "http://localhost:8000/health/$USER_ID/workout-suggestion"

# 5. Report settimanale (lunedì)
if [ $(date +%u) -eq 1 ]; then
  curl "http://localhost:8000/health/$USER_ID/wellness-report?period=week"
fi
```

### Scenario 4: Tracciamento Pasti Giornalieri

```bash
# Colazione
curl -X POST "http://localhost:8000/health/user123/nutrition?meal_description=caffe+latte+fette+biscottate+marmellata"

# Pranzo
curl -X POST "http://localhost:8000/health/user123/nutrition?meal_description=insalata+di+riso+con+tonno+e+verdure"

# Cena
curl -X POST "http://localhost:8000/health/user123/nutrition?meal_description=petto+pollo+grigliato+150g+patate+al+forno+broccoli"
```

### Scenario 5: Conversazione con LLM (via Chat)

```bash
# L'utente può interagire naturalmente con Jarvis
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Come ho dormito questa settimana?",
    "user_id": "user123"
  }'

# Jarvis chiamerà automaticamente health_get_sleep_analysis e risponderà:
# "Questa settimana hai dormito in media 7.2 ore a notte, con qualità buona.
#  Unica nota: venerdì hai dormito solo 6.1 ore. Ti consiglio di..."

# Altri esempi:
# - "Suggeriscimi un allenamento per oggi"
# - "Traccia questo pasto: pasta carbonara 200g"
# - "Quanti passi ho fatto oggi?"
# - "Ci sono correlazioni tra il mio sonno e lo stress lavorativo?"
```

---

## Google Fit OAuth Setup

### 1. Crea Progetto Google Cloud

1. Vai su https://console.cloud.google.com
2. Crea nuovo progetto: "Jarvis Health"
3. Abilita **Google Fitness API**:
   - API & Services → Library
   - Cerca "Fitness API"
   - Click Enable

### 2. Crea Credenziali OAuth2

1. API & Services → Credentials → Create Credentials → OAuth 2.0 Client ID
2. Tipo applicazione: **Desktop app**
3. Nome: "Jarvis Health Desktop"
4. Scarica JSON

### 3. Configura Schermata Consenso

1. OAuth consent screen → External
2. App name: "Jarvis Health"
3. User support email: tua email
4. Developer contact: tua email
5. Scopes: Aggiungi `.../auth/fitness.activity.read`, `fitness.body.read`, `fitness.heart_rate.read`, `fitness.sleep.read`
6. Test users: aggiungi il tuo account Google

### 4. Installa Credenziali nel Container

```bash
# Copia il file JSON scaricato
cp ~/Downloads/client_secret_*.json google_fit_credentials.json

# Copia nel container
docker cp google_fit_credentials.json jarvis-orchestrator:/app/google_fit_credentials.json

# O monta volume in docker-compose.yml:
# volumes:
#   - ./google_fit_credentials.json:/app/google_fit_credentials.json
```

### 5. Prima Autenticazione

```bash
# Esegui prima sincronizzazione - si aprirà browser per OAuth
curl -X POST "http://localhost:8000/health/user123/sync?source=google_fit&days=7"

# Il token viene salvato nel database (users.metadata.google_fit_token)
# Le chiamate successive non richiedono browser
```

### 6. Verifica Permessi

Nel tuo account Google:
- Vai su https://myaccount.google.com/permissions
- Verifica che "Jarvis Health" abbia accesso a Fitness API
- Puoi revocare da qui in qualsiasi momento

---

## Sicurezza e Privacy

### Principi di Sicurezza

1. **Encryption at Rest**
   - PostgreSQL supporta nativamente encryption at rest
   - Abilita tramite `pgcrypto` extension
   - Dati health mai loggati in chiaro

2. **OAuth2 con PKCE**
   - Token refresh automatico
   - Token stored in database (encrypted JSON)
   - Nessun token in file sistema

3. **GDPR Compliance**
   - Right to be forgotten: `DELETE /health/{user_id}/data?confirm=true`
   - Data retention policy: funzione `cleanup_old_health_data()`
   - Audit trail: tutte le operazioni loggati

4. **No Plain Text Logging**
   - Health values non loggati in chiaro
   - Solo metadata loggati (es: "Imported 10 data points")

### Disclaimer Medico

TUTTI i suggerimenti AI includono il disclaimer:

> "Non sono un medico. Le mie indicazioni sono solo suggerimenti generali di benessere. Se rilevi anomalie preoccupanti, consulta un medico."

Questo appare in:
- Analisi sonno
- Suggerimenti workout
- Tracking nutrizione
- Rilevamento anomalie
- Correlazioni salute-memoria

---

## Troubleshooting

### Errore: "Google Fit credentials file not found"

**Soluzione:**
```bash
docker cp google_fit_credentials.json jarvis-orchestrator:/app/
docker restart jarvis-orchestrator
```

### Errore: "Failed to generate embedding"

**Causa:** Modello Ollama `all-minilm` mancante

**Soluzione:**
```bash
docker exec ollama ollama pull all-minilm
```

### Errore: "Table health_data does not exist"

**Causa:** Migration non eseguita

**Soluzione:**
```bash
docker exec -it jarvis-postgres psql -U jarvis -d jarvis -f /app/db/health_migration.sql
```

### Performance Lente

**Causa:** Troppi dati senza indici

**Soluzione:**
```bash
# Verifica indici
docker exec -it jarvis-postgres psql -U jarvis -d jarvis -c "\\di"

# Re-crea indici se mancanti
docker exec -it jarvis-postgres psql -U jarvis -d jarvis -f /app/db/health_migration.sql
```

---

## Roadmap Future

- [ ] Apple Health direct integration (requires iOS app)
- [ ] Withings API integration
- [ ] Oura Ring API integration
- [ ] Real-time anomaly alerts via Telegram
- [ ] Weekly wellness report email/notification
- [ ] Voice commands integration ("Jarvis, how did I sleep?")
- [ ] Dashboard web UI for health data visualization
- [ ] ML-based predictive wellness scoring
- [ ] Social features (compare with friends - anonymized)
- [ ] Integration with calendar (suggest workouts based on free time)

---

## Credits

Developed for Jarvis AI Assistant by Claude Code.

Health data integrations:
- Google Fit API
- Fitbit, Apple Health, Garmin (file import)

AI analysis powered by:
- Google Gemini API
- Ollama (local fallback)

---

## License

Part of Jarvis AI Assistant project.
