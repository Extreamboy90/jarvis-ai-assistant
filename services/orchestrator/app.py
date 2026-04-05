"""
Jarvis AI Assistant — Orchestrator (FastAPI)

Fix applicati rispetto alla versione precedente:
- [BUG#1] min_importance abbassato da 6 a 3 nel retrieval
- [BUG#2] Formato memoria strutturato ([MEMORIA UTENTE] + lista) invece di stringa piatta
- [BUG#3] use_smart=True passato esplicitamente nella final_response call (evita doppia analisi intent)
- [BUG#4] WebSocket: aggiunto contesto data/ora (mancava completamente)
- [BUG#5] WebSocket: aggiunto memory context con stesso formato dell'endpoint HTTP
- [IMPROVE] should_use_smart_model chiamato UNA sola volta per chat (era chiamato 2-3 volte)
- [IMPROVE] Separazione _build_system_context() per evitare duplicazione HTTP/WebSocket
- [IMPROVE] Pre-check lunghezza messaggio prima di extract_memories_background
"""

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
import locale

import requests
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database
from database import (
    init_db, close_db,
    add_message, get_conversation_history,
    log_interaction, log_function_call,
    clear_conversation as db_clear_conversation
)
from gemini_client import GeminiClient
import memory
from memory import (
    retrieve_relevant_memories,
    process_conversation_for_memories,
    format_memories_for_prompt,
)
from plugins import PluginManager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Jarvis Orchestrator…")
    await init_db()
    yield
    logger.info("Shutting down…")
    await close_db()

