"""
Mission Control - Dashboard Contestuale Proattiva
Genera briefing personalizzati combinando calendario, meteo, smart home, notizie e routine apprese
"""

from plugins import function
from typing import Dict, List, Optional
import os
import logging
from datetime import datetime, timedelta
import asyncio
import json

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CACHE LAYER - evita troppe chiamate API
# ─────────────────────────────────────────────────────────────────────────────

_cache = {}
CACHE_TTL = {
    "weather": 3600,      # 1 ora
    "news": 1800,         # 30 minuti
    "commute": 900,       # 15 minuti
    "routine": 86400,     # 24 ore
}

def _get_cached(key: str) -> Optional[Dict]:
    """Recupera valore dalla cache se non scaduto"""
    if key in _cache:
        data, timestamp = _cache[key]
        ttl = CACHE_TTL.get(key.split(":")[0], 300)
        if (datetime.now().timestamp() - timestamp) < ttl:
            return data
    return None

def _set_cache(key: str, value: Dict):
    """Salva valore in cache con timestamp"""
    _cache[key] = (value, datetime.now().timestamp())

# ─────────────────────────────────────────────────────────────────────────────
# ROUTINE ANALYSIS - impara pattern dalle interazioni
# ─────────────────────────────────────────────────────────────────────────────

async def _analyze_routine_patterns(user_id: str) -> Dict:
    """
    Analizza i pattern comportamentali dalle memorie e interactions.
    Ritorna insights su:
    - Orari tipici di attività
    - Giorni della settimana più attivi
    - Pattern di richieste comuni
    - Preferenze apprese
    """
    try:
        import database

        async with database.pg_pool.acquire() as conn:
            # Analizza pattern temporali dalle interactions
            interactions = await conn.fetch("""
                SELECT
                    EXTRACT(HOUR FROM created_at) as hour,
                    EXTRACT(DOW FROM created_at) as dow,
                    action
                FROM interactions
                WHERE user_id = $1
                  AND created_at > NOW() - INTERVAL '30 days'
                ORDER BY created_at DESC
                LIMIT 200
            """, user_id)

            # Analizza preferenze dalle memorie
            preferences = await conn.fetch("""
                SELECT snippet, category, importance
                FROM memory_snippets
                WHERE user_id = $1
                  AND category IN ('preferenza', 'fatto', 'nome')
                  AND (metadata->>'obsolete')::boolean IS NOT TRUE
                ORDER BY importance DESC, access_count DESC
                LIMIT 15
            """, user_id)

            # Calcola statistiche
            hour_counts = {}
            dow_counts = {}
            actions = []

            for row in interactions:
                h = int(row['hour'])
                d = int(row['dow'])
                hour_counts[h] = hour_counts.get(h, 0) + 1
                dow_counts[d] = dow_counts.get(d, 0) + 1
                actions.append(row['action'])

            # Identifica picchi di attività
            peak_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            most_active_day = max(dow_counts.items(), key=lambda x: x[1])[0] if dow_counts else None

            # Giorno della settimana in italiano
            dow_names = ["Domenica", "Lunedi", "Martedi", "Mercoledi", "Giovedi", "Venerdi", "Sabato"]

            # Compila insights
            insights = {
                "peak_hours": [h for h, _ in peak_hours],
                "most_active_day": dow_names[most_active_day] if most_active_day is not None else "N/A",
                "total_interactions_30d": len(interactions),
                "common_actions": list(set(actions))[:5],
                "preferences": [
                    {"text": p['snippet'], "importance": p['importance']}
                    for p in preferences
                ]
            }

            logger.info(f"Routine patterns analyzed for {user_id}: {len(interactions)} interactions")
            return insights

    except Exception as e:
        logger.error(f"Error analyzing routine patterns: {e}")
        return {
            "peak_hours": [],
            "most_active_day": "N/A",
            "total_interactions_30d": 0,
            "common_actions": [],
            "preferences": []
        }

# ─────────────────────────────────────────────────────────────────────────────
# WEATHER - usa OpenWeatherMap API (gratuita)
# ─────────────────────────────────────────────────────────────────────────────

