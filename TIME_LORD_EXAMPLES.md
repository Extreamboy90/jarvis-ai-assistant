# Time Lord - Esempi di Utilizzo

Guida completa per testare le nuove funzionalità di timeline e analisi temporale della memoria.

## Setup

Prima di testare, assicurati che il servizio orchestrator sia in esecuzione:

```bash
# Avvia i servizi
docker-compose up -d --build orchestrator

# Verifica che sia attivo
curl http://localhost:8000/health
```

## 1. Query Timeline - Memorie in Range Temporale

### Esempio Base (senza filtro semantico)

```bash
# Recupera memorie di Marzo 2025
curl -X GET "http://localhost:8000/memories/test_user/timeline?start_date=2025-03-01&end_date=2025-03-30"
```

**Risposta:**
```json
{
  "user_id": "test_user",
  "start_date": "2025-03-01",
  "end_date": "2025-03-30",
  "query": null,
  "total": 15,
  "memories": [
    {
      "snippet": "L'utente lavora nel settore energia in Sardegna",
      "category": "fatto",
      "importance": 8,
      "created_at": "2025-03-15T10:30:00",
      "access_count": 5,
      "obsolete": false
    }
    // ... altre memorie
  ]
}
```

### Con Filtro Semantico

```bash
# Cerca memorie su "lavoro" in Marzo 2025
curl -X GET "http://localhost:8000/memories/test_user/timeline?start_date=2025-03-01&end_date=2025-03-30&query=lavoro"
```

**Risposta include similarity score:**
```json
{
  "memories": [
    {
      "snippet": "Lavora nel settore energia",
      "similarity": 0.87,
      "importance": 8,
      ...
    }
  ]
}
```

### Range Temporale Personalizzato

```bash
# Ultime 2 settimane
curl -X GET "http://localhost:8000/memories/test_user/timeline?start_date=2025-03-16&end_date=2025-03-30&limit=100"

# Tutto l'anno 2024
curl -X GET "http://localhost:8000/memories/test_user/timeline?start_date=2024-01-01&end_date=2024-12-31"

# Cerca hobby negli ultimi 6 mesi
curl -X GET "http://localhost:8000/memories/test_user/timeline?start_date=2024-10-01&end_date=2025-03-30&query=hobby"
```

## 2. Riassunto Periodo - Summary Generato da LLM

### Riassunto Settimanale

```bash
curl -X GET "http://localhost:8000/memories/test_user/summary?period=week"
```

**Risposta:**
```json
{
  "period": "week",
  "start_date": "2025-03-23T...",
  "end_date": "2025-03-30T...",
  "summary": "Nell'ultima settimana hai parlato principalmente di lavoro e progetti personali. Hai menzionato un nuovo interesse per la fotografia e hai discusso di come organizzare meglio il tuo tempo libero. Emerge una crescente attenzione al bilanciamento vita-lavoro.",
  "stats": {
    "total": 12,
    "by_category": {
      "fatto": 5,
      "preferenza": 4,
      "richiesta": 3
    },
    "avg_importance": 6.5
  },
  "top_memories": [
    // Top 10 memorie del periodo
  ]
}
```

### Riassunto Mensile

```bash
curl -X GET "http://localhost:8000/memories/test_user/summary?period=month"
```

### Riassunto Annuale

```bash
curl -X GET "http://localhost:8000/memories/test_user/summary?period=year"
```

## 3. Temi Ricorrenti - Pattern Recognition

### Analisi Standard (30 giorni)

```bash
curl -X GET "http://localhost:8000/memories/test_user/themes"
```

**Risposta:**
```json
{
  "timeframe_days": 30,
  "total_memories": 45,
  "themes": [
    {
      "theme": "fatto",
      "occurrences": 18,
      "percentage": 40.0,
      "examples": [
        "Lavora nel settore energia",
        "Vive in Sardegna",
        "Ha un cane di nome Max"
      ]
    },
    {
      "theme": "preferenza",
      "occurrences": 12,
      "percentage": 26.7,
      "examples": [
        "Preferisce caffè nero",
        "Ama la musica jazz",
        "Odia i film horror"
      ]
    }
  ],
  "keywords": [
    {"word": "lavoro", "count": 15},
    {"word": "preferisce", "count": 12},
    {"word": "sardegna", "count": 8}
  ]
}
```