app = FastAPI(title="Jarvis AI Orchestrator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In produzione: specifica gli origin esatti
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────────────────────────────────────

STT_SERVICE_URL = os.getenv("STT_SERVICE_URL", "http://stt:8001")
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://tts:8002")
OLLAMA_URL      = os.getenv("OLLAMA_URL", "http://ollama:11434")

OLLAMA_MODEL_FAST  = os.getenv("OLLAMA_MODEL_FAST",  "gemma3:1b")
OLLAMA_MODEL_SMART = os.getenv("OLLAMA_MODEL_SMART", "llama3.1:8b")
OLLAMA_MODEL       = OLLAMA_MODEL_FAST  # retrocompatibilità

gemini_client = GeminiClient()
USE_GEMINI    = os.getenv("USE_GEMINI", "true").lower() == "true"

if USE_GEMINI and gemini_client.check_availability():
    logger.info("🚀 Using Google Gemini API (primary LLM)")
else:
    logger.info("🏠 Using local Ollama (Gemini not available)")

plugin_manager = PluginManager()

PLUGINS_TO_LOAD = ["system", "tuya", "calendar", "web_search", "context_dashboard", "health"]
for plugin_name in PLUGINS_TO_LOAD:
    try:
        plugin_manager.load_plugin(plugin_name)
        logger.info(f"✅ Plugin loaded: {plugin_name}")
    except Exception as e:
        logger.error(f"❌ Failed to load plugin {plugin_name}: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    max_history: int = 3
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    function_calls: Optional[List[Dict]] = None

# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT BUILDER — unica funzione condivisa tra HTTP e WebSocket
# ─────────────────────────────────────────────────────────────────────────────

def _build_datetime_context() -> str:
    """
    Costruisce il contesto data/ora da iniettare nel system prompt.
    Centralizzato qui per essere identico in HTTP e WebSocket.
    [BUG#4 FIX: il WebSocket non aveva questo contesto]
    """
    try:
        locale.setlocale(locale.LC_TIME, "it_IT.UTF-8")
    except Exception:
        pass

    now  = datetime.now()
    year = now.year
    return (
        f"Data e ora corrente: {now.strftime('%A %d %B %Y, ore %H:%M:%S')}. "
        f"Siamo nell'anno {year}. "
        f"Quando fai ricerche web, specifica sempre l'anno {year} nelle query."
    )


async def _build_system_context(user_id: str, query: str) -> str:
    """
    Costruisce il system context completo:
    - data/ora corrente
    - memorie rilevanti (se presenti)

    [BUG#1 FIX] min_importance=3 invece di 6
    [BUG#2 FIX] formato strutturato via format_memories_for_prompt()
    [BUG#4 FIX] funzione centralizzata usata sia in HTTP che WebSocket
    """
    datetime_ctx = _build_datetime_context()

    relevant_memories = await retrieve_relevant_memories(
        user_id=user_id,
        query=query,
        limit=5,
        min_importance=3,   # [BUG#1 FIX] era 6 → troppo restrittivo
    )

    if relevant_memories:
        memory_ctx = format_memories_for_prompt(relevant_memories)  # [BUG#2 FIX] lista strutturata
        logger.info(f"Injecting {len(relevant_memories)} memories into context")
        return datetime_ctx + "\n\n" + memory_ctx

    return datetime_ctx

# ─────────────────────────────────────────────────────────────────────────────
# INTENT ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def _analyze_intent_with_gemini(message: str) -> Dict:
    """
    Analizza l'intenzione del messaggio utente con Gemini (modello fast).
    Ritorna {'needs_function_call': bool, 'reason': str}.
    """
    try:
        if not USE_GEMINI or not gemini_client.check_availability():
            return {"needs_function_call": False, "reason": "Gemini not available"}

        prompt = f"""Analizza questa richiesta utente e rispondi SOLO con un JSON.

Messaggio: "{message}"

Determina se richiede:
- Ricerca web (notizie, eventi, meteo, prezzi)
- Funzioni di sistema (ora, data, info hardware)
- Controllo domotica (luci, dispositivi smart)
- Calendario (eventi, appuntamenti)
- Memoria/informazioni personali

Rispondi SOLO con:
{{"needs_function_call": true/false, "reason": "breve spiegazione"}}

Conversazione generica (saluti, domande semplici) → false."""

        result = gemini_client.chat(
            messages=[{"role": "user", "content": prompt}],
            functions=None,
            use_smart=False,
            temperature=0.3,
            max_tokens=100
        )

        response_text = re.sub(r"```(?:json)?", "", result.get("message", "")).strip().rstrip("`").strip()
        json_match = re.search(r'\{[^{}]*"needs_function_call"[^{}]*\}', response_text, re.DOTALL)

        if json_match:
            intent_data = json.loads(json_match.group())
            logger.info(
                f"Intent: needs_function={intent_data.get('needs_function_call')}, "
                f"reason={intent_data.get('reason', '')[:50]}"
            )
            return intent_data

        # Fallback: parsing diretto
        return json.loads(response_text)

    except Exception as e:
        logger.error(f"Intent analysis error: {e}")
        return {"needs_function_call": True, "reason": f"Error fallback: {str(e)}"}


def _should_use_smart_model(messages: List[Dict]) -> bool:
    """
    Decide se usare il modello smart o fast.
    [IMPROVE] Questa funzione viene ora chiamata UNA sola volta per request.
    """
    last_message = messages[-1].get("content", "") if messages else ""
    logger.info(f"Model selection for: '{last_message[:80]}'")

    if USE_GEMINI and gemini_client.check_availability():
        intent = _analyze_intent_with_gemini(last_message)
        return intent.get("needs_function_call", False)

    # Fallback keyword matching
    keywords = [
        "accendi", "spegni", "controlla", "attiva", "disattiva",
        "esegui", "apri", "chiudi", "imposta", "regola",
        "che ore", "che ora", "ora", "data", "quando", "giorno",
        "informazioni sistema", "sistema", "cpu", "disco", "memoria",
        "calendario", "impegni", "eventi", "appuntamento", "meeting",
        "cerca", "ricerca", "trova", "web", "internet", "online",
        "notizie", "gara", "partita", "chi ha vinto", "meteo", "tempo",
    ]
    last_lower = last_message.lower()
    for kw in keywords:
        if kw in last_lower:
            logger.info(f"Keyword matched (fallback): {kw}")
            return True

    return False

# ─────────────────────────────────────────────────────────────────────────────
# LLM CALL
# ─────────────────────────────────────────────────────────────────────────────

def _call_llm(
    messages: List[Dict],
    functions: Optional[List[Dict]] = None,
    use_smart: Optional[bool] = None
) -> Dict:
    """
    Chiama Gemini (primario) o Ollama (fallback).

    [BUG#3 FIX] use_smart deve essere passato esplicitamente nella chiamata
    finale dopo una function call — altrimenti viene ricalcolato con
    should_use_smart_model che fa un'altra chiamata Gemini inutile.
    """
    try:
        # [IMPROVE] use_smart calcolato UNA volta dall'esterno, non qui
        if use_smart is None:
            use_smart = _should_use_smart_model(messages)

        if USE_GEMINI and gemini_client.check_availability():
            try:
                result = gemini_client.chat(
                    messages=messages,
                    functions=functions,
                    use_smart=use_smart,
                    temperature=0.7,
                    max_tokens=2048
                )
                return {
                    "message": {"role": "assistant", "content": result.get("message", "")},
                    "function_call": result.get("function_call")
                }
            except Exception as e:
                logger.error(f"Gemini error, falling back to Ollama: {e}")

        # Ollama fallback
        model = OLLAMA_MODEL_SMART if use_smart else OLLAMA_MODEL_FAST
        logger.info(f"Ollama model: {model} (smart={use_smart})")

        payload: Dict = {"model": model, "messages": messages, "stream": False}

        if functions:
            system_msg = {
                "role": "system",
                "content": (
                    "Sei Jarvis, assistente vocale italiano.\n\n"
                    f"Funzioni disponibili:\n{json.dumps(functions, indent=2, ensure_ascii=False)}\n\n"
                    'Se serve una funzione, rispondi SOLO con:\n'
                    '{"function": "nome_funzione", "parameters": {}}\n\n'
                    'Esempi:\n'
                    '- "che ore sono?" → {"function": "system_get_current_time", "parameters": {}}\n'
                    '- "info sistema" → {"function": "system_get_system_info", "parameters": {}}\n'
                    '- "ciao" → Ciao! Come posso aiutarti?'
                )
            }
            payload["messages"] = [system_msg] + messages

        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        response.raise_for_status()

        return {
            "message": response.json().get("message", {}),
            "function_call": None
        }

    except Exception as e:
        logger.error(f"LLM call error: {e}")
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")


def _parse_function_call(response_text: str) -> Optional[Dict]:
    """Parsa una function call JSON dalla risposta Ollama."""
    try:
        if "{" in response_text and "}" in response_text:
            start = response_text.find("{")
            end   = response_text.rfind("}") + 1
            data  = json.loads(response_text[start:end])
            if "function" in data:
                return data
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION EXECUTION (estratto per evitare duplicazione HTTP/WebSocket)
# ─────────────────────────────────────────────────────────────────────────────

async def _execute_function_call(
    function_call: Dict,
    user_id: str,
    session_id: Optional[str],
    assistant_message: str,
    history: List[Dict],
    use_smart: bool
) -> tuple[str, List[Dict]]:
    """
    Esegue una function call, salva il risultato, e chiama LLM per la risposta finale.

    [BUG#3 FIX] Passa use_smart=True alla chiamata LLM finale invece di None
    (evita che venga ricalcolato con una terza chiamata Gemini).

    Ritorna (assistant_message_finale, function_results).
    """
    function_results = []

    try:
        function_name = function_call["function"]
        parameters    = {k: v for k, v in function_call.get("parameters", {}).items() if k and k.strip()}

        t0     = time.time()
        result = plugin_manager.call_function(function_name, **parameters)
        exec_ms = int((time.time() - t0) * 1000)

        function_results.append({
            "function":   function_name,
            "parameters": parameters,
            "result":     result
        })

        assistant_msg_id = await add_message(user_id, "assistant", assistant_message, session_id)
        await log_function_call(assistant_msg_id, function_name, parameters, result, True, exec_ms)

        await add_message(
            user_id, "system",
            f"Risultato funzione: {json.dumps(result, ensure_ascii=False)}",
            session_id
        )

        # Aggiorna history con risultato funzione
        updated_history = await get_conversation_history(user_id, 5, session_id)

        # Aggiungi istruzione citazione fonti per web search
        if function_name == "web_search_search_web" and result.get("success") and result.get("results"):
            sources = [s.get("source", "Web") for s in result.get("results", [])[:2]]
            updated_history.append({
                "role": "system",
                "content": (
                    "IMPORTANTE: Cita le fonti quando rispondi. "
                    f"Fonti usate: {', '.join(sources)}"
                )
            })

        # [BUG#3 FIX] use_smart=True passato esplicitamente, evita 3a chiamata Gemini
        final_response   = _call_llm(updated_history, functions=None, use_smart=True)
        final_message    = final_response.get("message", {}).get("content", "")

        return final_message, function_results

    except Exception as e:
        logger.error(f"Function call error: {e}")
        return f"Mi dispiace, ho avuto un problema nell'eseguire l'azione: {str(e)}", []

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":    "healthy",
        "ollama":    OLLAMA_MODEL,
        "plugins":   list(plugin_manager.plugins.keys()),
        "functions": list(plugin_manager.functions.keys()),
        "gemini":    USE_GEMINI and gemini_client.check_availability(),
    }

@app.get("/functions")
async def list_functions():
    return {"functions": plugin_manager.get_functions_schema()}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Endpoint principale di chat.
    Tutti i fix applicati e logica semplificata rispetto alla versione originale.
    """
    try:
        t0 = time.time()

        await log_interaction(request.user_id, "chat", {"message": request.message})
        await add_message(request.user_id, "user", request.message, request.session_id)

        # Recupera history
        history = await get_conversation_history(request.user_id, request.max_history, request.session_id)
        logger.info(f"History: {(time.time()-t0)*1000:.0f}ms")

        # [BUG#1+2+4 FIX] Costruisce system context (data/ora + memoria)
        t = time.time()
        system_context = await _build_system_context(request.user_id, request.message)
        history.insert(0, {"role": "system", "content": system_context})
        logger.info(f"System context built: {(time.time()-t)*1000:.0f}ms")

        # [IMPROVE] should_use_smart_model chiamato UNA SOLA VOLTA
        t = time.time()
        use_smart        = _should_use_smart_model(history)
        functions_schema = plugin_manager.get_functions_schema() if use_smart else None
        logger.info(f"Model selection: {'smart' if use_smart else 'fast'} — {(time.time()-t)*1000:.0f}ms")

        # Prima chiamata LLM
        t = time.time()
        llm_response     = _call_llm(history, functions_schema, use_smart)
        assistant_message = llm_response.get("message", {}).get("content", "")
        logger.info(f"LLM call: {(time.time()-t)*1000:.0f}ms")

        # Gestione function call
        function_call    = llm_response.get("function_call") or _parse_function_call(assistant_message)
        function_results = []

        if function_call:
            logger.info(f"Function call: {function_call}")
            assistant_message, function_results = await _execute_function_call(
                function_call, request.user_id, request.session_id,
                assistant_message, history, use_smart  # [BUG#3 FIX]
            )
        else:
            await add_message(request.user_id, "assistant", assistant_message, request.session_id)

        # Salva risposta finale (se non già salvata da _execute_function_call)
        if not function_results:
            pass  # già salvato sopra
        else:
            await add_message(request.user_id, "assistant", assistant_message, request.session_id)

        # Estrazione memoria in background
        # [IMPROVE] Pre-check lunghezza prima di lanciare il task
        async def extract_memories_background():
            try:
                if len(request.message.strip()) < 12:
                    return  # Messaggio troppo corto, skip
                updated_history = await get_conversation_history(request.user_id, 5, request.session_id)
                saved = await process_conversation_for_memories(
                    request.user_id, updated_history,
                    gemini_client, OLLAMA_URL, OLLAMA_MODEL_SMART
                )
                if saved > 0:
                    logger.info(f"Background memory: {saved} facts saved for {request.user_id}")
            except Exception as e:
                logger.warning(f"Memory extraction error (non-critical): {e}")

        asyncio.create_task(extract_memories_background())

        logger.info(f"Total request time: {(time.time()-t0)*1000:.0f}ms")

        return ChatResponse(
            response=assistant_message,
            function_calls=function_results if function_results else None
        )

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversation/{user_id}")
async def clear_conversation(user_id: str, session_id: Optional[str] = None):
    await db_clear_conversation(user_id, session_id)
    return {"success": True, "message": f"Conversation cleared for {user_id}"}

@app.get("/memories/{user_id}")
async def get_user_memories(user_id: str, limit: int = 20):
    async with database.pg_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT snippet, category, importance, created_at, access_count,
                   (metadata->>'obsolete')::boolean AS obsolete
            FROM memory_snippets
            WHERE user_id = $1
            ORDER BY importance DESC, created_at DESC
            LIMIT $2
            """,
            user_id, limit
        )
        memories = [
            {
                "snippet":      row["snippet"],
                "category":     row["category"],
                "importance":   row["importance"],
                "created_at":   row["created_at"].isoformat(),
                "access_count": row["access_count"],
                "obsolete":     bool(row["obsolete"]),
            }
            for row in rows
        ]
        return {"user_id": user_id, "total": len(memories), "memories": memories}