def _get_weather_internal(location: str) -> Dict:
    """
    Recupera previsioni meteo da OpenWeatherMap.
    Fallback: ritorna dati mock se API non disponibile.
    """
    cache_key = f"weather:{location}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        api_key = os.getenv("OPENWEATHER_API_KEY")
        if not api_key:
            logger.warning("OPENWEATHER_API_KEY not set, using fallback data")
            return _weather_fallback(location)

        import requests
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": location,
            "appid": api_key,
            "units": "metric",
            "lang": "it"
        }

        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        result = {
            "success": True,
            "location": data.get("name", location),
            "temperature": round(data["main"]["temp"]),
            "feels_like": round(data["main"]["feels_like"]),
            "description": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "wind_speed": round(data["wind"]["speed"] * 3.6),  # m/s -> km/h
            "icon": data["weather"][0]["icon"]
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return _weather_fallback(location)

def _weather_fallback(location: str) -> Dict:
    """Ritorna dati meteo di fallback quando API non disponibile"""
    return {
        "success": False,
        "location": location,
        "temperature": 20,
        "feels_like": 20,
        "description": "dati non disponibili",
        "humidity": 60,
        "wind_speed": 10,
        "icon": "01d",
        "note": "API meteo non configurata - dati di esempio"
    }

# ─────────────────────────────────────────────────────────────────────────────
# NEWS - usa NewsAPI (gratuita)
# ─────────────────────────────────────────────────────────────────────────────

def _get_news_internal(interests: List[str], location: str = "it") -> Dict:
    """
    Recupera notizie personalizzate da NewsAPI.
    interests: lista di keyword basate sulle memorie utente
    """
    cache_key = f"news:{','.join(interests[:3])}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        api_key = os.getenv("NEWSAPI_KEY")
        if not api_key:
            logger.warning("NEWSAPI_KEY not set, using fallback")
            return _news_fallback(interests)

        import requests

        # Costruisci query basata su interessi (max 3 keyword)
        query = " OR ".join(interests[:3]) if interests else "Italia"

        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "apiKey": api_key,
            "country": location,
            "pageSize": 5,
            "language": "it"
        }

        # Se ci sono interessi specifici, usa /everything invece di /top-headlines
        if interests:
            url = "https://newsapi.org/v2/everything"
            params = {
                "apiKey": api_key,
                "q": query,
                "language": "it",
                "sortBy": "publishedAt",
                "pageSize": 5
            }

        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        articles = []
        for article in data.get("articles", [])[:5]:
            articles.append({
                "title": article.get("title", ""),
                "description": article.get("description", "")[:200],
                "source": article.get("source", {}).get("name", "Web"),
                "url": article.get("url", "")
            })

        result = {
            "success": True,
            "total": len(articles),
            "articles": articles,
            "interests": interests
        }

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"News API error: {e}")
        return _news_fallback(interests)

def _news_fallback(interests: List[str]) -> Dict:
    """Ritorna notizie di fallback"""
    return {
        "success": False,
        "total": 0,
        "articles": [],
        "interests": interests,
        "note": "API notizie non configurata"
    }

