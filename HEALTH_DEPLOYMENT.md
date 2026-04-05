# Health Plugin - Deployment Instructions

Quick deployment checklist per mettere in produzione il plugin health.

## Prerequisites Checklist

- [ ] Docker e docker-compose funzionanti
- [ ] PostgreSQL container attivo
- [ ] Orchestrator service running
- [ ] Ollama con modello `all-minilm` installato

## Deployment Steps

### Step 1: Backup Database (Recommended)

```bash
# Backup database before migration
docker exec jarvis-postgres pg_dump -U jarvis jarvis > backup_$(date +%Y%m%d).sql

# In caso di problemi, restore:
# docker exec -i jarvis-postgres psql -U jarvis -d jarvis < backup_YYYYMMDD.sql
```

### Step 2: Run Database Migration

```bash
# Accedi al database
docker exec -it jarvis-postgres psql -U jarvis -d jarvis

# Esegui migration
\i /app/db/health_migration.sql

# Verifica tabelle create
\dt health*

# Output atteso:
#  public | health_anomalies | table | jarvis
#  public | health_data      | table | jarvis
#  public | health_goals     | table | jarvis
#  public | nutrition_log    | table | jarvis
#  public | workouts         | table | jarvis

# Verifica views
\dv

# Output atteso:
#  public | daily_health_summary   | view | jarvis
#  public | weekly_workout_summary | view | jarvis

# Esci
\q
```

### Step 3: Install Ollama Embedding Model

```bash
# Il plugin health usa all-minilm per embeddings
docker exec ollama ollama pull all-minilm

# Verifica
docker exec ollama ollama list | grep all-minilm
```

### Step 4: Update Docker Compose (if needed)

Se vuoi montare le credenziali Google Fit, aggiungi a `docker-compose.yml`:

```yaml
services:
  orchestrator:
    volumes:
      - ./google_fit_credentials.json:/app/google_fit_credentials.json:ro
```

### Step 5: Rebuild and Restart

```bash
# Rebuild con nuove dipendenze
docker-compose build orchestrator

# Restart
docker-compose up -d orchestrator

# Verifica plugin caricato
docker-compose logs orchestrator | grep "Plugin loaded: health"
# Output atteso: "✅ Plugin loaded: health"
```

### Step 6: Run Tests

```bash
# Test automatico
chmod +x test_health.sh
./test_health.sh

# Se tutti i test passano, il deployment è completo!
```

### Step 7: Configure Google Fit (Optional)

Solo se vuoi sincronizzazione automatica da Google Fit:

1. Vai su https://console.cloud.google.com
2. Crea progetto "Jarvis Health"
3. Abilita Google Fitness API
4. Crea OAuth 2.0 credentials (Desktop app)
5. Scarica `google_fit_credentials.json`
6. Copia nel container:
   ```bash
   docker cp google_fit_credentials.json jarvis-orchestrator:/app/
   ```

7. Prima autenticazione (apre browser):
   ```bash
   curl -X POST "http://localhost:8000/health/YOUR_USER_ID/sync?source=google_fit&days=7"
   ```

## Verification Checklist

Verifica che tutto funzioni:

- [ ] Database migration completata senza errori
- [ ] Plugin health caricato (check logs)
- [ ] Test suite passa tutti i test
- [ ] Endpoint `/health` risponde
- [ ] Import dati funziona
- [ ] Analisi AI funziona (sleep, workout suggestion)
- [ ] Google Fit sync funziona (se configurato)

## Post-Deployment Configuration

### 1. Setup Cron Jobs (Recommended)

Per sincronizzazione automatica:

```bash
# Edita crontab
crontab -e

# Aggiungi:
# Sync Google Fit every hour
0 * * * * /usr/bin/python3 /path/to/health_automation_example.py --user YOUR_USER_ID --action sync_google_fit --days 1 >> /var/log/health_sync.log 2>&1

# Morning routine at 7 AM
0 7 * * * /usr/bin/python3 /path/to/health_automation_example.py --user YOUR_USER_ID --action morning_routine >> /var/log/health_morning.log 2>&1

# Weekly report on Monday at 8 AM
0 8 * * 1 /usr/bin/python3 /path/to/health_automation_example.py --user YOUR_USER_ID --action weekly_report >> /var/log/health_weekly.log 2>&1
```

### 2. Setup Monitoring (Optional)

```bash
# Create log directory
mkdir -p /var/log/jarvis

# Setup logrotate
sudo tee /etc/logrotate.d/jarvis <<EOF
/var/log/jarvis/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF
```

### 3. Configure Alerts (Optional)

Se vuoi notifiche Telegram per anomalie:

```python
# Aggiungi al telegram_bot.py
async def check_health_anomalies():
    """Check health anomalies and notify user"""
    automation = HealthAutomation(user_id=user_id)
    result = automation.detect_anomalies()

    if result.get('anomalies_detected'):
        for anomaly in result.get('anomalies', []):
            severity = anomaly.get('severity')
            if severity in ['high', 'critical']:
                # Send Telegram notification
                await bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ Health Alert: {anomaly.get('message')}"
                )

# Schedule check (esempio: ogni 6 ore)
```

## Rollback Plan

Se qualcosa va storto:

### 1. Rollback Database