# ─────────────────────────────────────────────────────────────────────────────
# TIME LORD ENDPOINTS - TIMELINE & TEMPORAL ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/memories/{user_id}/timeline")
async def get_memory_timeline(
    user_id: str,
    start_date: str,
    end_date: str,
    query: Optional[str] = None,
    limit: int = 50
):
    """
    Recupera memorie in un range temporale con optional semantic search.

    Query params:
        - start_date: Data inizio (formato ISO: YYYY-MM-DD)
        - end_date: Data fine (formato ISO: YYYY-MM-DD)
        - query: Query semantica opzionale
        - limit: Numero massimo risultati (default 50)

    Example:
        GET /memories/user123/timeline?start_date=2025-01-01&end_date=2025-03-30
        GET /memories/user123/timeline?start_date=2025-01-01&end_date=2025-03-30&query=lavoro
    """
    try:
        memories = await memory.query_timeline(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            query=query,
            limit=limit
        )

        return {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "query": query,
            "total": len(memories),
            "memories": memories
        }

    except Exception as e:
        logger.error(f"Timeline endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/{user_id}/summary")
async def get_period_summary(user_id: str, period: str = "week"):
    """
    Genera un riassunto del periodo specificato usando LLM.

    Query params:
        - period: Tipo di periodo (week|month|year)

    Example:
        GET /memories/user123/summary?period=month
    """
    if period not in ["week", "month", "year"]:
        raise HTTPException(
            status_code=400,
            detail="period must be 'week', 'month', or 'year'"
        )

    try:
        summary = await memory.generate_period_summary(
            user_id=user_id,
            period_type=period,
            gemini_client=gemini_client,
            ollama_url=OLLAMA_URL,
            ollama_model=OLLAMA_MODEL_SMART
        )

        return summary

    except Exception as e:
        logger.error(f"Summary endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/{user_id}/themes")
