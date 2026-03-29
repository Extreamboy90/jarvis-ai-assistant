"""
Long-term memory system for Jarvis
Automatically extracts and retrieves important facts from conversations

Fixes applied:
- [BUG#1] Soglia minima similarità nel retrieval (0.35)
- [BUG#2] Contradiction detection via snippet match, non indici numerici
- [BUG#3] Filtraggio messaggi system/function nel contesto estrazione
- [BUG#4] SQL injection in cleanup_old_memories (parametro $3 corretto)
- [MARK-XXX] Pre-check YES/NO a 2 stadi prima dell'estrazione completa
- [MARK-XXX] Deduplica per snippet esatto prima della similarità vettoriale
- [IMPROVE] Logging strutturato con statistiche di retrieval
"""

import logging
import json
import re
from typing import List, Dict, Optional
import database

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAZIONE
# ─────────────────────────────────────────────────────────────────────────────

# Soglia minima di similarità coseno per il retrieval.
# Sotto questa soglia, la memoria viene scartata anche se ha importance alta.
RETRIEVAL_SIMILARITY_THRESHOLD = 0.35

# Soglia sopra cui due snippet sono considerati duplicati.
DEDUPLICATION_SIMILARITY_THRESHOLD = 0.95

# Numero di turni conversazione analizzati per estrazione fatti.
EXTRACTION_CONTEXT_TURNS = 5

# Lunghezza minima del messaggio utente per tentare l'estrazione (Mark XXX: len < 10 → skip).
MIN_MESSAGE_LENGTH_FOR_EXTRACTION = 12

# Ruoli da ESCLUDERE dal contesto di estrazione (fix Bug #3).
EXCLUDED_ROLES = {"system", "function", "tool"}

# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDING
# ─────────────────────────────────────────────────────────────────────────────

def get_embedding(text: str) -> Optional[List[float]]:
    """Genera embedding vettoriale tramite Ollama (all-minilm, 384 dim)."""
    try:
        import requests
        import os

        ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        response = requests.post(
            f"{ollama_url}/api/embeddings",
            json={"model": "all-minilm", "prompt": text},
            timeout=10
        )

        if response.status_code == 200:
            return response.json().get("embedding")

        logger.error(f"Ollama embedding failed: {response.status_code}")
        return None

    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return None


def _embedding_to_pg(embedding: List[float]) -> str:
    """Converte lista float in stringa formato pgvector."""
    return "[" + ",".join(map(str, embedding)) + "]"

# ─────────────────────────────────────────────────────────────────────────────
# PRE-CHECK (ispirato a Mark XXX: Stage 1 YES/NO, Stage 2 estrazione)
# ─────────────────────────────────────────────────────────────────────────────

def _should_extract_memories(messages: List[Dict]) -> bool:
    """
    Stage 1 (veloce, senza LLM): decide se vale la pena tentare l'estrazione.
    Evita chiamate API su messaggi banali — risparmio ~80% chiamate.
    Ispirato alla logica 2-stadi di Mark XXX.
    """
    # Raccogli solo messaggi utente recenti (esclude system/function)
    user_messages = [
        m["content"] for m in messages[-EXTRACTION_CONTEXT_TURNS:]
        if m.get("role") == "user"
    ]

    if not user_messages:
        return False

    # Messaggio troppo corto → skip
    last_user_msg = user_messages[-1].strip()
    if len(last_user_msg) < MIN_MESSAGE_LENGTH_FOR_EXTRACTION:
        return False

    # Keywords che indicano contenuto personale (Mark XXX pattern)
    personal_keywords = [
        "mi chiamo", "sono", "abito", "vivo", "lavoro", "faccio",
        "mi piace", "preferisco", "odio", "adoro", "voglio",
        "ho", "mio", "mia", "miei", "ricorda", "non dimenticare",
        "ho anni", "nato", "compleanno", "moglie", "marito", "figlio",
        "figlia", "fratello", "sorella", "madre", "padre",
        "my name", "i am", "i live", "i work", "i like", "i love",
    ]

    combined_text = " ".join(user_messages).lower()
    return any(kw in combined_text for kw in personal_keywords)


