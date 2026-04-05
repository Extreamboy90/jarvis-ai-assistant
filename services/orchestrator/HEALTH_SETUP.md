# Neuralink Health Plugin - Quick Setup Guide

Setup rapido in 5 minuti per iniziare a usare il plugin health.

## Prerequisites

- Docker e docker-compose in esecuzione
- PostgreSQL container attivo
- Orchestrator service running

## Step 1: Database Migration (OBBLIGATORIO)

```bash
# Accedi al container PostgreSQL
docker exec -it jarvis-postgres psql -U jarvis -d jarvis

# Esegui migration (crea tabelle health)
\i /app/db/health_migration.sql

# Verifica tabelle create
\dt health*

# Dovresti vedere:
#  health_data
#  health_goals
#  workouts
#  nutrition_log
#  health_anomalies

# Esci
\q
```

## Step 2: Restart Orchestrator

```bash
docker-compose restart orchestrator

# Verifica che il plugin sia caricato
docker-compose logs orchestrator | grep "Plugin loaded: health"
# Output atteso: "✅ Plugin loaded: health"
```

## Step 3: Test di Base (senza Google Fit)

```bash
# Test 1: Import dati mock
curl -X POST "http://localhost:8000/health/test_user/import" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "source": "generic",
    "file_content": "date,metric_type,value\n2026-03-30,steps,8523\n2026-03-30,calories,2100\n2026-03-30,sleep,7.5\n2026-03-30,heart_rate,68"
  }'

# Test 2: Verifica dati importati
curl "http://localhost:8000/health/test_user/activity?date=2026-03-30"

# Test 3: Imposta obiettivi
curl -X POST "http://localhost:8000/health/test_user/goals" \
  -H "Content-Type: application/json" \
  -d '{"steps": 10000, "sleep": 8}'

# Test 4: Wellness report
curl "http://localhost:8000/health/test_user/wellness-report?period=today"
```

Se tutti i test rispondono con `"success": true`, il setup è completo!

## Step 4 (Opzionale): Google Fit OAuth

Solo se vuoi sincronizzazione automatica da Google Fit.

### 4.1 Crea Progetto Google Cloud

1. Vai su https://console.cloud.google.com
2. Crea progetto "Jarvis Health"
3. Abilita Google Fitness API
4. Crea credenziali OAuth 2.0 (Desktop app)
5. Scarica JSON come `google_fit_credentials.json`

### 4.2 Installa Credenziali

```bash
# Copia nel container
docker cp google_fit_credentials.json jarvis-orchestrator:/app/

# O aggiungi a docker-compose.yml:
# volumes:
#   - ./google_fit_credentials.json:/app/google_fit_credentials.json
```

### 4.3 Prima Autenticazione

```bash
# Questo aprirà browser per OAuth
curl -X POST "http://localhost:8000/health/YOUR_USER_ID/sync?source=google_fit&days=7"

# Segui il flusso OAuth nel browser
# Il token verrà salvato nel database

# Le sincronizzazioni successive NON richiedono browser
curl -X POST "http://localhost:8000/health/YOUR_USER_ID/sync?source=google_fit&days=7"
```

## Quick Test Script

Salva come `test_health.sh`:

```bash
#!/bin/bash

USER="test_user"
BASE_URL="http://localhost:8000"

echo "=== Testing Health Plugin ==="

echo -e "\n1. Importing mock data..."
curl -s -X POST "$BASE_URL/health/$USER/import" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER'",
    "source": "generic",
    "file_content": "date,metric_type,value\n2026-03-30,steps,8523\n2026-03-30,calories,2100\n2026-03-30,sleep,7.5\n2026-03-30,heart_rate,68\n2026-03-29,steps,10234\n2026-03-29,sleep,8.2"
  }' | jq .

echo -e "\n2. Setting goals..."
curl -s -X POST "$BASE_URL/health/$USER/goals" \
  -H "Content-Type: application/json" \
  -d '{"steps": 10000, "sleep": 8, "workouts_per_week": 3}' | jq .

echo -e "\n3. Getting activity summary..."
curl -s "$BASE_URL/health/$USER/activity?date=2026-03-30" | jq .

echo -e "\n4. Sleep analysis..."
curl -s "$BASE_URL/health/$USER/sleep?days=2" | jq .

echo -e "\n5. Workout suggestion..."
curl -s "$BASE_URL/health/$USER/workout-suggestion" | jq .

echo -e "\n6. Detect anomalies..."
curl -s "$BASE_URL/health/$USER/anomalies" | jq .

echo -e "\n=== Tests Complete ==="
```

Esegui:
```bash
chmod +x test_health.sh
./test_health.sh
```

## Quick Test via Chat

Puoi anche testare tramite conversazione con Jarvis:

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Come ho dormito nelle ultime 2 notti?",
    "user_id": "test_user"
  }' | jq -r '.response'
```

Altri esempi:
- "Suggeriscimi un allenamento per oggi"
- "Quanti passi ho fatto oggi?"
- "Traccia questo pasto: pasta al pomodoro 150g"
- "Dammi un report della mia salute questa settimana"

## Troubleshooting

### Errore: "Table health_data does not exist"

```bash
# Ri-esegui migration
docker exec -it jarvis-postgres psql -U jarvis -d jarvis -f /app/db/health_migration.sql
```

### Errore: "Plugin health not loaded"

```bash
# Verifica che health.py esista
docker exec jarvis-orchestrator ls -la /app/plugins/health.py

# Restart orchestrator
docker-compose restart orchestrator

# Check logs
docker-compose logs orchestrator | grep health
```

### Errore: "Failed to generate embedding"

```bash
# Installa modello Ollama per embeddings
docker exec ollama ollama pull all-minilm
```

### Performance lente su analisi AI

Questo è normale - l'analisi AI con LLM può richiedere 5-30 secondi.
Usa il modello fast per analisi veloci:

```python
# Nel plugin health.py, modifica:
use_smart=False  # Invece di use_smart=True
```

## Next Steps

1. Leggi documentazione completa: `HEALTH_PLUGIN.md`
2. Guarda esempi avanzati: `health_test_data.json`
3. Configura Google Fit per sync automatica (opzionale)
4. Integra con Telegram bot per notifiche
5. Crea routine automatiche (es: sync mattutina)

## Comandi Utili

```bash
# Check health endpoint
curl http://localhost:8000/health

# List all plugin functions
curl http://localhost:8000/functions | jq '.functions[] | select(.name | startswith("health_"))'

# Get user goals
curl "http://localhost:8000/health/USER_ID/goals"

# Delete all health data (GDPR)
curl -X DELETE "http://localhost:8000/health/USER_ID/data?confirm=true"
```

## Support

Per problemi o domande, controlla:
- `HEALTH_PLUGIN.md` - Documentazione completa
- `health_test_data.json` - Esempi di test
- Logs: `docker-compose logs orchestrator | grep -i health`