### Analisi Personalizzata

```bash
# Ultimi 60 giorni, minimo 5 occorrenze
curl -X GET "http://localhost:8000/memories/test_user/themes?days=60&min_occurrences=5"

# Ultimi 3 mesi, minimo 2 occorrenze
curl -X GET "http://localhost:8000/memories/test_user/themes?days=90&min_occurrences=2"
```

## 4. Statistiche Memoria - Overview Completo

```bash
curl -X GET "http://localhost:8000/memories/test_user/stats"
```

**Risposta:**
```json
{
  "user_id": "test_user",
  "overview": {
    "total_memories": 156,
    "active_memories": 142,
    "obsolete_memories": 14,
    "avg_importance": 6.3,
    "max_importance": 10,
    "min_importance": 3,
    "avg_access_count": 2.5,
    "oldest_memory": "2024-06-15T10:00:00",
    "newest_memory": "2025-03-30T14:30:00"
  },
  "by_category": [
    {
      "category": "fatto",
      "count": 58,
      "avg_importance": 7.2,
      "avg_access_count": 3.1
    },
    {
      "category": "preferenza",
      "count": 42,
      "avg_importance": 6.0,
      "avg_access_count": 2.3
    }
  ],
  "timeline": [
    {"month": "2025-03", "count": 23},
    {"month": "2025-02", "count": 18},
    {"month": "2025-01", "count": 15}
  ],
  "top_memories": [
    // Top 5 memorie più importanti
  ],
  "most_accessed": [
    // Top 5 memorie più accedute
  ]
}
```

## 5. Recap Annuale - Life Recap

```bash
# Recap anno 2024
curl -X GET "http://localhost:8000/memories/test_user/recap?year=2024"
```

**Risposta:**
```json
{
  "user_id": "test_user",
  "year": 2024,
  "recap": "Il 2024 è stato un anno di grandi cambiamenti per te. Hai iniziato un nuovo lavoro nel settore energia, ti sei trasferito in Sardegna e hai sviluppato nuove passioni come la fotografia e il trekking. I mesi estivi sono stati particolarmente intensi, con molti viaggi e nuove esperienze. Verso la fine dell'anno hai iniziato a concentrarti maggiormente sul bilanciamento vita-lavoro e sul benessere personale...",
  "stats": {
    "total_memories": 287,
    "by_month": {
      "Gennaio": 18,
      "Febbraio": 22,
      "Marzo": 25,
      // ...
      "Dicembre": 20
    },
    "by_category": {
      "fatto": 98,
      "preferenza": 72,
      "richiesta": 45,
      "nome": 3
    },
    "most_active_month": {
      "month": "Agosto",
      "count": 35
    },
    "avg_importance": 6.8
  },
  "highlights": [
    {
      "snippet": "Ha cambiato lavoro e si è trasferito in Sardegna",
      "date": "2024-03-15",
      "category": "fatto",
      "importance": 10
    }
    // ... top 10 highlights dell'anno
  ]
}
```

```bash
# Recap anno corrente (2025)
curl -X GET "http://localhost:8000/memories/test_user/recap?year=2025"
```

## 6. Analisi Mood - Sentiment Analysis

### Analisi Standard (30 giorni)

```bash
curl -X GET "http://localhost:8000/memories/test_user/mood"
```

**Risposta:**
```json
{
  "user_id": "test_user",
  "timeframe_days": 30,
  "total_memories_analyzed": 45,
  "analysis": {
    "overall_mood": "positivo",
    "mood_description": "Le conversazioni mostrano un tono generalmente positivo e costruttivo. Emerge entusiasmo per nuovi progetti e interesse per il miglioramento personale.",
    "emotional_keywords": [
      "entusiasta",
      "motivato",
      "curioso",
      "soddisfatto",
      "determinato"
    ],
    "positive_aspects": [
      "Nuovi interessi e hobby",
      "Crescita professionale",
      "Relazioni sociali positive"
    ],
    "concerns": [
      "Gestione del tempo",
      "Equilibrio vita-lavoro"
    ],
    "trend": "miglioramento"
  },
  "stats": {
    "avg_importance": 6.5,
    "categories": {
      "fatto": 18,
      "preferenza": 15,
      "richiesta": 12
    }
  }
}
```

