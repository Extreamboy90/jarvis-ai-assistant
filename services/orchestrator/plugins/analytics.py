"""
Analytics Plugin - Advanced Memory Analysis
Provides mood tracking, topic evolution, and life recap features
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import Counter
import database
from memory import query_timeline, get_embedding, _embedding_to_pg

logger = logging.getLogger(__name__)


async def analyze_mood_trends(
    user_id: str,
    days: int = 30,
    gemini_client=None,
    ollama_url: str = None,
    ollama_model: str = None
) -> Dict:
    """
    Analizza il tono emotivo delle conversazioni nel tempo.

    Args:
        user_id: ID dell'utente
        days: Giorni da analizzare (default 30)
        gemini_client: Client Gemini per analisi
        ollama_url: URL Ollama fallback
        ollama_model: Modello Ollama fallback

    Returns:
        Dict con trend del mood e analisi temporale
    """
    try:
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        end_date = datetime.now().isoformat()

        # Recupera memorie del periodo
        memories = await query_timeline(user_id, start_date, end_date, limit=200)

        if not memories:
            return {
                "timeframe_days": days,
                "message": "Nessuna memoria da analizzare nel periodo specificato"
            }

        # Analizza con LLM
        memories_text = "\n".join([
            f"[{m['created_at'][:10]}] {m['snippet']}"
            for m in memories[:100]  # Limita per token budget
        ])

        prompt = f"""Analizza il tono emotivo di queste memorie degli ultimi {days} giorni.

Memorie:
{memories_text}

Fornisci un'analisi JSON con:
1. "overall_mood": mood generale (positivo/neutro/negativo/misto)
2. "mood_description": descrizione del mood (2-3 frasi)
3. "emotional_keywords": lista di 5 parole chiave emotive
4. "positive_aspects": lista di aspetti positivi emersi
5. "concerns": lista di eventuali preoccupazioni o problemi
6. "trend": tendenza nel tempo (miglioramento/stabile/peggioramento)

Rispondi SOLO con un JSON valido."""

        response_text = ""

        # Prova Gemini
        if gemini_client and gemini_client.check_availability():
            try:
                result = gemini_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    use_smart=True,
                    temperature=0.5,
                    max_tokens=512
                )
                response_text = result.get("message", "")
                logger.info(f"Mood analysis via Gemini for {user_id}")
            except Exception as e:
                logger.warning(f"Gemini mood analysis failed: {e}")

        # Fallback Ollama
        if not response_text and ollama_url and ollama_model:
            import requests
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": ollama_model, "prompt": prompt, "stream": False},
                timeout=60
            )
            if response.status_code == 200:
                response_text = response.json().get("response", "")
                logger.info(f"Mood analysis via Ollama for {user_id}")

        # Parsa risposta
        import json
        import re

        mood_data = {}
        if response_text:
            try:
                # Rimuovi markdown code blocks
                response_text = re.sub(r"```(?:json)?", "", response_text).strip().rstrip("`")
                if "[" in response_text or "{" in response_text:
                    start = max(response_text.find("{"), 0)
                    end = response_text.rfind("}") + 1
                    mood_data = json.loads(response_text[start:end])
            except json.JSONDecodeError:
                logger.warning("Failed to parse mood analysis JSON")

        # Statistiche base
        categories = Counter([m["category"] for m in memories])
        avg_importance = sum(m["importance"] for m in memories) / len(memories)

        return {
            "user_id": user_id,
            "timeframe_days": days,
            "total_memories_analyzed": len(memories),
            "analysis": mood_data,
            "stats": {
                "avg_importance": round(avg_importance, 2),
                "categories": dict(categories.most_common(5)),
                "date_range": {
                    "start": start_date[:10],
                    "end": end_date[:10]
                }
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing mood trends: {e}")
        return {
            "user_id": user_id,
            "timeframe_days": days,
            "error": str(e)
        }


async def track_topic_evolution(
    user_id: str,
    topic: str,
    days: int = 90
) -> Dict:
    """
    Traccia come si è evoluto un argomento specifico nel tempo.

    Args:
        user_id: ID dell'utente
        topic: Argomento da tracciare
        days: Giorni da analizzare

    Returns:
        Dict con evoluzione del topic nel tempo
    """
    try:
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        end_date = datetime.now().isoformat()

        # Recupera memorie correlate al topic (semantic search)
        memories = await query_timeline(user_id, start_date, end_date, query=topic, limit=100)

        if not memories:
            return {
                "user_id": user_id,
                "topic": topic,
                "timeframe_days": days,
                "message": f"Nessuna memoria trovata relativa a '{topic}' negli ultimi {days} giorni"
            }

        # Raggruppa per mese
        by_month = {}
        for m in memories:
            month = m["created_at"][:7]  # YYYY-MM
            if month not in by_month:
                by_month[month] = []
            by_month[month].append(m)

        # Crea timeline
        timeline = []
        for month in sorted(by_month.keys()):
            month_memories = by_month[month]
            timeline.append({
                "month": month,
                "count": len(month_memories),
                "avg_importance": round(
                    sum(m["importance"] for m in month_memories) / len(month_memories),
                    2
                ),
                "avg_similarity": round(
                    sum(m.get("similarity", 0) for m in month_memories) / len(month_memories),
                    3
                ) if "similarity" in month_memories[0] else None,
                "top_snippets": [m["snippet"] for m in month_memories[:3]]
            })

        # Calcola trend
        if len(timeline) >= 2:
            first_month_count = timeline[0]["count"]
            last_month_count = timeline[-1]["count"]
            if last_month_count > first_month_count * 1.2:
                trend = "crescente"
            elif last_month_count < first_month_count * 0.8:
                trend = "decrescente"
            else:
                trend = "stabile"
        else:
            trend = "dati insufficienti"

        logger.info(
            f"Topic evolution tracked for {user_id}: '{topic}' - "
            f"{len(memories)} memories, trend: {trend}"
        )

        return {
            "user_id": user_id,
            "topic": topic,
            "timeframe_days": days,
            "total_mentions": len(memories),
            "trend": trend,
            "timeline": timeline,
            "recent_highlights": [
                {
                    "snippet": m["snippet"],
                    "date": m["created_at"][:10],
                    "importance": m["importance"],
                    "similarity": m.get("similarity")
                }
                for m in memories[:5]
            ]
        }

    except Exception as e:
        logger.error(f"Error tracking topic evolution: {e}")
        return {
            "user_id": user_id,
            "topic": topic,
            "timeframe_days": days,
            "error": str(e)
        }


async def generate_life_recap(
    user_id: str,
    year: int,
    gemini_client=None,
    ollama_url: str = None,
    ollama_model: str = None
) -> Dict:
    """
    Genera un recap annuale con insight e statistiche.

    Args:
        user_id: ID dell'utente
        year: Anno da analizzare
        gemini_client: Client Gemini per generazione recap
        ollama_url: URL Ollama fallback
        ollama_model: Modello Ollama fallback

    Returns:
        Dict con recap annuale strutturato
    """
    try:
        start_date = f"{year}-01-01T00:00:00"
        end_date = f"{year}-12-31T23:59:59"

        # Recupera tutte le memorie dell'anno
        memories = await query_timeline(user_id, start_date, end_date, limit=1000)

        if not memories:
            return {
                "user_id": user_id,
                "year": year,
                "message": f"Nessuna memoria trovata per l'anno {year}"
            }

        # Analizza per mese
        by_month = {}
        for m in memories:
            month = int(m["created_at"][5:7])  # Estrai mese
            month_name = [
                "", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
            ][month]

            if month_name not in by_month:
                by_month[month_name] = []
            by_month[month_name].append(m)

        # Statistiche per categoria
        by_category = Counter([m["category"] for m in memories])

        # Top memorie più importanti
        top_memories = sorted(memories, key=lambda x: x["importance"], reverse=True)[:10]

        # Prepara contesto per LLM
        memories_summary = "\n\n".join([
            f"**{month}** ({len(mems)} memorie):\n" +
            "\n".join(f"- {m['snippet']}" for m in mems[:5])
            for month, mems in by_month.items()
        ])

        prompt = f"""Crea un recap coinvolgente dell'anno {year} basato su queste memorie.