async def _llm_precheck(
    context: str,
    gemini_client=None,
    ollama_url: str = None,
    ollama_model: str = None
) -> bool:
    """
    Stage 2 (con LLM veloce): conferma YES/NO se ci sono fatti personali.
    Chiamato solo se Stage 1 ha già dato esito positivo.
    Usa il modello più piccolo disponibile (gemini flash / gemma3:1b).
    """
    prompt = (
        "Questa conversazione contiene fatti personali sull'utente "
        "(nome, città, lavoro, hobby, preferenze, relazioni, età, compleanno)? "
        "Rispondi SOLO con YES o NO.\n\n"
        f"Conversazione:\n{context[:400]}"
    )

    try:
        if gemini_client and gemini_client.check_availability():
            result = gemini_client.chat(
                messages=[{"role": "user", "content": prompt}],
                use_smart=False,
                temperature=0.1,
                max_tokens=5
            )
            answer = result.get("message", "").strip().upper()
            return "YES" in answer

        if ollama_url and ollama_model:
            import requests
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": ollama_model, "prompt": prompt, "stream": False},
                timeout=15
            )
            if response.status_code == 200:
                answer = response.json().get("response", "").strip().upper()
                return "YES" in answer

    except Exception as e:
        logger.warning(f"LLM precheck failed, proceeding with extraction: {e}")
        return True  # In caso di errore, meglio estrarre per sicurezza

    return False

# ─────────────────────────────────────────────────────────────────────────────
# ESTRAZIONE FATTI
# ─────────────────────────────────────────────────────────────────────────────

async def extract_facts_from_conversation(
    user_id: str,
    messages: List[Dict[str, str]],
    gemini_client=None,
    ollama_url: str = None,
    ollama_model: str = None
) -> List[Dict]:
    """
    Estrae fatti importanti dalla conversazione usando LLM.

    Fix Bug #3: esclude messaggi system/function dal contesto.
    Fix Mark XXX: pre-check a 2 stadi prima di chiamare il LLM.
    """
    try:
        # [BUG#3 FIX] Filtra solo messaggi user/assistant, escludi system e function results
        clean_messages = [
            m for m in messages[-EXTRACTION_CONTEXT_TURNS:]
            if m.get("role") not in EXCLUDED_ROLES
        ]

        if not clean_messages:
            return []

        context = "\n".join([
            f"{m['role'].upper()}: {m['content']}"
            for m in clean_messages
        ])

        # [MARK-XXX] Stage 1: pre-check keyword (senza LLM)
        if not _should_extract_memories(clean_messages):
            logger.debug("Memory pre-check Stage 1: SKIP (no personal keywords)")
            return []

        # [MARK-XXX] Stage 2: pre-check LLM veloce (YES/NO)
        has_personal_facts = await _llm_precheck(
            context, gemini_client, ollama_url, ollama_model
        )

        if not has_personal_facts:
            logger.debug("Memory pre-check Stage 2: SKIP (LLM says NO)")
            return []

        logger.info("Memory pre-check: YES — proceeding with full extraction")

        # Stage 3: estrazione completa
        extraction_prompt = f"""Analizza questa conversazione ed estrai SOLO i fatti personali importanti da ricordare.

Conversazione:
{context}

Estrai fatti come:
- Nome dell'utente
- Preferenze (cibo, hobby, interessi, musica)
- Informazioni personali (lavoro, famiglia, città, età)
- Richieste esplicite da ricordare

NON estrarre:
- Risultati di ricerche web
- Dati meteo o informazioni temporanee
- Date/ore di sistema
- Risposte generiche dell'assistente

Rispondi SOLO con un JSON array. Ogni elemento deve avere:
- "snippet": fatto breve e chiaro (max 100 caratteri)
- "category": nome | preferenza | fatto | richiesta
- "importance": da 1 a 10

Se non ci sono fatti personali, rispondi con [].

Esempio output:
[
  {{"snippet": "L'utente si chiama Alessandro", "category": "nome", "importance": 10}},
  {{"snippet": "Lavora nel settore energia in Sardegna", "category": "fatto", "importance": 8}},
  {{"snippet": "Preferisce risposte concise", "category": "preferenza", "importance": 7}}
]

JSON:"""

        response_text = ""

        # Prova Gemini (modello fast per estrazione)
        if gemini_client and gemini_client.check_availability():
            try:
                result = gemini_client.chat(
                    messages=[{"role": "user", "content": extraction_prompt}],
                    use_smart=False,
                    temperature=0.3,
                    max_tokens=1024
                )
                response_text = result.get("message", "")
                logger.info("Fact extraction via Gemini")
            except Exception as e:
                logger.warning(f"Gemini extraction failed, fallback to Ollama: {e}")

        # Fallback Ollama
        if not response_text and ollama_url and ollama_model:
            import requests
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": ollama_model, "prompt": extraction_prompt, "stream": False},
                timeout=30
            )
            if response.status_code == 200:
                response_text = response.json().get("response", "")
                logger.info("Fact extraction via Ollama")

        if not response_text:
            logger.error("No LLM available for fact extraction")
            return []

        facts = _parse_facts_from_response(response_text)
        logger.info(f"Extracted {len(facts)} facts from conversation")
        return facts

    except Exception as e:
        logger.error(f"Error extracting facts: {e}")
        return []


