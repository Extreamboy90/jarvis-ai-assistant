# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Jarvis AI Assistant is an offline voice assistant (similar to Iron Man's Jarvis) with:
- Italian speech-to-text (Faster Whisper)
- Italian text-to-speech (Piper TTS)
- LLM-based conversation (Ollama with dual-model architecture)
- Long-term memory system with semantic search (PostgreSQL + pgvector)
- Telegram bot interface
- Progressive Web App (PWA) for multi-device access
- WebSocket support for real-time communication
- Extensible plugin system for function calling
- Smart home integration (Tuya devices)
- Google Calendar integration

## Architecture

### Dual-Model LLM Strategy

The system uses **two models** to balance speed and accuracy:

- **Fast Model** (`gemma3:1b`): 1-2 second responses for simple conversation
- **Smart Model** (`llama3.1:8b`): 5-10 second responses for complex tasks requiring function calls

Model selection is automatic based on keyword detection in `app.py:should_use_smart_model()`. Action keywords (accendi, spegni, che ore, info sistema) and complex keywords (spiega, analizza, come mi chiamo) trigger the smart model.

### Memory System Architecture

**Critical concept**: The LLM does NOT access the database directly. The system flow is:

1. User message → Database stores it
2. System retrieves conversation history + relevant long-term memories from database
3. System sends context to LLM (LLM only sees text, transparent to database)
4. LLM responds
5. System extracts important facts in background (non-blocking)
6. System saves facts to database with embeddings for future semantic search

**Memory lifecycle**:
- Extraction: LLM analyzes conversation and returns JSON array of facts
- Storage: Facts saved with Ollama embeddings (`all-minilm` model)
- Retrieval: Semantic search using pgvector cosine similarity
- Contradiction detection: New facts compared to existing using LLM reasoning
- Obsolescence: Contradictory memories marked with `metadata.obsolete=true` and importance lowered

**Performance optimization**: Memory extraction runs in `asyncio.create_task()` to avoid blocking responses (critical - this reduced response time from 15s to 1s).

### Service Communication

```
Telegram Bot (telegram_bot.py)
    ↓ HTTP requests (120s timeout)
Orchestrator (app.py:8000) ←─── PWA (port 3001)
    ↓ calls plugins          WebSocket /ws
Plugin Manager (plugins/__init__.py)
    ↓ loads/executes
Plugins (plugins/system.py, plugins/tuya.py, plugins/calendar.py)

Orchestrator also calls:
- STT Service (8001) - Faster Whisper transcription
- TTS Service (8002) - Piper voice synthesis
- TTS-MMS (8003) - Alternative TTS (Meta MMS)
- Ollama (11434) - LLM inference + embeddings
- PostgreSQL (5432) - Conversation history + memory snippets with vector search
- Redis (6379) - Caching layer
```

## Common Commands

### Docker Operations

```bash
# Start all services
docker-compose up -d --build

# Restart specific service after code changes
docker-compose up -d --build orchestrator
docker-compose up -d --build telegram-bot

# View logs
docker-compose logs -f orchestrator
docker-compose logs -f telegram-bot

# Check service status
docker-compose ps

# Copy file to container and restart (for hot fixes)
docker cp services/orchestrator/app.py jarvis-orchestrator:/app/app.py
docker restart jarvis-orchestrator
```

### Ollama Model Management

```bash
# List available models
docker exec ollama ollama list

# Pull new model
docker exec ollama ollama pull gemma3:1b
docker exec ollama ollama pull llama3.1:8b

# Download embedding model (required for memory system)
docker exec ollama ollama pull all-minilm
```

### Testing Services

```bash
# Health checks
curl http://localhost:8000/health  # Orchestrator
curl http://localhost:8001/health  # STT
curl http://localhost:8002/health  # TTS

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"ciao","user_id":"test"}'

# Test STT
curl -X POST http://localhost:8001/transcribe \
  -F "audio=@test.wav"

# Test TTS
curl -X POST http://localhost:8002/speak \
  -H "Content-Type: application/json" \
  -d '{"text":"Ciao sono Jarvis"}' \
  --output test.wav

# List available functions
curl http://localhost:8000/functions

# Get user memories
curl http://localhost:8000/memories/test_user?limit=20
```

### Database Access

```bash
# Connect to PostgreSQL
docker exec -it jarvis-postgres psql -U jarvis -d jarvis

# Useful queries
SELECT * FROM users;
SELECT * FROM conversations WHERE user_id = 'your_user_id';
SELECT * FROM messages WHERE conversation_id = X ORDER BY created_at DESC;
SELECT * FROM memory_snippets WHERE user_id = 'your_user_id' ORDER BY importance DESC;
SELECT snippet, category, importance FROM memory_snippets WHERE (metadata->>'obsolete')::boolean IS NOT TRUE;
```