### Analisi Personalizzata

```bash
# Ultimi 60 giorni
curl -X GET "http://localhost:8000/memories/test_user/mood?days=60"

# Ultimi 7 giorni (settimana)
curl -X GET "http://localhost:8000/memories/test_user/mood?days=7"
```

## 7. Topic Evolution - Tracking Argomenti

### Esempio: Traccia "lavoro"

```bash
curl -X GET "http://localhost:8000/memories/test_user/topic/lavoro"
```

**Risposta:**
```json
{
  "user_id": "test_user",
  "topic": "lavoro",
  "timeframe_days": 90,
  "total_mentions": 28,
  "trend": "crescente",
  "timeline": [
    {
      "month": "2025-03",
      "count": 12,
      "avg_importance": 7.5,
      "avg_similarity": 0.82,
      "top_snippets": [
        "Nuovo progetto al lavoro sulle energie rinnovabili",
        "Meeting importante con il team",
        "Promozione ricevuta"
      ]
    },
    {
      "month": "2025-02",
      "count": 10,
      "avg_importance": 6.8,
      "avg_similarity": 0.79,
      "top_snippets": [
        "Lavora su analisi dati energetici",
        "Corso di formazione completato",
        "Collaborazione con team tedesco"
      ]
    }
  ],
  "recent_highlights": [
    {
      "snippet": "Promosso a Senior Analyst",
      "date": "2025-03-25",
      "importance": 9,
      "similarity": 0.89
    }
    // ... altri highlights recenti
  ]
}
```

### Altri Esempi di Topic

```bash
# Traccia hobby
curl -X GET "http://localhost:8000/memories/test_user/topic/hobby?days=180"

# Traccia famiglia
curl -X GET "http://localhost:8000/memories/test_user/topic/famiglia?days=365"

# Traccia salute
curl -X GET "http://localhost:8000/memories/test_user/topic/salute?days=90"

# Traccia viaggi
curl -X GET "http://localhost:8000/memories/test_user/topic/viaggi?days=365"
```

## 8. Testing Completo - Script Bash

Crea questo script per testare tutti gli endpoint:

```bash
#!/bin/bash
# test_time_lord.sh

USER_ID="test_user"
BASE_URL="http://localhost:8000"

echo "=== Testing Time Lord API ==="
echo ""

echo "1. Timeline (ultimi 30 giorni)"
curl -s "${BASE_URL}/memories/${USER_ID}/timeline?start_date=2025-03-01&end_date=2025-03-30" | jq '.total'
echo ""

echo "2. Summary settimanale"
curl -s "${BASE_URL}/memories/${USER_ID}/summary?period=week" | jq '.summary' | head -n 3
echo ""

echo "3. Temi ricorrenti"
curl -s "${BASE_URL}/memories/${USER_ID}/themes" | jq '.themes[0]'
echo ""

echo "4. Statistiche memoria"
curl -s "${BASE_URL}/memories/${USER_ID}/stats" | jq '.overview'
echo ""

echo "5. Analisi mood"
curl -s "${BASE_URL}/memories/${USER_ID}/mood?days=30" | jq '.analysis.overall_mood'
echo ""

echo "6. Topic evolution: lavoro"
curl -s "${BASE_URL}/memories/${USER_ID}/topic/lavoro?days=90" | jq '.trend'
echo ""

echo "7. Recap annuale 2025"
curl -s "${BASE_URL}/memories/${USER_ID}/recap?year=2025" | jq '.stats.total_memories'
echo ""

echo "=== Test completato ==="
```

Esegui:
```bash
chmod +x test_time_lord.sh
./test_time_lord.sh
```

## 9. Query Avanzate con jq