def _parse_facts_from_response(response_text: str) -> List[Dict]:
    """Parsa il JSON dei fatti dalla risposta LLM con fallback robusto."""
    try:
        # Rimuovi markdown code blocks
        response_text = re.sub(r"```(?:json)?", "", response_text).strip().rstrip("`").strip()

        if "[" not in response_text or "]" not in response_text:
            return []

        start = response_text.find("[")
        end = response_text.rfind("]") + 1
        facts = json.loads(response_text[start:end])

        validated = []
        for fact in facts:
            if not isinstance(fact, dict) or "snippet" not in fact:
                continue
            snippet = str(fact["snippet"]).strip()
            if not snippet or len(snippet) < 5:
                continue
            validated.append({
                "snippet": snippet[:200],  # cap lunghezza
                "category": fact.get("category", "fatto"),
                "importance": min(max(int(fact.get("importance", 5)), 1), 10)
            })

        return validated

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse facts JSON: {e}")
    except Exception as e:
        logger.error(f"Error parsing facts: {e}")

    return []

# ─────────────────────────────────────────────────────────────────────────────
# CONTRADICTION DETECTION (fix Bug #2: snippet match invece di indici)
# ─────────────────────────────────────────────────────────────────────────────

async def _find_contradictory_memories(
    user_id: str,
    new_snippet: str,
    category: str,
    gemini_client=None,
    ollama_url: str = None,
    ollama_model: str = None
) -> List[Dict]:
    """
    Trova memorie che contraddicono il nuovo snippet.

    Fix Bug #2: il LLM restituisce snippet esatti (non indici numerici)
    per evitare errori di off-by-one e allucinazioni sugli indici.
    """
    try:
        async with database.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, snippet, importance
                FROM memory_snippets
                WHERE user_id = $1 AND category = $2
                  AND (metadata->>'obsolete')::boolean IS NOT TRUE
                """,
                user_id, category
            )

            if not rows:
                return []

            existing = [
                {"id": row["id"], "snippet": row["snippet"], "importance": row["importance"]}
                for row in rows
            ]

            # [BUG#2 FIX] Chiedi al LLM di restituire snippet ESATTI, non indici numerici
            prompt = (
                f'Nuovo fatto: "{new_snippet}"\n\n'
                f"Fatti esistenti:\n"
                + "\n".join(f'- "{m["snippet"]}"' for m in existing)
                + "\n\n"
                "Elenca SOLO i fatti che CONTRADDICONO o rendono obsoleto il nuovo fatto.\n"
                "Copia il testo ESATTO dalla lista sopra.\n"
                "Se il nuovo fatto è solo un'aggiunta o specificazione, NON includere nulla.\n\n"
                "Esempi:\n"
                '- Nuovo: "vive a Milano" vs Esistente: "vive a Roma" → CONTRADDIZIONE\n'
                '- Nuovo: "odia il caffè" vs Esistente: "ama il caffè" → CONTRADDIZIONE\n'
                '- Nuovo: "ama la pizza margherita" vs Esistente: "ama la pizza" → OK, non è contraddizione\n\n'
                "Rispondi SOLO con un JSON array di stringhe (testo esatto dei fatti da marcare obsoleti).\n"
                "Se nessuna contraddizione, rispondi con [].\n\n"
                "JSON:"
            )

            response_text = ""

            if gemini_client and gemini_client.check_availability():
                try:
                    result = gemini_client.chat(
                        messages=[{"role": "user", "content": prompt}],
                        use_smart=False,
                        temperature=0.1,
                        max_tokens=512
                    )
                    response_text = result.get("message", "")
                except Exception as e:
                    logger.warning(f"Gemini contradiction check failed: {e}")

            if not response_text and ollama_url and ollama_model:
                import requests
                response = requests.post(
                    f"{ollama_url}/api/generate",
                    json={"model": ollama_model, "prompt": prompt, "stream": False},
                    timeout=20
                )
                if response.status_code == 200:
                    result = response.json()
                    response_text = result.get("response", "")

            if not response_text or "[" not in response_text:
                return []

            # [BUG#2 FIX] Match per testo esatto, non per indice
            response_text = re.sub(r"```(?:json)?", "", response_text).strip().rstrip("`")
            start = response_text.find("[")
            end = response_text.rfind("]") + 1
            contradictory_snippets = json.loads(response_text[start:end])

            if not isinstance(contradictory_snippets, list):
                return []

            # Filtra per corrispondenza esatta o substring del testo
            contradictory = []
            for mem in existing:
                for cs in contradictory_snippets:
                    if isinstance(cs, str) and (
                        cs.strip() == mem["snippet"].strip() or
                        cs.strip() in mem["snippet"] or
                        mem["snippet"] in cs.strip()
                    ):
                        contradictory.append(mem)
                        break

            if contradictory:
                logger.info(f"Found {len(contradictory)} contradictory memories")

            return contradictory

    except Exception as e:
        logger.warning(f"Error finding contradictions: {e}")
        return []

# ─────────────────────────────────────────────────────────────────────────────
# SALVATAGGIO
# ─────────────────────────────────────────────────────────────────────────────

async def save_memory_snippet(
    user_id: str,
    snippet: str,
    category: str = "fatto",
    importance: int = 5,
    metadata: Optional[Dict] = None,
    gemini_client=None,
    ollama_url: Optional[str] = None,
    ollama_model: Optional[str] = None
) -> bool:
    """
    Salva uno snippet in memoria con embedding, deduplica e contradiction detection.

    Ordine operazioni:
    1. Deduplica esatta per snippet text (veloce, senza vettori)
    2. Deduplica semantica via pgvector (similarity > 0.95)
    3. Contradiction detection via LLM
    4. Insert
    """
    try:
        embedding = get_embedding(snippet)
        if not embedding:
            logger.error(f"Failed to generate embedding for: {snippet[:50]}")
            return False

        embedding_str = _embedding_to_pg(embedding)

        async with database.pg_pool.acquire() as conn:

            # ── Step 1: Deduplica esatta su testo (Mark XXX pattern) ──────────
            existing_exact = await conn.fetchrow(
                """
                SELECT id, importance FROM memory_snippets
                WHERE user_id = $1 AND snippet = $2
                """,
                user_id, snippet
            )
            if existing_exact:
                if importance > existing_exact["importance"]:
                    await conn.execute(
                        """
                        UPDATE memory_snippets
                        SET importance = $1,
                            last_accessed = CURRENT_TIMESTAMP,
                            embedding = $2::vector
                        WHERE id = $3
                        """,
                        importance, embedding_str, existing_exact["id"]
                    )
                    logger.info(f"Updated exact duplicate with higher importance: {snippet[:50]}")
                else:
                    logger.debug(f"Exact duplicate skipped (same or lower importance): {snippet[:50]}")
                return True

            # ── Step 2: Deduplica semantica vettoriale ────────────────────────
            similar_memories = await conn.fetch(
                """
                SELECT id, snippet, category, importance,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM memory_snippets
                WHERE user_id = $2
                ORDER BY similarity DESC
                LIMIT 5
                """,
                embedding_str, user_id
            )

            for mem in similar_memories:
                if mem["similarity"] > DEDUPLICATION_SIMILARITY_THRESHOLD and mem["category"] == category:
                    if importance > mem["importance"]:
                        await conn.execute(
                            """
                            UPDATE memory_snippets
                            SET snippet = $1, importance = $2,
                                last_accessed = CURRENT_TIMESTAMP,
                                embedding = $3::vector
                            WHERE id = $4
                            """,
                            snippet, importance, embedding_str, mem["id"]
                        )
                        logger.info(f"Updated near-duplicate (sim={mem['similarity']:.2f}): {snippet[:50]}")
                    else:
                        logger.debug(f"Near-duplicate skipped: {snippet[:50]}")
                    return True

            # ── Step 3: Contradiction detection ──────────────────────────────
            if gemini_client or (ollama_url and ollama_model):
                contradictory = await _find_contradictory_memories(
                    user_id, snippet, category, gemini_client, ollama_url, ollama_model
                )
                for mem in contradictory:
                    await conn.execute(
                        """
                        UPDATE memory_snippets
                        SET importance = GREATEST(1, importance - 3),
                            metadata = jsonb_set(
                                COALESCE(metadata, '{}'::jsonb),
                                '{obsolete}',
                                'true'::jsonb
                            )
                        WHERE id = $1
                        """,
                        mem["id"]
                    )
                    logger.info(f"Marked obsolete: {mem['snippet'][:50]}")

            # ── Step 4: Insert ────────────────────────────────────────────────
            await conn.execute(
                """
                INSERT INTO memory_snippets
                    (user_id, snippet, category, importance, metadata,
                     embedding, created_at, last_accessed, access_count)
                VALUES ($1, $2, $3, $4, $5, $6::vector,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
                """,
                user_id, snippet, category, importance,
                json.dumps(metadata or {}), embedding_str
            )
            logger.info(f"Saved new memory (importance={importance}): {snippet[:60]}")
            return True

    except Exception as e:
        logger.error(f"Error saving memory snippet: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# RETRIEVAL (fix Bug #1: soglia similarità minima)
# ─────────────────────────────────────────────────────────────────────────────

async def retrieve_relevant_memories(
    user_id: str,
    query: str,
    limit: int = 5,
    min_importance: int = 3,
    min_similarity: float = RETRIEVAL_SIMILARITY_THRESHOLD,
    exclude_obsolete: bool = True
) -> List[Dict]:
    """
    Recupera memorie rilevanti via semantic search.

    Fix Bug #1: aggiunge soglia minima di similarità coseno.
    Senza questa soglia, memorie completamente irrilevanti venivano
    iniettate nel prompt inquinando il contesto LLM.
    """
    try:
        query_embedding = get_embedding(query)
        if not query_embedding:
            logger.warning("Failed to generate query embedding for retrieval")
            return []

        embedding_str = _embedding_to_pg(query_embedding)
        obsolete_filter = (
            "AND (metadata->>'obsolete')::boolean IS NOT TRUE"
            if exclude_obsolete else ""
        )

        # [BUG#1 FIX] La soglia MIN_SIMILARITY filtra risultati irrilevanti
        query_sql = f"""
            SELECT
                snippet,
                category,
                importance,
                created_at,
                access_count,
                1 - (embedding <=> $1::vector) AS similarity
            FROM memory_snippets
            WHERE user_id = $2
              AND importance >= $3
              AND 1 - (embedding <=> $1::vector) >= $4
              {obsolete_filter}
            ORDER BY
                (1 - (embedding <=> $1::vector)) * 0.6 + (importance::float / 10.0) * 0.4 DESC
            LIMIT $5
        """
        # Ranking combinato: 60% similarità semantica + 40% importanza

        async with database.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                query_sql,
                embedding_str, user_id, min_importance, min_similarity, limit
            )

            memories = []
            for row in rows:
                await conn.execute(
                    """
                    UPDATE memory_snippets
                    SET last_accessed = CURRENT_TIMESTAMP,
                        access_count = access_count + 1
                    WHERE user_id = $1 AND snippet = $2
                    """,
                    user_id, row["snippet"]
                )
                memories.append({
                    "snippet": row["snippet"],
                    "category": row["category"],
                    "importance": row["importance"],
                    "similarity": round(float(row["similarity"]), 3),
                    "access_count": row["access_count"]
                })

            if memories:
                logger.info(
                    f"Retrieved {len(memories)} memories "
                    f"(similarity range: "
                    f"{min(m['similarity'] for m in memories):.2f}–"
                    f"{max(m['similarity'] for m in memories):.2f})"
                )
            else:
                logger.debug(
                    f"No memories above threshold "
                    f"(min_importance={min_importance}, min_similarity={min_similarity})"
                )

            return memories

    except Exception as e:
        logger.error(f"Error retrieving memories: {e}")
        return []

# ─────────────────────────────────────────────────────────────────────────────
# PROCESSO COMPLETO
# ─────────────────────────────────────────────────────────────────────────────

async def process_conversation_for_memories(
    user_id: str,
    messages: List[Dict[str, str]],
    gemini_client=None,
    ollama_url: str = None,
    ollama_model: str = None
) -> int:
    """
    Processa una conversazione ed estrae/salva i ricordi importanti.
    Ritorna il numero di ricordi salvati.
    """
    facts = await extract_facts_from_conversation(
        user_id, messages, gemini_client, ollama_url, ollama_model
    )

    if not facts:
        return 0

    saved_count = 0
    for fact in facts:
        success = await save_memory_snippet(
            user_id=user_id,
            snippet=fact["snippet"],
            category=fact["category"],
            importance=fact["importance"],
            gemini_client=gemini_client,
            ollama_url=ollama_url,
            ollama_model=ollama_model
        )
        if success:
            saved_count += 1

    logger.info(f"Memory process complete: {saved_count}/{len(facts)} facts saved for {user_id}")
    return saved_count

# ─────────────────────────────────────────────────────────────────────────────
# UTILITÀ
# ─────────────────────────────────────────────────────────────────────────────

def format_memories_for_prompt(memories: List[Dict]) -> str:
    """
    Formatta le memorie per l'injection nel system prompt.
    Formato strutturato a lista invece di stringa piatta (fix app.py Bug).
    """
    if not memories:
        return ""

    lines = "\n".join(f"- {m['snippet']}" for m in memories)
    return f"[MEMORIA UTENTE]\n{lines}"


async def get_user_memories_summary(user_id: str, limit: int = 10) -> str:
    """Ritorna un sommario testuale delle memorie più importanti."""
    try:
        async with database.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT snippet, category, importance
                FROM memory_snippets
                WHERE user_id = $1
                  AND (metadata->>'obsolete')::boolean IS NOT TRUE
                ORDER BY importance DESC, created_at DESC
                LIMIT $2
                """,
                user_id, limit
            )

            if not rows:
                return ""

            by_category: Dict[str, List[str]] = {}
            for row in rows:
                cat = row["category"]
                by_category.setdefault(cat, []).append(row["snippet"])

            parts = [
                f"{cat.capitalize()}: {', '.join(snippets)}"
                for cat, snippets in by_category.items()
            ]
            return " | ".join(parts)

    except Exception as e:
        logger.error(f"Error getting memory summary: {e}")
        return ""