async def get_recurring_themes(
    user_id: str,
    days: int = 30,
    min_occurrences: int = 3
):
    """
    Identifica temi ricorrenti nelle memorie dell'utente.

    Query params:
        - days: Giorni da analizzare (default 30)
        - min_occurrences: Minimo occorrenze per tema (default 3)

    Example:
        GET /memories/user123/themes?days=60
    """
    try:
        themes = await memory.extract_recurring_themes(
            user_id=user_id,
            timeframe_days=days,
            min_occurrences=min_occurrences
        )

        return themes

    except Exception as e:
        logger.error(f"Themes endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/{user_id}/stats")
async def get_user_memory_stats(user_id: str):
    """
    Recupera statistiche complete sulla memoria dell'utente.

    Example:
        GET /memories/user123/stats
    """
    try:
        stats = await memory.get_memory_stats(user_id=user_id)
        return stats

    except Exception as e:
        logger.error(f"Stats endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/{user_id}/recap")
async def get_life_recap(user_id: str, year: int):
    """
    Genera un recap annuale con insight e statistiche.

    Query params:
        - year: Anno da analizzare (es. 2025)

    Example:
        GET /memories/user123/recap?year=2025
    """
    try:
        # Import analytics module
        import sys
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from plugins import analytics

        recap = await analytics.generate_life_recap(
            user_id=user_id,
            year=year,
            gemini_client=gemini_client,
            ollama_url=OLLAMA_URL,
            ollama_model=OLLAMA_MODEL_SMART
        )

        return recap

    except Exception as e:
        logger.error(f"Recap endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/{user_id}/mood")