### PWA Development Server

```bash
# Start PWA server (from pwa/ directory)
cd pwa
python3 serve.py  # Default port 3001

# Access locally
http://localhost:3001

# Access from mobile device (same network)
http://<your-ip>:3001

# Debug page for testing connectivity
http://localhost:3001/debug.html
```

## Key Implementation Details

### Plugin System

Plugins use a decorator pattern (`@function`) to register callable functions:

```python
# In plugins/myplugin.py
from plugins import function

@function(
    name="my_action",
    description="What this function does",
    parameters={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "Parameter description"}
        },
        "required": ["param"]
    }
)
def my_action(param: str):
    return {"result": "success"}
```

Register plugin in `app.py`:
```python
PLUGINS_TO_LOAD = ["system", "tuya", "calendar", "myplugin"]
```

Function naming: Plugin functions are automatically prefixed with `{plugin_name}_` by PluginManager (e.g., `system_get_current_time`).

**Available plugins:**
- `system.py` - System info, current time, command execution
- `tuya.py` - Smart home device control
- `calendar.py` - Google Calendar integration (requires OAuth setup)

### Function Call Flow

1. User message → LLM receives conversation history + function schema
2. LLM responds with JSON: `{"function": "system_get_current_time", "parameters": {}}`
3. `parse_function_call()` extracts JSON from LLM response
4. `plugin_manager.call_function()` executes the function
5. Function result added to conversation as system message
6. LLM called again to formulate natural language response
7. Final response sent to user

### Memory Retrieval Filter

**Critical bug fix**: Always exclude obsolete memories when retrieving context:

```python
# In memory.py:retrieve_relevant_memories()
exclude_obsolete = True  # DEFAULT - prevents contradictory info reaching LLM
obsolete_filter = "AND (metadata->>'obsolete')::boolean IS NOT TRUE" if exclude_obsolete else ""
```

Without this filter, LLM receives both current and obsolete facts, causing incorrect responses.

### WebSocket Communication

The orchestrator supports WebSocket connections for real-time bidirectional communication with PWA clients:

```python
# WebSocket endpoint in app.py
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Handle messages with typing indicators
```

**Connection URL**: `ws://localhost:8000/ws?user_id=<id>&session_id=<session>`

**Message format**:
- Client → Server: `{"message": "text", "max_history": 3}`
- Server → Client: `{"type": "message", "content": "response"}` or `{"type": "typing", "is_typing": true}`

**CORS**: Enabled for all origins in development (configure for production)

### Progressive Web App (PWA)

Located in `pwa/` directory with vanilla HTML/CSS/JS (no build step required):

**Structure:**
- `index.html` - Main interface
- `css/main.css` - Styles (dark theme, iOS-optimized)
- `js/config.js` - Configuration
- `js/api.js` - WebSocket + HTTP API client
- `js/voice.js` - Web Speech API (STT/TTS)
- `js/ui.js` - UI management
- `js/app.js` - Initialization
- `sw.js` - Service Worker for offline support
- `manifest.json` - PWA manifest for installability
- `serve.py` - Development server (port 3001)
- `debug.html` - Connectivity testing page

**Features:**
- Installable on iOS, Android, Windows, Mac, Linux
- WebSocket with automatic reconnection
- Voice input/output using browser APIs
- Offline support via Service Worker
- Mobile-first responsive design
- iOS Safari viewport fixes (`-webkit-fill-available`)

**Installation:**
- iOS: Safari → Share → Add to Home Screen
- Android: Chrome → Menu → Add to Home Screen
- Desktop: Chrome/Edge → Install icon in address bar

### Performance Considerations

- Conversation history limited to `max_history=3` (reduced from 5 for speed)
- Memory extraction runs in background task (non-blocking)
- Smart model only invoked when needed (keyword detection)
- Telegram bot timeout: 120s (handles slow smart model responses)
- Database operations are fast (<100ms total)
- Main bottleneck: LLM inference time (1-30s depending on model and context)
- ROCm GPU acceleration supported (AMD GPUs, tested with Radeon 680M)

### Database Schema

Key tables:
- `users`: User profiles and metadata
- `conversations`: Conversation sessions (auto-created, 24h window)
- `messages`: Chat messages with role (user/assistant/system)
- `function_calls`: Log of all function executions with timing
- `memory_snippets`: Long-term facts with embeddings (vector(384))
- `interactions`: Audit log of all user actions