async def cleanup_old_memories(
    user_id: str,
    days_threshold: int = 90,
    min_importance: int = 3
):
    """
    Rimuove memorie vecchie, inutilizzate e a bassa importanza.

    Fix Bug #4: parametro days_threshold ora correttamente parametrizzato
    in asyncpg ($3 * INTERVAL '1 day' invece di interpolazione stringa %s).
    """
    try:
        async with database.pg_pool.acquire() as conn:
            # Elimina memorie vecchie, poco importanti e poco accedute
            result = await conn.execute(
                """
                DELETE FROM memory_snippets
                WHERE user_id = $1
                  AND importance < $2
                  AND access_count < 2
                  AND last_accessed < NOW() - ($3 * INTERVAL '1 day')
                  AND (metadata->>'obsolete')::boolean IS NOT TRUE
                """,
                user_id, min_importance, days_threshold  # [BUG#4 FIX]
            )
            logger.info(f"Cleanup removed stale memories for {user_id}: {result}")

            # Elimina memorie obsolete non accedute da 30 giorni
            await conn.execute(
                """
                DELETE FROM memory_snippets
                WHERE user_id = $1
                  AND (metadata->>'obsolete')::boolean = true
                  AND last_accessed < NOW() - INTERVAL '30 days'
                """,
                user_id
            )

        return True

    except Exception as e:
        logger.error(f"Error cleaning up memories: {e}")
        return False
