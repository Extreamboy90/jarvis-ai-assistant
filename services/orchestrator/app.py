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
from typing import Dict, List, Optional
import locale

import requests
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import (
    init_db, close_db,
    add_message, get_conversation_history,
    log_interaction, log_function_call,
    clear_conversation as db_clear_conversation,
    pg_pool
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

PLUGINS_TO_LOAD = ["system", "tuya", "calendar", "web_search"]
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
        final_response   = _call_llm(updated_history, use_smart=True)
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
    async with pg_pool.acquire() as conn:
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
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