{memories_summary}

Il recap deve includere:
1. **Highlights dell'anno**: i momenti più significativi
2. **Temi ricorrenti**: cosa ha caratterizzato quest'anno
3. **Crescita personale**: come sei cambiato/a
4. **Riflessioni**: insight interessanti emersi

Scrivi in modo narrativo e personale (max 400 parole). Usa il tono di un amico che ricorda insieme all'utente l'anno trascorso."""

        response_text = ""

        # Prova Gemini
        if gemini_client and gemini_client.check_availability():
            try:
                result = gemini_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    use_smart=True,
                    temperature=0.8,
                    max_tokens=800
                )
                response_text = result.get("message", "")
                logger.info(f"Life recap generated via Gemini for {user_id}")
            except Exception as e:
                logger.warning(f"Gemini recap failed: {e}")

        # Fallback Ollama
        if not response_text and ollama_url and ollama_model:
            import requests
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": ollama_model, "prompt": prompt, "stream": False},
                timeout=90
            )
            if response.status_code == 200:
                response_text = response.json().get("response", "")
                logger.info(f"Life recap generated via Ollama for {user_id}")

        if not response_text:
            response_text = f"Hai creato {len(memories)} memorie nel {year}, ma non riesco a generare un recap dettagliato."

        # Mese più attivo
        most_active_month = max(by_month.items(), key=lambda x: len(x[1]))

        return {
            "user_id": user_id,
            "year": year,
            "recap": response_text.strip(),
            "stats": {
                "total_memories": len(memories),
                "by_month": {month: len(mems) for month, mems in by_month.items()},
                "by_category": dict(by_category.most_common()),
                "most_active_month": {
                    "month": most_active_month[0],
                    "count": len(most_active_month[1])
                },
                "avg_importance": round(
                    sum(m["importance"] for m in memories) / len(memories),
                    2
                )
            },
            "highlights": [
                {
                    "snippet": m["snippet"],
                    "date": m["created_at"][:10],
                    "category": m["category"],
                    "importance": m["importance"]
                }
                for m in top_memories[:10]
            ]
        }

    except Exception as e:
        logger.error(f"Error generating life recap: {e}")
        return {
            "user_id": user_id,
            "year": year,
            "error": str(e)
        }


# Nota: Le funzioni analytics NON sono esposte come plugin functions callable dal LLM
# perché sono funzioni di analisi che richiedono parametri complessi.
# Vengono chiamate direttamente dagli endpoint HTTP in app.py.