```bash
# Restore backup
docker exec -i jarvis-postgres psql -U jarvis -d jarvis < backup_YYYYMMDD.sql

# O solo drop tabelle health
docker exec -it jarvis-postgres psql -U jarvis -d jarvis -c "
DROP TABLE IF EXISTS health_data CASCADE;
DROP TABLE IF EXISTS health_goals CASCADE;
DROP TABLE IF EXISTS workouts CASCADE;
DROP TABLE IF EXISTS nutrition_log CASCADE;
DROP TABLE IF EXISTS health_anomalies CASCADE;
DROP VIEW IF EXISTS daily_health_summary;
DROP VIEW IF EXISTS weekly_workout_summary;
"
```

### 2. Rollback Code

```bash
# Rimuovi plugin dalla lista
# In app.py, rimuovi "health" da PLUGINS_TO_LOAD

# Restart
docker-compose restart orchestrator
```

### 3. Rollback Dependencies

```bash
# Se ci sono conflitti, rimuovi le dipendenze aggiunte da requirements.txt
# e rebuild
docker-compose build orchestrator
docker-compose up -d orchestrator
```

## Performance Tuning

### Database Optimization

```sql
-- Vacuum analyze per ottimizzare indici
VACUUM ANALYZE health_data;
VACUUM ANALYZE health_goals;
VACUUM ANALYZE workouts;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE tablename LIKE 'health%'
ORDER BY idx_scan;
```

### Redis Caching (Future)

Per migliorare performance, aggiungi caching:

```python
# In health.py, aggiungi:
import database

def get_cached_wellness_report(user_id: str, period: str):
    cache_key = f"wellness:{user_id}:{period}"
    cached = database.cache_get(user_id, cache_key)
    if cached:
        return json.loads(cached)

    # Generate report
    report = generate_wellness_report(user_id, period)

    # Cache for 1 hour
    database.cache_set(user_id, cache_key, json.dumps(report), ttl=3600)
    return report
```

## Security Hardening

### 1. Enable PostgreSQL Encryption

```bash
# In postgresql.conf
ssl = on
ssl_cert_file = '/path/to/server.crt'
ssl_key_file = '/path/to/server.key'
```

### 2. Restrict API Access

```python
# In app.py, aggiungi rate limiting
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

@app.get("/health/{user_id}/summary", dependencies=[Depends(RateLimiter(times=10, seconds=60))])
async def get_health_summary(...):
    ...
```

### 3. HTTPS Only

```yaml
# In docker-compose.yml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
```

## Monitoring & Alerts

### Key Metrics to Monitor

1. **API Response Times**
   - `/health/{user_id}/sync` - should be < 5s
   - `/health/{user_id}/sleep` - should be < 10s (includes AI)
   - `/health/{user_id}/activity` - should be < 1s

2. **Database Performance**
   - Query time for health_data selects
   - Index usage statistics
   - Table sizes (should grow predictably)

3. **Google Fit Sync**
   - Success rate (should be >95%)
   - Data points per sync
   - Token refresh failures

4. **AI Analysis**
   - LLM response times
   - Error rates
   - Token usage (if using Gemini)

### Setup Grafana Dashboard (Optional)

```bash
# Example Prometheus metrics
docker run -d \
  --name=prometheus \
  -p 9090:9090 \
  -v ./prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus

# Grafana
docker run -d \
  --name=grafana \
  -p 3000:3000 \
  grafana/grafana
```

## Maintenance

### Weekly

- [ ] Check logs for errors
- [ ] Verify Google Fit sync working
- [ ] Review anomaly detection accuracy
- [ ] Check database size growth

### Monthly

- [ ] Clean old health data (>2 years)
  ```sql
  SELECT cleanup_old_health_data('user_id', 730);
  ```
- [ ] Review and optimize slow queries
- [ ] Update dependencies if needed
- [ ] Backup database

### Quarterly

- [ ] Security audit
- [ ] Performance review
- [ ] User feedback collection
- [ ] Feature requests evaluation

## Support

### Getting Help

1. Check logs:
   ```bash
   docker-compose logs orchestrator | grep -i health
   ```

2. Review documentation:
   - `HEALTH_SETUP.md` - Quick setup
   - `HEALTH_PLUGIN.md` - Full documentation
   - `health_test_data.json` - Examples

3. Test with automation script:
   ```bash
   python health_automation_example.py --user test --action morning_routine
   ```

### Common Issues

See `HEALTH_PLUGIN.md` → Troubleshooting section

## Success Criteria

Deployment is successful when:

- ✅ All tests pass (`./test_health.sh`)
- ✅ No errors in logs
- ✅ Users can import health data
- ✅ AI analysis works (sleep, workouts, etc.)
- ✅ Google Fit sync works (if configured)
- ✅ Anomaly detection working
- ✅ Health-memory correlations working

## Next Steps After Deployment

1. **User Onboarding**
   - Guide users through Google Fit setup
   - Provide sample data import files
   - Explain goal setting

2. **Feature Promotion**
   - Announce new health features
   - Create tutorial videos
   - Share wellness report examples

3. **Feedback Collection**
   - Monitor user engagement
   - Collect feedback on AI suggestions
   - Identify most used features

4. **Iteration**
   - Improve AI prompts based on feedback
   - Add requested features
   - Optimize performance

---

**Deployment Date:** _______________

**Deployed By:** _______________

**Version:** 1.0.0

**Sign-off:** _______________