# ─────────────────────────────────────────────────────────────────────────────
# COMMUTE - stima traffico (usa dati statici o Google Maps API)
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_commute_internal(from_loc: str, to_loc: str) -> Dict:
    """
    Calcola tempo stimato di percorrenza.
    TODO: integrare Google Maps Distance Matrix API per dati reali.
    Per ora usa stime approssimative basate su orario.
    """
    cache_key = f"commute:{from_loc}:{to_loc}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        # Se disponibile, usa Google Maps API
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if api_key:
            import requests
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": from_loc,
                "destinations": to_loc,
                "key": api_key,
                "mode": "driving",
                "language": "it",
                "departure_time": "now"
            }

            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            if data["status"] == "OK":
                element = data["rows"][0]["elements"][0]
                if element["status"] == "OK":
                    result = {
                        "success": True,
                        "from": from_loc,
                        "to": to_loc,
                        "duration_minutes": element["duration"]["value"] // 60,
                        "duration_text": element["duration"]["text"],
                        "distance_km": element["distance"]["value"] / 1000,
                        "distance_text": element["distance"]["text"],
                        "traffic_delay": element.get("duration_in_traffic", {}).get("value", 0) // 60 - element["duration"]["value"] // 60
                    }
                    _set_cache(cache_key, result)
                    return result

        # Fallback: stima statica basata su ora del giorno
        hour = datetime.now().hour
        base_time = 25  # minuti base

        # Ore di punta: 7-9 e 17-19
        if (7 <= hour <= 9) or (17 <= hour <= 19):
            traffic_multiplier = 1.5
            traffic_note = "traffico intenso"
        elif (6 <= hour < 7) or (9 < hour < 17) or (19 < hour <= 20):
            traffic_multiplier = 1.2
            traffic_note = "traffico moderato"
        else:
            traffic_multiplier = 1.0
            traffic_note = "traffico scorrevole"

        estimated_time = int(base_time * traffic_multiplier)

        return {
            "success": True,
            "from": from_loc,
            "to": to_loc,
            "duration_minutes": estimated_time,
            "duration_text": f"{estimated_time} min",
            "distance_km": 15,
            "distance_text": "~15 km",
            "traffic_delay": int(base_time * (traffic_multiplier - 1)),
            "traffic_note": traffic_note,
            "note": "Stima approssimata - configura Google Maps API per dati reali"
        }

    except Exception as e:
        logger.error(f"Commute calculation error: {e}")
        return {
            "success": False,
            "error": str(e),
            "from": from_loc,
            "to": to_loc
        }

# ─────────────────────────────────────────────────────────────────────────────
# SUGGESTIONS - suggerimenti proattivi
# ─────────────────────────────────────────────────────────────────────────────

async def _suggest_optimizations(user_id: str, context_data: Dict) -> List[str]:
    """
    Genera suggerimenti proattivi basati su:
    - Calendario (eventi imminenti)
    - Meteo (consigli vestiario)
    - Casa (ottimizzazioni energetiche)
    - Routine (pattern apprese)
    """
    suggestions = []

    try:
        # Suggerimenti basati su calendario
        calendar = context_data.get("calendar", {})
        if calendar.get("success") and calendar.get("events"):
            next_event = calendar["events"][0]
            event_time = datetime.fromisoformat(next_event["start"].replace("Z", "+00:00"))
            time_until = event_time - datetime.now().astimezone()

            if time_until.total_seconds() < 3600:  # meno di 1 ora
                suggestions.append(f"⏰ Hai '{next_event['summary']}' tra {int(time_until.total_seconds()/60)} minuti")

            if next_event.get("location"):
                suggestions.append(f"📍 Ricorda: l'evento è a {next_event['location']}")

        # Suggerimenti meteo
        weather = context_data.get("weather", {})
        if weather.get("success"):
            temp = weather.get("temperature", 20)
            if temp < 10:
                suggestions.append("🧥 Temperatura bassa - porta una giacca pesante")
            elif temp < 15:
                suggestions.append("🧥 Fa freschetto - meglio portare una giacca")
            elif temp > 30:
                suggestions.append("☀️ Caldo intenso - ricorda di idratarti")

            if "pioggia" in weather.get("description", "").lower():
                suggestions.append("☔ Prevista pioggia - porta l'ombrello")

        # Suggerimenti casa
        home = context_data.get("home", {})
        if home.get("success"):
            lights_on = home.get("lights_on", 0)
            if lights_on > 0:
                hour = datetime.now().hour
                if hour > 8 and hour < 18:  # giorno
                    suggestions.append(f"💡 Hai {lights_on} luci accese in pieno giorno - considera di spegnerle")

        # Suggerimenti routine
        routine = context_data.get("routine", {})
        peak_hours = routine.get("peak_hours", [])
        current_hour = datetime.now().hour

        if peak_hours and current_hour in peak_hours:
            suggestions.append("📊 Sei più produttivo in questa fascia oraria")

        # Suggerimenti preferenze
        preferences = routine.get("preferences", [])
        if preferences:
            # Estrae keyword da preferenze per suggerimenti contestuali
            pref_text = " ".join([p["text"] for p in preferences[:3]]).lower()

            if "calcio" in pref_text or "partita" in pref_text:
                # Potrebbe controllare se oggi c'è partita della squadra preferita
                suggestions.append("⚽ Verifica se oggi gioca la tua squadra del cuore")

        return suggestions[:5]  # max 5 suggerimenti

    except Exception as e:
        logger.error(f"Error generating suggestions: {e}")
        return []

