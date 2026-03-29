# Configurazione Google Gemini API

## Perché Gemini?

Gemini 1.5 Flash offre:
- ✅ **Velocità**: 1-2 secondi vs 15-30 secondi di Ollama (15-30x più veloce!)
- ✅ **Gratuito**: Piano gratuito generoso (15 req/min, 1500 req/day)
- ✅ **Function Calling**: Supporto nativo eccellente
- ✅ **Italiano**: Ottimo supporto multilingua
- ✅ **Affidabile**: API ufficiale Google stabile

## Come Ottenere l'API Key

1. Vai su https://ai.google.dev/
2. Clicca "Get API Key" in alto a destra
3. Accedi con il tuo account Google
4. Crea un nuovo progetto (o usa uno esistente)
5. Clicca "Create API Key"
6. Copia la chiave API generata

## Configurazione

1. Apri il file `.env` nella root del progetto:
   ```bash
   nano /home/extreamboy/ai-assistant/.env
   ```

2. Sostituisci `your_api_key_here` con la tua API key:
   ```bash
   GOOGLE_API_KEY=AIzaSy...your_actual_key_here
   ```

3. Salva il file (Ctrl+O, Ctrl+X)

## Avvio con Gemini

```bash
cd /home/extreamboy/ai-assistant

# Rebuild orchestrator con nuove dipendenze
docker compose build --no-cache orchestrator

# Avvia/riavvia i servizi
docker compose up -d orchestrator

# Verifica che Gemini sia attivo
docker compose logs orchestrator | grep -i gemini
# Dovresti vedere: "🚀 Using Google Gemini API for LLM (fast & reliable)"
```

## Test

```bash
# Test semplice
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"ciao","user_id":"test"}'

# Test con function calling
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"che ore sono?","user_id":"test"}'

# Test ricerca web
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"cerca le ultime notizie sulla tecnologia","user_id":"test"}'
```

## Disabilitare Gemini (tornare a Ollama)

Se vuoi tornare a usare Ollama locale:

```bash
# Modifica docker-compose.yml
# Cambia: - USE_GEMINI=true
# In:     - USE_GEMINI=false

docker compose up -d orchestrator
```

## Monitoraggio Uso API

- Dashboard Google AI Studio: https://aistudio.google.com/app/apikey
- Visualizza quote e utilizzo
- Piano gratuito: 15 req/min, 1500 req/day
- Se superi i limiti, otterrai errore 429 (troppi request)

## Prezzi (se superi il piano gratuito)

- **Gemini 1.5 Flash**: $0.075 per 1M token input, $0.30 per 1M output
- **Gemini 1.5 Pro**: $1.25 per 1M token input, $5.00 per 1M output

Con uso normale di Jarvis, il piano gratuito è più che sufficiente!

## Troubleshooting

### "No GOOGLE_API_KEY found"
- Verifica che l'API key sia nel file `.env`
- Riavvia i container: `docker compose up -d orchestrator`

### "Gemini API error: 403"
- API key non valida o scaduta
- Verifica su https://ai.google.dev/

### "Gemini API error: 429"
- Superato il rate limit (15 req/min)
- Aspetta 1 minuto o passa a piano a pagamento

### Sistema usa ancora Ollama
- Verifica logs: `docker compose logs orchestrator | grep "Using"`
- Controlla che `USE_GEMINI=true` in docker-compose.yml
- Verifica che la API key sia configurata correttamente

## Performance Attese

| Operazione | Ollama qwen2.5:7b | Gemini 1.5 Flash | Miglioramento |
|------------|-------------------|------------------|---------------|
| Chat semplice | 15-20s | 1-2s | **10x più veloce** |
| Function calling | 25-35s | 2-3s | **12x più veloce** |
| Con ricerca web | 40-50s | 3-4s | **15x più veloce** |