async def analyze_user_mood(user_id: str, days: int = 30):
    """
    Analizza il tono emotivo delle conversazioni nel tempo.

    Query params:
        - days: Giorni da analizzare (default 30)

    Example:
        GET /memories/user123/mood?days=60
    """
    try:
        # Import analytics module
        import sys
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from plugins import analytics

        mood_analysis = await analytics.analyze_mood_trends(
            user_id=user_id,
            days=days,
            gemini_client=gemini_client,
            ollama_url=OLLAMA_URL,
            ollama_model=OLLAMA_MODEL_SMART
        )

        return mood_analysis

    except Exception as e:
        logger.error(f"Mood endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/{user_id}/topic/{topic}")
async def track_user_topic(user_id: str, topic: str, days: int = 90):
    """
    Traccia l'evoluzione di un topic specifico nel tempo.

    Path params:
        - topic: Argomento da tracciare

    Query params:
        - days: Giorni da analizzare (default 90)

    Example:
        GET /memories/user123/topic/lavoro?days=180
    """
    try:
        # Import analytics module
        import sys
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from plugins import analytics

        evolution = await analytics.track_topic_evolution(
            user_id=user_id,
            topic=topic,
            days=days
        )

        return evolution

    except Exception as e:
        logger.error(f"Topic tracking endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# MISSION CONTROL - DASHBOARD ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/dashboard/{user_id}/context")
async def get_dashboard_context(user_id: str, location: str = "Cagliari"):
    """
    Recupera tutti i dati contestuali per il dashboard (JSON).

    Query params:
        - location: Città per meteo e notizie (default: Cagliari)

    Example:
        GET /dashboard/user123/context?location=Milan

    Returns:
        JSON con calendario, meteo, casa, routine, notizie
    """
    try:
        result = plugin_manager.call_function(
            "context_dashboard_get_daily_context",
            user_id=user_id,
            location=location
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to get context")
            )

        return result.get("context", {})

    except Exception as e:
        logger.error(f"Dashboard context error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/{user_id}/briefing")