# ─────────────────────────────────────────────────────────────────────────────
# PLUGIN FUNCTIONS - esposte al sistema LLM
# ─────────────────────────────────────────────────────────────────────────────

@function(
    name="get_daily_context",
    description="Recupera tutti i dati contestuali giornalieri (calendario, meteo, casa, routine)",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID utente"
            },
            "location": {
                "type": "string",
                "description": "Città per meteo e notizie (default: Cagliari)"
            }
        },
        "required": ["user_id"]
    }
)
def get_daily_context(user_id: str, location: str = "Cagliari") -> Dict:
    """
    Raccoglie tutti i dati contestuali necessari per il briefing.
    Questa funzione NON genera il briefing vocale, ma solo i dati JSON.
    """
    try:
        # Usa asyncio.run per chiamare funzioni async (safe in plugin context)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Importa plugin manager per chiamare altri plugin
        from plugins import PluginManager
        pm = PluginManager()

        # Carica plugin necessari se non già caricati
        for plugin in ["calendar", "tuya", "web_search"]:
            try:
                if plugin not in pm.plugins:
                    pm.load_plugin(plugin)
            except:
                pass

        context = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "location": location
        }

        # 1. Calendario
        try:
            if "calendar_get_today_schedule_summary" in pm.functions:
                context["calendar"] = pm.call_function("calendar_get_today_schedule_summary")
            else:
                context["calendar"] = {"success": False, "note": "Calendar plugin not available"}
        except Exception as e:
            logger.error(f"Calendar error: {e}")
            context["calendar"] = {"success": False, "error": str(e)}

        # 2. Meteo
        context["weather"] = _get_weather_internal(location)

        # 3. Casa smart
        try:
            if "tuya_get_home_status_summary" in pm.functions:
                context["home"] = pm.call_function("tuya_get_home_status_summary")
            else:
                context["home"] = {"success": False, "note": "Smart home plugin not available"}
        except Exception as e:
            logger.error(f"Smart home error: {e}")
            context["home"] = {"success": False, "error": str(e)}

        # 4. Routine e preferenze
        context["routine"] = loop.run_until_complete(_analyze_routine_patterns(user_id))

        # 5. Notizie personalizzate
        interests = [p["text"].split()[0] for p in context["routine"].get("preferences", [])[:3]]
        if not interests:
            interests = ["Italia", "tecnologia"]
        context["news"] = _get_news_internal(interests, "it")

        loop.close()

        return {
            "success": True,
            "context": context
        }

    except Exception as e:
        logger.error(f"Error getting daily context: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@function(
    name="generate_morning_briefing",
    description="Genera un briefing completo mattutino personalizzato (stile Jarvis)",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID utente"
            },
            "location": {
                "type": "string",
                "description": "Città per meteo (default: Cagliari)"
            },
            "work_location": {
                "type": "string",
                "description": "Destinazione lavoro per calcolo traffico"
            }
        },
        "required": ["user_id"]
    }
)
def generate_morning_briefing(user_id: str, location: str = "Cagliari", work_location: str = None) -> Dict:
    """
    Genera briefing mattutino completo che combina:
    - Saluto personalizzato
    - Data e ora
    - Meteo
    - Eventi calendario
    - Stato casa
    - Notizie rilevanti
    - Suggerimenti proattivi
    - Tempo di percorrenza (se work_location specificato)
    """
    try:
        # Recupera contesto completo
        context_result = get_daily_context(user_id, location)

        if not context_result.get("success"):
            return {
                "success": False,
                "error": "Failed to gather context data"
            }

        context = context_result["context"]

        # Calcola traffico se destinazione fornita
        commute = None
        if work_location:
            commute = _calculate_commute_internal(location, work_location)

        # Genera suggerimenti
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        context["commute"] = commute
        suggestions = loop.run_until_complete(_suggest_optimizations(user_id, context))
        loop.close()

        # Compila briefing strutturato
        briefing = {
            "success": True,
            "timestamp": context["timestamp"],
            "user_id": user_id,
            "greeting": _generate_greeting(context["routine"]),
            "datetime": _format_datetime(),
            "weather": {
                "summary": f"{context['weather'].get('temperature', 'N/A')}°C, {context['weather'].get('description', 'N/A')}",
                "details": context["weather"]
            },
            "calendar": context["calendar"],
            "home": context["home"],
            "news": context["news"],
            "commute": commute,
            "suggestions": suggestions,
            "routine_insights": context["routine"]
        }

        # Genera versione vocale (naturale, stile Jarvis)
        briefing["voice_text"] = _generate_voice_briefing(briefing)

        return briefing

    except Exception as e:
        logger.error(f"Error generating morning briefing: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def _generate_greeting(routine: Dict) -> str:
    """Genera saluto personalizzato basato su routine"""
    hour = datetime.now().hour

    # Estrae nome da preferenze se disponibile
    name = None
    for pref in routine.get("preferences", []):
        if "chiama" in pref["text"].lower() or "nome" in pref["text"].lower():
            # Estrae nome (es: "L'utente si chiama Marco" -> "Marco")
            parts = pref["text"].split()
            if len(parts) > 0:
                name = parts[-1].strip(".,;:!?")

    name_part = f", {name}" if name else ""

    if hour < 6:
        return f"Notte fonda{name_part}! Tutto bene?"
    elif hour < 12:
        return f"Buongiorno{name_part}"
    elif hour < 18:
        return f"Buon pomeriggio{name_part}"
    else:
        return f"Buonasera{name_part}"


def _format_datetime() -> str:
    """Formatta data/ora corrente in italiano"""
    import locale
    try:
        locale.setlocale(locale.LC_TIME, "it_IT.UTF-8")
    except:
        pass

    now = datetime.now()
    return now.strftime("%A %d %B %Y, ore %H:%M")


def _generate_voice_briefing(briefing: Dict) -> str:
    """
    Genera versione vocale del briefing in stile Jarvis.
    Conciso, naturale, max 2 minuti di lettura (~300 parole).
    """
    lines = []

    # 1. Saluto
    lines.append(briefing["greeting"] + ".")
    lines.append(briefing["datetime"] + ".")

    # 2. Meteo
    weather = briefing["weather"]["details"]
    if weather.get("success"):
        temp = weather.get("temperature")
        desc = weather.get("description")
        feels = weather.get("feels_like")

        weather_line = f"Attualmente {temp} gradi, {desc}"
        if abs(temp - feels) > 3:
            weather_line += f", percepiti {feels}"
        lines.append(weather_line + ".")

    # 3. Calendario
    calendar = briefing["calendar"]
    if calendar.get("success") and calendar.get("events"):
        count = calendar.get("total_events", 0)
        if count == 1:
            lines.append("Hai un evento in agenda oggi.")
        elif count > 1:
            lines.append(f"Hai {count} eventi in agenda oggi.")

        # Primo evento
        first = calendar["events"][0]
        event_time = datetime.fromisoformat(first["start"].replace("Z", "+00:00"))
        time_str = event_time.strftime("%H:%M")
        lines.append(f"Il primo è '{first['summary']}' alle {time_str}.")
    else:
        lines.append("Nessun impegno in calendario oggi.")

    # 4. Traffico/Commute
    commute = briefing.get("commute")
    if commute and commute.get("success"):
        duration = commute.get("duration_minutes")
        delay = commute.get("traffic_delay", 0)
        traffic_note = commute.get("traffic_note", "")

        if delay > 5:
            lines.append(f"Tempo di percorrenza stimato: {duration} minuti, {traffic_note}.")
        else:
            lines.append(f"Strada libera, circa {duration} minuti.")

    # 5. Casa
    home = briefing["home"]
    if home.get("success"):
        lights = home.get("lights_on", 0)
        temp = home.get("temperature")

        if lights > 0:
            lines.append(f"In casa hai {lights} luci accese.")

        if temp:
            lines.append(f"Temperatura interna: {temp} gradi.")

    # 6. Suggerimenti (max 3)
    suggestions = briefing.get("suggestions", [])
    if suggestions:
        lines.append("Alcuni suggerimenti:")
        for sugg in suggestions[:3]:
            # Rimuovi emoji per versione vocale
            clean_sugg = ''.join(c for c in sugg if c.isalnum() or c.isspace() or c in "',.-:;!?")
            lines.append(clean_sugg.strip())

    # 7. Notizie (solo headline principale)
    news = briefing["news"]
    if news.get("success") and news.get("articles"):
        first_news = news["articles"][0]
        lines.append(f"Nelle notizie: {first_news['title']}.")

    # 8. Chiusura
    lines.append("Buona giornata!")

    return " ".join(lines)


@function(
    name="calculate_commute_time",
    description="Calcola tempo di percorrenza tra due luoghi considerando traffico",
    parameters={
        "type": "object",
        "properties": {
            "location_from": {
                "type": "string",
                "description": "Località di partenza"
            },
            "location_to": {
                "type": "string",
                "description": "Località di destinazione"
            }
        },
        "required": ["location_from", "location_to"]
    }
)
def calculate_commute_time(location_from: str, location_to: str) -> Dict:
    """Calcola tempo di percorrenza con traffico attuale"""
    return _calculate_commute_internal(location_from, location_to)


@function(
    name="get_personalized_news",
    description="Recupera notizie personalizzate basate sugli interessi dell'utente",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID utente"
            },
            "max_results": {
                "type": "integer",
                "description": "Numero massimo di articoli (default: 5)"
            }
        },
        "required": ["user_id"]
    }
)
def get_personalized_news(user_id: str, max_results: int = 5) -> Dict:
    """
    Recupera notizie filtrate per interessi utente dalle memorie.
    """
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        routine = loop.run_until_complete(_analyze_routine_patterns(user_id))
        loop.close()

        # Estrae keyword interessi
        interests = []
        for pref in routine.get("preferences", [])[:5]:
            text = pref["text"].lower()
            # Estrae keyword significative
            keywords = ["calcio", "politica", "tecnologia", "economia", "sport", "musica", "cinema"]
            for kw in keywords:
                if kw in text:
                    interests.append(kw)

        if not interests:
            interests = ["Italia"]

        return _get_news_internal(list(set(interests)), "it")

    except Exception as e:
        logger.error(f"Error getting personalized news: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@function(
    name="analyze_routine_patterns",
    description="Analizza pattern comportamentali e routine dell'utente",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID utente"
            }
        },
        "required": ["user_id"]
    }
)
def analyze_routine_patterns(user_id: str) -> Dict:
    """Espone analisi routine come funzione chiamabile dal LLM"""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        routine = loop.run_until_complete(_analyze_routine_patterns(user_id))
        loop.close()

        return {
            "success": True,
            "routine": routine
        }

    except Exception as e:
        logger.error(f"Error analyzing routine: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@function(
    name="suggest_daily_optimizations",
    description="Genera suggerimenti proattivi personalizzati per la giornata",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID utente"
            },
            "location": {
                "type": "string",
                "description": "Città (default: Cagliari)"
            }
        },
        "required": ["user_id"]
    }
)
def suggest_daily_optimizations(user_id: str, location: str = "Cagliari") -> Dict:
    """Genera suggerimenti contestuali proattivi"""
    try:
        context_result = get_daily_context(user_id, location)

        if not context_result.get("success"):
            return {
                "success": False,
                "error": "Failed to get context"
            }

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        suggestions = loop.run_until_complete(
            _suggest_optimizations(user_id, context_result["context"])
        )
        loop.close()

        return {
            "success": True,
            "suggestions": suggestions,
            "count": len(suggestions)
        }

    except Exception as e:
        logger.error(f"Error generating suggestions: {e}")
        return {
            "success": False,
            "error": str(e)
        }