All tables use pgvector HNSW indexes for fast semantic search on embedding columns.

### Environment Variables

Key variables in docker-compose.yml:

```bash
OLLAMA_MODEL_FAST=gemma3:1b      # Fast conversational model
OLLAMA_MODEL_SMART=llama3.1:8b   # Smart model for function calling
TELEGRAM_BOT_TOKEN=...           # From .env file
POSTGRES_PASSWORD=jarvis_password
TZ=Europe/Rome                   # Timezone for date/time functions
```

## Common Issues

### Slow Responses (>15 seconds)

**First check**: Is memory extraction blocking?
- Memory extraction should be `asyncio.create_task()` not `await` in `app.py:chat()`
- Check logs for timing: `⏱️ LLM call`, `⏱️ Retrieve memories`, etc.

**Second check**: Which model is being used?
- Fast model (gemma3:1b): 1-2s
- Smart model (llama3.1:8b): 5-10s (or 30s+ with long history)
- Check logs: `Using model: llama3.1:8b (smart=True)`

### Wrong/Contradictory Responses

**Root cause**: System sent obsolete memories to LLM
**Fix**: Verify `exclude_obsolete=True` in `memory.py:retrieve_relevant_memories()`
**Verify**: Check database - obsolete memories should have `metadata->>'obsolete' = 'true'` and lower importance

### Telegram Bot Timeout

Bot says wrong answer after delay → timeout too short
- Telegram bot timeout in `telegram_bot.py`: `timeout=120`
- Orchestrator might take 30s+ with llama3.1:8b and long history
- Increase timeout or reduce `max_history` parameter

### Plugin Not Loading

Check orchestrator logs: `docker-compose logs orchestrator | grep Plugin`
- Verify plugin in `PLUGINS_TO_LOAD` list
- Check decorator syntax (`@function(...)`)
- Ensure plugin file in `services/orchestrator/plugins/`
- Rebuild: `docker-compose up -d --build orchestrator`

### Ollama Model Not Found

```bash
# Verify model exists
docker exec ollama ollama list

# Pull if missing
docker exec ollama ollama pull llama3.1:8b
docker exec ollama ollama pull all-minilm  # For embeddings
```

### Memory System Not Working

**Check embedding model**: `docker exec ollama ollama pull all-minilm`
**Check pgvector**: `docker exec -it jarvis-postgres psql -U jarvis -d jarvis -c "SELECT COUNT(*) FROM memory_snippets;"`
**Check logs**: `docker-compose logs orchestrator | grep -i memory`

### PWA Connection Issues

**Symptoms**: "Server unreachable" or no input field visible

**Fixes**:
1. Verify backend is running: `curl http://localhost:8000/health`
2. Check CORS is enabled in `app.py` (CORSMiddleware)
3. Use debug page: `http://localhost:3001/debug.html`
4. On iOS: Hard reload (pull down to refresh)
5. Check browser console (F12) for errors
6. For missing input on iOS: CSS viewport issue - ensure `-webkit-fill-available` is set

**Port conflicts**: If port 3001 is busy, edit `pwa/serve.py` and change `PORT = 3001` to another port

### Google Calendar Setup

The calendar plugin requires OAuth credentials:

1. Create Google Cloud project at https://console.cloud.google.com
2. Enable Google Calendar API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download credentials as `credentials.json`
5. Place in `services/orchestrator/`
6. First run will open browser for OAuth consent
7. Token saved as `token.pickle` for future use

## Code Modification Workflow

### Backend Changes

1. Edit files in `services/{service}/`
2. If editing orchestrator Python files:
   - Hot fix: `docker cp services/orchestrator/file.py jarvis-orchestrator:/app/file.py && docker restart jarvis-orchestrator`
   - Proper: `docker-compose up -d --build orchestrator`
3. If editing telegram bot: `docker-compose up -d --build telegram-bot`
4. Test with curl or Telegram
5. Check logs: `docker-compose logs -f {service}`

### PWA Changes

1. Edit files in `pwa/` directory (HTML/CSS/JS)
2. Hard reload browser (Ctrl+Shift+R or Cmd+Shift+R)
3. Service Worker changes: Unregister SW in DevTools → Application → Service Workers
4. No rebuild needed - static files served directly by `serve.py`
5. For production: Update `CACHE_NAME` in `sw.js` to force cache refresh

## Testing

No automated test suite currently. Manual testing via:
- Telegram bot interaction
- Direct API calls with curl
- Manual script: `test_memory_manual.py` (if present)
- Check function_calls table for execution logs