### Filtra memorie per categoria

```bash
curl -s "http://localhost:8000/memories/test_user/timeline?start_date=2025-01-01&end_date=2025-03-30" \
  | jq '.memories[] | select(.category == "fatto")'
```

### Top 5 memorie più importanti nel periodo

```bash
curl -s "http://localhost:8000/memories/test_user/timeline?start_date=2025-01-01&end_date=2025-03-30" \
  | jq '.memories | sort_by(.importance) | reverse | .[0:5]'
```

### Conta memorie per categoria

```bash
curl -s "http://localhost:8000/memories/test_user/timeline?start_date=2025-01-01&end_date=2025-03-30" \
  | jq '.memories | group_by(.category) | map({category: .[0].category, count: length})'
```

### Memorie con similarity > 0.8

```bash
curl -s "http://localhost:8000/memories/test_user/timeline?start_date=2025-01-01&end_date=2025-03-30&query=lavoro" \
  | jq '.memories[] | select(.similarity > 0.8)'
```

## 10. Python Testing Script

Per test più avanzati, usa Python:

```python
#!/usr/bin/env python3
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"
USER_ID = "test_user"

def test_timeline():
    """Test timeline query"""
    end_date = datetime.now().isoformat()[:10]
    start_date = (datetime.now() - timedelta(days=30)).isoformat()[:10]

    response = requests.get(
        f"{BASE_URL}/memories/{USER_ID}/timeline",
        params={
            "start_date": start_date,
            "end_date": end_date,
            "query": "lavoro"
        }
    )

    data = response.json()
    print(f"Timeline: {data['total']} memories found")

    for mem in data['memories'][:3]:
        print(f"  - {mem['snippet'][:50]}... (sim: {mem.get('similarity', 'N/A')})")

def test_summary():
    """Test period summary"""
    response = requests.get(
        f"{BASE_URL}/memories/{USER_ID}/summary",
        params={"period": "month"}
    )

    data = response.json()
    print(f"\nSummary: {data['summary'][:150]}...")

def test_stats():
    """Test memory stats"""
    response = requests.get(f"{BASE_URL}/memories/{USER_ID}/stats")
    data = response.json()

    print(f"\nStats:")
    print(f"  Total: {data['overview']['total_memories']}")
    print(f"  Active: {data['overview']['active_memories']}")
    print(f"  Avg Importance: {data['overview']['avg_importance']}")

if __name__ == "__main__":
    test_timeline()
    test_summary()
    test_stats()
```

Esegui:
```bash
python3 test_time_lord.py
```

## Troubleshooting

### Errore: No memories found

Se ricevi sempre risposte vuote, verifica che ci siano dati nel database:

```bash
docker exec jarvis-postgres psql -U jarvis -d jarvis -c "SELECT COUNT(*) FROM memory_snippets WHERE user_id = 'test_user';"
```

### Errore: LLM timeout

Se gli endpoint summary/mood/recap vanno in timeout, aumenta il timeout:

```bash
curl -X GET --max-time 120 "http://localhost:8000/memories/test_user/summary?period=month"
```

### Check logs

```bash
docker-compose logs -f orchestrator | grep -i "time lord\|timeline\|recap"
```

## Best Practices

1. **Date Format**: Usa sempre formato ISO `YYYY-MM-DD`
2. **Limit**: Per dataset grandi, aumenta gradualmente il limit
3. **Semantic Search**: Usa query brevi e specifiche (2-3 parole)
4. **Period Summary**: Per periodi lunghi (year), potrebbe richiedere 30-60s
5. **Caching**: Considera di cachare risposte pesanti (recap, mood) in Redis

## Note di Performance

- **Timeline query**: ~50-200ms (senza semantic search)
- **Timeline + semantic**: ~200-500ms (con embedding)
- **Summary/Recap**: ~5-30s (richiede LLM)
- **Stats**: ~100-300ms (solo DB query)
- **Themes**: ~200-800ms (elaborazione locale)
- **Mood**: ~10-40s (richiede LLM)

---

**Enjoy your Time Lord powers!** 🕰️✨