async def get_dashboard_briefing(
    user_id: str,
    time: str = "morning",
    location: str = "Cagliari",
    work_location: Optional[str] = None
):
    """
    Genera briefing completo personalizzato (morning/evening).

    Query params:
        - time: Momento del giorno (morning|evening) - default: morning
        - location: Città utente (default: Cagliari)
        - work_location: Destinazione lavoro per calcolo traffico (opzionale)

    Example:
        GET /dashboard/user123/briefing?time=morning&work_location=Rome

    Returns:
        JSON strutturato con briefing + versione vocale
    """
    try:
        if time not in ["morning", "evening"]:
            raise HTTPException(
                status_code=400,
                detail="time parameter must be 'morning' or 'evening'"
            )

        # Per ora implementiamo solo morning briefing
        # TODO: implementare evening briefing (recap giornata)
        if time == "evening":
            return {
                "success": False,
                "note": "Evening briefing not implemented yet",
                "user_id": user_id
            }

        result = plugin_manager.call_function(
            "context_dashboard_generate_morning_briefing",
            user_id=user_id,
            location=location,
            work_location=work_location
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate briefing")
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Briefing generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dashboard/{user_id}/briefing/tts")
async def briefing_to_speech(user_id: str, time: str = "morning"):
    """
    Genera briefing e converte in audio (TTS).

    Query params:
        - time: Momento del giorno (morning|evening)

    Returns:
        Audio WAV del briefing vocale
    """
    try:
        # Genera briefing
        briefing_result = await get_dashboard_briefing(user_id, time)

        if not briefing_result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to generate briefing")

        voice_text = briefing_result.get("voice_text", "")

        if not voice_text:
            raise HTTPException(status_code=500, detail="No voice text generated")

        # Chiama TTS service
        import requests
        tts_response = requests.post(
            f"{TTS_SERVICE_URL}/speak",
            json={"text": voice_text},
            timeout=30
        )

        tts_response.raise_for_status()

        # Ritorna audio
        from fastapi.responses import Response
        return Response(
            content=tts_response.content,
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"attachment; filename=briefing_{user_id}_{time}.wav"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS briefing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# HEALTH ENDPOINTS - NEURALINK INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

class HealthImportRequest(BaseModel):
    user_id: str
    source: str  # 'fitbit', 'apple_health', 'garmin', 'generic'
    file_content: str  # CSV or JSON content


@app.post("/health/{user_id}/sync")
async def sync_health_data_endpoint(user_id: str, source: str = "google_fit", days: int = 7):
    """
    Synchronize health data from Google Fit or file import.

    Query params:
        - source: 'google_fit' (default) or 'file'
        - days: Number of days to sync (default: 7)
    """
    try:
        result = plugin_manager.call_function(
            "health_sync_health_data",
            user_id=user_id,
            source=source,
            days=days
        )
        return result
    except Exception as e:
        logger.error(f"Health sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/health/{user_id}/import")
async def import_health_file(request: HealthImportRequest):
    """
    Import health data from CSV/JSON file export.

    Supported formats:
        - Fitbit CSV export
        - Apple Health JSON export
        - Garmin CSV export
        - Generic CSV (date, metric_type, value)
    """
    try:
        # Import health plugin to access parsers
        from plugins import health as health_plugin

        # Parse file based on source
        if request.source == "fitbit":
            data = health_plugin._parse_fitbit_export(request.file_content)
        elif request.source == "apple_health":
            data = health_plugin._parse_apple_health_export(request.file_content)
        elif request.source == "garmin":
            data = health_plugin._parse_garmin_export(request.file_content)
        elif request.source == "generic":
            data = health_plugin._parse_generic_csv(request.file_content)
        else:
            raise ValueError(f"Unsupported source: {request.source}")

        if not data:
            return {
                "success": False,
                "message": "No data could be parsed from file"
            }

        # Save to database
        saved = await health_plugin._save_health_data(request.user_id, data)

        return {
            "success": True,
            "source": request.source,
            "data_points_imported": saved,
            "message": f"Successfully imported {saved} data points from {request.source}"
        }

    except Exception as e:
        logger.error(f"Health import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/summary")
async def get_health_summary(user_id: str, period: str = "today"):
    """
    Get health summary for a period.

    Query params:
        - period: 'today', 'week', 'month' (default: 'today')
    """
    try:
        if period == "today":
            result = plugin_manager.call_function(
                "health_get_activity_summary",
                user_id=user_id
            )
        elif period in ["week", "month"]:
            result = plugin_manager.call_function(
                "health_generate_wellness_report",
                user_id=user_id,
                period=period
            )
        else:
            raise HTTPException(status_code=400, detail="period must be 'today', 'week', or 'month'")

        return result

    except Exception as e:
        logger.error(f"Health summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/sleep")
async def get_sleep_analysis_endpoint(user_id: str, days: int = 7):
    """
    Get sleep analysis with AI insights.

    Query params:
        - days: Number of days to analyze (default: 7)
    """
    try:
        result = plugin_manager.call_function(
            "health_get_sleep_analysis",
            user_id=user_id,
            days=days
        )
        return result
    except Exception as e:
        logger.error(f"Sleep analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/activity")
async def get_activity_endpoint(user_id: str, date: Optional[str] = None):
    """
    Get activity summary for a specific date.

    Query params:
        - date: Date in YYYY-MM-DD format (default: today)
    """
    try:
        result = plugin_manager.call_function(
            "health_get_activity_summary",
            user_id=user_id,
            date=date
        )
        return result
    except Exception as e:
        logger.error(f"Activity summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/heart-rate")
async def get_heart_rate_endpoint(user_id: str, days: int = 30):
    """
    Get heart rate trends.

    Query params:
        - days: Number of days to analyze (default: 30)
    """
    try:
        result = plugin_manager.call_function(
            "health_get_heart_rate_trends",
            user_id=user_id,
            days=days
        )
        return result
    except Exception as e:
        logger.error(f"Heart rate analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/goals")
async def get_health_goals(user_id: str):
    """Get user's health goals with progress."""
    try:
        async with database.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT goal_type, target_value, current_value, deadline,
                       ROUND((current_value::float / target_value::float) * 100) as progress_pct
                FROM health_goals
                WHERE user_id = $1
                """,
                user_id
            )

            goals = [
                {
                    "goal_type": row["goal_type"],
                    "target_value": float(row["target_value"]),
                    "current_value": float(row["current_value"]),
                    "progress_pct": int(row["progress_pct"]) if row["progress_pct"] else 0,
                    "deadline": row["deadline"].isoformat() if row["deadline"] else None
                }
                for row in rows
            ]

            return {
                "success": True,
                "user_id": user_id,
                "goals": goals
            }

    except Exception as e:
        logger.error(f"Get health goals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/health/{user_id}/goals")
async def set_health_goals_endpoint(user_id: str, goals: Dict[str, Any]):
    """
    Set or update health goals.

    Body: Dictionary of goals
        Example: {"steps": 10000, "sleep": 8, "workouts_per_week": 3}
    """
    try:
        result = plugin_manager.call_function(
            "health_set_health_goals",
            user_id=user_id,
            goals=goals
        )
        return result
    except Exception as e:
        logger.error(f"Set health goals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/wellness-report")
async def get_wellness_report(user_id: str, period: str = "week"):
    """
    Generate comprehensive wellness report.

    Query params:
        - period: 'today', 'week', 'month' (default: 'week')
    """
    try:
        result = plugin_manager.call_function(
            "health_generate_wellness_report",
            user_id=user_id,
            period=period
        )
        return result
    except Exception as e:
        logger.error(f"Wellness report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/health/{user_id}/nutrition")
async def track_nutrition_endpoint(user_id: str, meal_description: str):
    """
    Track meal with AI-powered nutrition estimation.

    Query params:
        - meal_description: Description of the meal
    """
    try:
        result = plugin_manager.call_function(
            "health_track_nutrition",
            user_id=user_id,
            meal_description=meal_description
        )
        return result
    except Exception as e:
        logger.error(f"Nutrition tracking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/workout-suggestion")
async def get_workout_suggestion(user_id: str):
    """Get personalized workout suggestion based on current state."""
    try:
        result = plugin_manager.call_function(
            "health_suggest_workout",
            user_id=user_id
        )
        return result
    except Exception as e:
        logger.error(f"Workout suggestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/anomalies")
async def detect_health_anomalies(user_id: str):
    """Detect anomalous health patterns (poor sleep, elevated HR, low activity)."""
    try:
        result = plugin_manager.call_function(
            "health_detect_anomalies",
            user_id=user_id
        )
        return result
    except Exception as e:
        logger.error(f"Anomaly detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/{user_id}/correlations")
async def get_health_memory_correlations(user_id: str, metric: str = "all", days: int = 14):
    """
    Correlate health metrics with memory/emotional states.

    Query params:
        - metric: Metric to correlate ('sleep', 'heart_rate', 'activity', 'all')
        - days: Days to analyze (default: 14)
    """
    try:
        result = plugin_manager.call_function(
            "health_correlate_with_memory",
            user_id=user_id,
            metric=metric,
            days=days
        )
        return result
    except Exception as e:
        logger.error(f"Health correlation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/health/{user_id}/disconnect")
async def disconnect_health_account(user_id: str, source: str = "google_fit"):
    """
    Disconnect health data source and optionally delete data.

    Query params:
        - source: Source to disconnect ('google_fit', etc.)
    """
    try:
        # Remove OAuth token from user metadata
        async with database.pg_pool.acquire() as conn:
            if source == "google_fit":
                await conn.execute(
                    """
                    UPDATE users
                    SET metadata = metadata - 'google_fit_token'
                    WHERE user_id = $1
                    """,
                    user_id
                )

        return {
            "success": True,
            "message": f"{source} account disconnected successfully",
            "note": "Health data has been preserved. Use DELETE /health/{user_id}/data to remove all data."
        }

    except Exception as e:
        logger.error(f"Health disconnect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/health/{user_id}/data")
async def delete_health_data(user_id: str, confirm: bool = False):
    """
    Delete ALL health data for user (GDPR compliance).

    Query params:
        - confirm: Must be true to proceed
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must set confirm=true to delete all health data"
        )

    try:
        async with database.pg_pool.acquire() as conn:
            # Delete from all health tables
            await conn.execute("DELETE FROM health_data WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM health_goals WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM workouts WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM nutrition_log WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM health_anomalies WHERE user_id = $1", user_id)

            # Remove OAuth tokens
            await conn.execute(
                """
                UPDATE users
                SET metadata = metadata - 'google_fit_token'
                WHERE user_id = $1
                """,
                user_id
            )

        return {
            "success": True,
            "message": "All health data and connections deleted permanently"
        }

    except Exception as e:
        logger.error(f"Health data deletion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket per comunicazione real-time con la PWA.

    [BUG#4 FIX] Aggiunto contesto data/ora (mancava completamente).
    [BUG#5 FIX] Aggiunto memory context con stesso formato dell'HTTP endpoint.
    [IMPROVE]   _build_system_context() condiviso con HTTP endpoint.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected: {websocket.client}")

    query_params = dict(websocket.query_params)
    user_id      = query_params.get("user_id", "websocket_user")
    session_id   = query_params.get("session_id")

    await websocket.send_json({
        "type":    "connection",
        "status":  "connected",
        "message": "Connesso a Jarvis"
    })

    try:
        while True:
            try:
                data         = await websocket.receive_json()
                message_text = data.get("message", "").strip()

                if not message_text:
                    continue

                logger.info(f"WS message from {user_id}: {message_text}")

                await websocket.send_json({"type": "typing", "status": True})

                # Salva messaggio utente
                await add_message(user_id, "user", message_text, session_id)

                # History
                history = await get_conversation_history(user_id, 3, session_id)

                # [BUG#4+5 FIX] System context completo (data/ora + memoria)
                system_context = await _build_system_context(user_id, message_text)
                history.insert(0, {"role": "system", "content": system_context})

                # Model selection — UNA sola volta
                use_smart        = _should_use_smart_model(history)
                functions_schema = plugin_manager.get_functions_schema() if use_smart else None

                # Chiamata LLM
                llm_response      = _call_llm(history, functions_schema, use_smart)
                assistant_message = llm_response.get("message", {}).get("content", "")

                # Function call
                function_call    = llm_response.get("function_call") or _parse_function_call(assistant_message)
                function_results = []

                if function_call:
                    assistant_message, function_results = await _execute_function_call(
                        function_call, user_id, session_id,
                        assistant_message, history, use_smart
                    )
                else:
                    await add_message(user_id, "assistant", assistant_message, session_id)

                if function_results:
                    await add_message(user_id, "assistant", assistant_message, session_id)

                # Memoria in background
                async def extract_memories_bg():
                    try:
                        if len(message_text) < 12:
                            return
                        updated_history = await get_conversation_history(user_id, 5, session_id)
                        saved = await process_conversation_for_memories(
                            user_id, updated_history,
                            gemini_client, OLLAMA_URL, OLLAMA_MODEL_SMART
                        )
                        if saved > 0:
                            logger.info(f"WS memory: {saved} facts saved for {user_id}")
                    except Exception as e:
                        logger.warning(f"WS memory extraction error: {e}")

                asyncio.create_task(extract_memories_bg())

                await websocket.send_json({
                    "type":           "response",
                    "message":        assistant_message,
                    "function_calls": function_results if function_results else None
                })

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected: {user_id}")
                break
            except Exception as e:
                logger.error(f"WebSocket message error: {e}")
                await websocket.send_json({"type": "error", "message": f"Errore: {str(e)}"})

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        logger.info(f"WebSocket closed: {user_id}")

# ─────────────────────────────────────────────────────────────────────────────
# VOICE WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket per voice loop browser-based.
    Gestisce streaming audio: Browser → STT → LLM → TTS → Browser
    """
    from voice_websocket import voice_handler

    query_params = dict(websocket.query_params)
    user_id = query_params.get("user_id", "voice_user")

    logger.info(f"🎙️ Voice WebSocket connection from: {user_id}")

    await voice_handler.handle_voice_loop(websocket, user_id)

# ─────────────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
