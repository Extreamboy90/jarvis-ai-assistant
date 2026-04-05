"""
Neuralink Health Plugin - Biometric and Health Data Integration

Integrates fitness trackers and smartwatches for health monitoring, coaching,
and correlations with memory/behavior patterns.

Features:
- Google Fit API integration
- File-based import (CSV/JSON exports from Fitbit, Apple Health, Garmin)
- Sleep analysis and activity tracking
- Heart rate trends and anomaly detection
- AI-powered nutrition tracking
- Personalized workout suggestions
- Wellness reports with memory correlations

Security:
- OAuth2 with PKCE for Google Fit
- No plain-text logging of health data
- Encryption at rest (PostgreSQL)
- Easy account disconnection
"""

import os
import json
import logging
import csv
import io
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any
import database
from plugins import function

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

GOOGLE_FIT_CREDENTIALS_PATH = os.getenv("GOOGLE_FIT_CREDENTIALS_PATH", "google_fit_credentials.json")
GOOGLE_FIT_TOKEN_PATH = os.getenv("GOOGLE_FIT_TOKEN_PATH", "google_fit_token.json")

# Health metric types
METRIC_TYPES = {
    "steps": "Daily step count",
    "calories": "Calories burned",
    "heart_rate": "Heart rate (bpm)",
    "sleep": "Sleep duration (hours)",
    "weight": "Body weight (kg)",
    "blood_pressure": "Blood pressure (systolic/diastolic)",
    "oxygen": "Blood oxygen saturation (%)",
    "stress": "Stress level (1-10)",
}

# Workout types
WORKOUT_TYPES = ["running", "walking", "cycling", "swimming", "yoga", "gym", "hiking", "other"]

# Goal types
GOAL_TYPES = ["steps", "calories", "sleep", "weight", "workouts_per_week", "active_minutes"]

# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE FIT INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

def _get_google_fit_service(user_id: str):
    """
    Initialize Google Fit API service with OAuth2 authentication.

    Uses PKCE flow for enhanced security.
    Stores tokens per-user in database for multi-user support.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        SCOPES = [
            'https://www.googleapis.com/auth/fitness.activity.read',
            'https://www.googleapis.com/auth/fitness.body.read',
            'https://www.googleapis.com/auth/fitness.heart_rate.read',
            'https://www.googleapis.com/auth/fitness.sleep.read',
        ]

        creds = None

        # Try to load credentials from database
        import asyncio
        async def get_token():
            async with database.pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT metadata->>'google_fit_token' as token FROM users WHERE user_id = $1",
                    user_id
                )
                return row['token'] if row and row['token'] else None

        token_json = asyncio.run(get_token())

        if token_json:
            creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(GOOGLE_FIT_CREDENTIALS_PATH):
                    raise FileNotFoundError(
                        f"Google Fit credentials file not found at {GOOGLE_FIT_CREDENTIALS_PATH}. "
                        "Please follow setup instructions in README."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    GOOGLE_FIT_CREDENTIALS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save credentials to database
            async def save_token():
                async with database.pg_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE users
                        SET metadata = jsonb_set(
                            COALESCE(metadata, '{}'::jsonb),
                            '{google_fit_token}',
                            $1::jsonb
                        )
                        WHERE user_id = $2
                        """,
                        json.dumps(json.loads(creds.to_json())),
                        user_id
                    )

            asyncio.run(save_token())

        return build('fitness', 'v1', credentials=creds)

    except ImportError:
        logger.error("Google Fit dependencies not installed. Run: pip install google-auth-oauthlib google-api-python-client")
        return None
    except Exception as e:
        logger.error(f"Error initializing Google Fit service: {e}")
        return None


def _fetch_google_fit_data(user_id: str, data_type: str, start_date: datetime, end_date: datetime) -> List[Dict]:
    """
    Fetch data from Google Fit API.

    Args:
        user_id: User identifier
        data_type: Type of data (steps, calories, heart_rate, sleep)
        start_date: Start of date range
        end_date: End of date range

    Returns:
        List of data points with timestamps and values
    """
    try:
        service = _get_google_fit_service(user_id)
        if not service:
            return []

        # Map data types to Google Fit data source IDs
        data_sources = {
            "steps": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps",
            "calories": "derived:com.google.calories.expended:com.google.android.gms:merge_calories_expended",
            "heart_rate": "derived:com.google.heart_rate.bpm:com.google.android.gms:merge_heart_rate_bpm",
            "sleep": "derived:com.google.sleep.segment:com.google.android.gms:merged",
        }

        if data_type not in data_sources:
            logger.warning(f"Unsupported Google Fit data type: {data_type}")
            return []

        # Convert to nanoseconds (Google Fit format)
        start_time_ns = int(start_date.timestamp() * 1e9)
        end_time_ns = int(end_date.timestamp() * 1e9)

        # Query Google Fit API
        dataset_id = f"{start_time_ns}-{end_time_ns}"
        dataset = service.users().dataSources().datasets().get(
            userId='me',
            dataSourceId=data_sources[data_type],
            datasetId=dataset_id
        ).execute()

        # Parse results
        results = []
        for point in dataset.get('point', []):
            timestamp = datetime.fromtimestamp(int(point['startTimeNanos']) / 1e9)

            # Extract value based on data type
            value = None
            if 'value' in point and len(point['value']) > 0:
                if data_type == "sleep":
                    # Sleep duration in minutes
                    start = int(point['startTimeNanos']) / 1e9
                    end = int(point['endTimeNanos']) / 1e9
                    value = (end - start) / 3600  # Convert to hours
                else:
                    value = point['value'][0].get('intVal') or point['value'][0].get('fpVal')

            if value is not None:
                results.append({
                    'timestamp': timestamp.isoformat(),
                    'value': float(value),
                    'source': 'google_fit'
                })

        logger.info(f"Fetched {len(results)} {data_type} data points from Google Fit for user {user_id}")
        return results

    except Exception as e:
        logger.error(f"Error fetching Google Fit data: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# FILE IMPORT PARSERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_apple_health_export(file_content: str) -> List[Dict]:
    """
    Parse Apple Health export XML/JSON format.

    Supports export format from Apple Health app.
    """
    results = []
    try:
        # Apple Health exports are typically XML
        # For simplicity, we'll support a simplified JSON format
        data = json.loads(file_content)

        for record in data.get('records', []):
            metric_type = record.get('type', '').lower()

            # Map Apple Health types to our metric types
            type_mapping = {
                'stepcount': 'steps',
                'activeenergyburned': 'calories',
                'heartrate': 'heart_rate',
                'sleepanalysis': 'sleep',
                'bodymass': 'weight',
            }

            for apple_type, our_type in type_mapping.items():
                if apple_type in metric_type:
                    results.append({
                        'timestamp': record.get('startDate', record.get('date')),
                        'metric_type': our_type,
                        'value': float(record.get('value', 0)),
                        'source': 'apple_health',
                        'metadata': {'unit': record.get('unit', '')}
                    })
                    break

    except json.JSONDecodeError:
        logger.error("Invalid Apple Health JSON format")
    except Exception as e:
        logger.error(f"Error parsing Apple Health export: {e}")

    return results


def _parse_fitbit_export(file_content: str) -> List[Dict]:
    """
    Parse Fitbit CSV export format.

    Fitbit exports daily summaries as CSV files.
    """
    results = []
    try:
        csv_file = io.StringIO(file_content)
        reader = csv.DictReader(csv_file)

        for row in reader:
            date_str = row.get('Date', row.get('date', ''))
            if not date_str:
                continue

            # Parse common Fitbit fields
            if 'Steps' in row:
                results.append({
                    'timestamp': date_str,
                    'metric_type': 'steps',
                    'value': float(row['Steps']),
                    'source': 'fitbit'
                })

            if 'Calories Burned' in row:
                results.append({
                    'timestamp': date_str,
                    'metric_type': 'calories',
                    'value': float(row['Calories Burned']),
                    'source': 'fitbit'
                })

            if 'Minutes Asleep' in row:
                results.append({
                    'timestamp': date_str,
                    'metric_type': 'sleep',
                    'value': float(row['Minutes Asleep']) / 60,  # Convert to hours
                    'source': 'fitbit'
                })

    except Exception as e:
        logger.error(f"Error parsing Fitbit export: {e}")

    return results


def _parse_garmin_export(file_content: str) -> List[Dict]:
    """
    Parse Garmin Connect CSV export format.
    """
    results = []
    try:
        csv_file = io.StringIO(file_content)
        reader = csv.DictReader(csv_file)

        for row in reader:
            date_str = row.get('Date', row.get('date', ''))
            if not date_str:
                continue

            # Parse common Garmin fields
            if 'Steps' in row:
                results.append({
                    'timestamp': date_str,
                    'metric_type': 'steps',
                    'value': float(row['Steps']),
                    'source': 'garmin'
                })

            if 'Calories' in row:
                results.append({
                    'timestamp': date_str,
                    'metric_type': 'calories',
                    'value': float(row['Calories']),
                    'source': 'garmin'
                })

            if 'Sleep Time' in row:
                # Garmin exports sleep as HH:MM format
                time_parts = row['Sleep Time'].split(':')
                if len(time_parts) == 2:
                    hours = float(time_parts[0]) + float(time_parts[1]) / 60
                    results.append({
                        'timestamp': date_str,
                        'metric_type': 'sleep',
                        'value': hours,
                        'source': 'garmin'
                    })

    except Exception as e:
        logger.error(f"Error parsing Garmin export: {e}")

    return results


def _parse_generic_csv(file_content: str) -> List[Dict]:
    """
    Parse generic CSV format with columns: date, metric_type, value
    """
    results = []
    try:
        csv_file = io.StringIO(file_content)
        reader = csv.DictReader(csv_file)

        for row in reader:
            if 'date' in row and 'metric_type' in row and 'value' in row:
                results.append({
                    'timestamp': row['date'],
                    'metric_type': row['metric_type'],
                    'value': float(row['value']),
                    'source': 'csv_import',
                    'metadata': {k: v for k, v in row.items() if k not in ['date', 'metric_type', 'value']}
                })

    except Exception as e:
        logger.error(f"Error parsing generic CSV: {e}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def _save_health_data(user_id: str, data_points: List[Dict]) -> int:
    """Save health data points to database."""
    saved_count = 0

    try:
        async with database.pg_pool.acquire() as conn:
            for point in data_points:
                # Parse timestamp
                timestamp = point.get('timestamp')
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except:
                        timestamp = datetime.fromisoformat(timestamp)

                # Insert or update (avoid duplicates)
                await conn.execute(
                    """
                    INSERT INTO health_data (user_id, timestamp, metric_type, value, metadata)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id, timestamp, metric_type)
                    DO UPDATE SET value = EXCLUDED.value, metadata = EXCLUDED.metadata
                    """,
                    user_id,
                    timestamp,
                    point.get('metric_type'),
                    float(point.get('value', 0)),
                    json.dumps(point.get('metadata', {'source': point.get('source', 'unknown')}))
                )
                saved_count += 1

    except Exception as e:
        logger.error(f"Error saving health data: {e}")

    return saved_count


async def _get_health_data(
    user_id: str,
    metric_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100
) -> List[Dict]:
    """Retrieve health data from database."""
    try:
        async with database.pg_pool.acquire() as conn:
            query = "SELECT * FROM health_data WHERE user_id = $1"
            params = [user_id]
            param_count = 1

            if metric_type:
                param_count += 1
                query += f" AND metric_type = ${param_count}"
                params.append(metric_type)

            if start_date:
                param_count += 1
                query += f" AND timestamp >= ${param_count}"
                params.append(start_date)

            if end_date:
                param_count += 1
                query += f" AND timestamp <= ${param_count}"
                params.append(end_date)

            query += f" ORDER BY timestamp DESC LIMIT ${param_count + 1}"
            params.append(limit)

            rows = await conn.fetch(query, *params)

            return [
                {
                    'timestamp': row['timestamp'].isoformat(),
                    'metric_type': row['metric_type'],
                    'value': float(row['value']),
                    'metadata': json.loads(row['metadata']) if row['metadata'] else {}
                }
                for row in rows
            ]

    except Exception as e:
        logger.error(f"Error retrieving health data: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# AI-POWERED ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

async def _llm_analyze_health(prompt: str, user_data: str) -> str:
    """Use LLM to analyze health data and provide insights."""
    try:
        # Import Gemini client (follows project architecture)
        from gemini_client import GeminiClient

        gemini_client = GeminiClient()

        full_prompt = f"""{prompt}

Dati utente:
{user_data}

IMPORTANTE: Non sei un medico. Le tue indicazioni sono solo suggerimenti generali di benessere.
Se rilevi anomalie preoccupanti, consiglia di consultare un medico.

Rispondi in italiano, in modo chiaro e conciso."""

        if gemini_client.check_availability():
            result = gemini_client.chat(
                messages=[{"role": "user", "content": full_prompt}],
                use_smart=True,
                temperature=0.7,
                max_tokens=1024
            )
            return result.get("message", "Analisi non disponibile.")
        else:
            # Fallback to Ollama
            import requests
            ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
            ollama_model = os.getenv("OLLAMA_MODEL_SMART", "llama3.1:8b")

            response = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": ollama_model, "prompt": full_prompt, "stream": False},
                timeout=30
            )

            if response.status_code == 200:
                return response.json().get("response", "Analisi non disponibile.")

    except Exception as e:
        logger.error(f"Error in LLM health analysis: {e}")

    return "Analisi non disponibile al momento."


# ─────────────────────────────────────────────────────────────────────────────
# PLUGIN FUNCTIONS (Exposed to LLM)
# ─────────────────────────────────────────────────────────────────────────────

@function(
    name="sync_health_data",
    description="Sincronizza dati di salute da fitness tracker o smartwatch (Google Fit, Fitbit, Apple Health, Garmin)",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            },
            "source": {
                "type": "string",
                "enum": ["google_fit", "file"],
                "description": "Fonte dei dati: google_fit per sincronizzazione automatica, file per import manuale"
            },
            "days": {
                "type": "integer",
                "description": "Numero di giorni da sincronizzare (default: 7)",
                "default": 7
            }
        },
        "required": ["user_id", "source"]
    }
)
def sync_health_data(user_id: str, source: str = "google_fit", days: int = 7) -> Dict:
    """Synchronize health data from various sources."""
    try:
        import asyncio

        if source == "google_fit":
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            all_data = []
            for data_type in ["steps", "calories", "heart_rate", "sleep"]:
                data = _fetch_google_fit_data(user_id, data_type, start_date, end_date)
                for point in data:
                    point['metric_type'] = data_type
                all_data.extend(data)

            if not all_data:
                return {
                    "success": False,
                    "message": "Nessun dato disponibile da Google Fit. Verifica autorizzazioni."
                }

            saved = asyncio.run(_save_health_data(user_id, all_data))

            return {
                "success": True,
                "message": f"Sincronizzati {saved} dati da Google Fit (ultimi {days} giorni)",
                "data_points": saved,
                "source": "google_fit"
            }

        else:
            return {
                "success": False,
                "message": "Per import da file, usa l'endpoint /health/{user_id}/import con file CSV/JSON"
            }

    except Exception as e:
        logger.error(f"Error syncing health data: {e}")
        return {
            "success": False,
            "message": f"Errore nella sincronizzazione: {str(e)}"
        }


@function(
    name="get_sleep_analysis",
    description="Analizza la qualità del sonno degli ultimi giorni con insights AI",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            },
            "days": {
                "type": "integer",
                "description": "Numero di giorni da analizzare (default: 7)",
                "default": 7
            }
        },
        "required": ["user_id"]
    }
)
def get_sleep_analysis(user_id: str, days: int = 7) -> Dict:
    """Analyze sleep quality with AI-powered insights."""
    try:
        import asyncio

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        sleep_data = asyncio.run(_get_health_data(
            user_id,
            metric_type="sleep",
            start_date=start_date,
            end_date=end_date
        ))

        if not sleep_data:
            return {
                "success": False,
                "message": f"Nessun dato sul sonno disponibile per gli ultimi {days} giorni"
            }

        # Calculate statistics
        sleep_hours = [d['value'] for d in sleep_data]
        avg_sleep = sum(sleep_hours) / len(sleep_hours)
        min_sleep = min(sleep_hours)
        max_sleep = max(sleep_hours)

        # AI analysis
        data_summary = f"""
        Periodo: ultimi {days} giorni
        Media sonno: {avg_sleep:.1f} ore/notte
        Range: {min_sleep:.1f}h - {max_sleep:.1f}h
        Notti registrate: {len(sleep_data)}
        Dettaglio: {', '.join([f"{d['timestamp'].split('T')[0]}: {d['value']:.1f}h" for d in sleep_data[:5]])}
        """

        analysis = asyncio.run(_llm_analyze_health(
            "Analizza questi dati sul sonno e fornisci: 1) Valutazione qualità (scarsa/sufficiente/buona/ottima), "
            "2) Pattern identificati, 3) Suggerimenti per migliorare",
            data_summary
        ))

        return {
            "success": True,
            "period_days": days,
            "nights_tracked": len(sleep_data),
            "average_hours": round(avg_sleep, 1),
            "min_hours": round(min_sleep, 1),
            "max_hours": round(max_sleep, 1),
            "quality_score": "buona" if 7 <= avg_sleep <= 9 else "sufficiente" if 6 <= avg_sleep < 7 else "scarsa",
            "ai_analysis": analysis,
            "raw_data": sleep_data[:7]  # Last 7 nights
        }

    except Exception as e:
        logger.error(f"Error in sleep analysis: {e}")
        return {"success": False, "message": str(e)}


@function(
    name="get_activity_summary",
    description="Ottieni un riepilogo delle attività fisiche di un giorno specifico (passi, calorie, allenamenti)",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            },
            "date": {
                "type": "string",
                "description": "Data nel formato YYYY-MM-DD (default: oggi)",
                "default": None
            }
        },
        "required": ["user_id"]
    }
)
def get_activity_summary(user_id: str, date: Optional[str] = None) -> Dict:
    """Get activity summary for a specific date."""
    try:
        import asyncio

        if date:
            target_date = datetime.fromisoformat(date)
        else:
            target_date = datetime.now()

        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        # Fetch all metrics for the day
        steps_data = asyncio.run(_get_health_data(
            user_id, "steps", start_of_day, end_of_day
        ))
        calories_data = asyncio.run(_get_health_data(
            user_id, "calories", start_of_day, end_of_day
        ))

        # Get workouts
        async def get_workouts():
            async with database.pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT type, duration_minutes, calories, intensity
                    FROM workouts
                    WHERE user_id = $1 AND date = $2
                    """,
                    user_id, target_date.date()
                )
                return [dict(row) for row in rows]

        workouts = asyncio.run(get_workouts())

        total_steps = sum(d['value'] for d in steps_data)
        total_calories = sum(d['value'] for d in calories_data)

        return {
            "success": True,
            "date": target_date.date().isoformat(),
            "steps": int(total_steps),
            "calories": int(total_calories),
            "workouts": workouts,
            "total_workouts": len(workouts),
            "active": total_steps > 5000 or len(workouts) > 0
        }

    except Exception as e:
        logger.error(f"Error getting activity summary: {e}")
        return {"success": False, "message": str(e)}


@function(
    name="get_heart_rate_trends",
    description="Analizza i trend del battito cardiaco negli ultimi giorni",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            },
            "days": {
                "type": "integer",
                "description": "Numero di giorni da analizzare (default: 30)",
                "default": 30
            }
        },
        "required": ["user_id"]
    }
)
def get_heart_rate_trends(user_id: str, days: int = 30) -> Dict:
    """Analyze heart rate trends over time."""
    try:
        import asyncio

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        hr_data = asyncio.run(_get_health_data(
            user_id,
            metric_type="heart_rate",
            start_date=start_date,
            end_date=end_date
        ))

        if not hr_data:
            return {
                "success": False,
                "message": f"Nessun dato battito cardiaco disponibile per gli ultimi {days} giorni"
            }

        # Calculate statistics
        heart_rates = [d['value'] for d in hr_data]
        avg_hr = sum(heart_rates) / len(heart_rates)
        min_hr = min(heart_rates)
        max_hr = max(heart_rates)
        resting_hr = sorted(heart_rates)[:len(heart_rates)//4]  # Bottom 25%
        avg_resting = sum(resting_hr) / len(resting_hr) if resting_hr else avg_hr

        return {
            "success": True,
            "period_days": days,
            "measurements": len(hr_data),
            "average_bpm": round(avg_hr, 1),
            "resting_bpm": round(avg_resting, 1),
            "min_bpm": round(min_hr, 1),
            "max_bpm": round(max_hr, 1),
            "trend": "normale" if 60 <= avg_resting <= 100 else "consulta_medico",
            "recent_readings": [
                {"time": d['timestamp'], "bpm": d['value']}
                for d in hr_data[:10]
            ]
        }

    except Exception as e:
        logger.error(f"Error analyzing heart rate: {e}")
        return {"success": False, "message": str(e)}


@function(
    name="suggest_workout",
    description="Suggerisci un allenamento personalizzato basato sullo stato fisico attuale e storico dell'utente",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            }
        },
        "required": ["user_id"]
    }
)
def suggest_workout(user_id: str) -> Dict:
    """Suggest personalized workout based on user's current state and history."""
    try:
        import asyncio

        # Get recent activity
        today_activity = get_activity_summary(user_id)
        sleep_analysis = get_sleep_analysis(user_id, days=3)

        # Get goals
        async def get_goals():
            async with database.pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT goal_type, target_value, current_value FROM health_goals WHERE user_id = $1",
                    user_id
                )
                return [dict(row) for row in rows]

        goals = asyncio.run(get_goals())

        # Prepare context for AI
        context = f"""
        Attività oggi: {today_activity.get('steps', 0)} passi, {today_activity.get('calories', 0)} calorie
        Allenamenti oggi: {today_activity.get('total_workouts', 0)}
        Qualità sonno (ultimi 3 giorni): {sleep_analysis.get('average_hours', 0):.1f} ore/notte
        Obiettivi: {', '.join([f"{g['goal_type']}: {g['target_value']}" for g in goals]) if goals else 'Nessuno'}
        """

        suggestion = asyncio.run(_llm_analyze_health(
            "Suggerisci un allenamento appropriato per oggi. Considera: "
            "1) Livello attività già svolta, 2) Qualità sonno, 3) Obiettivi utente. "
            "Specifica: tipo allenamento, durata, intensità, consigli.",
            context
        ))

        return {
            "success": True,
            "current_state": {
                "steps_today": today_activity.get('steps', 0),
                "workouts_today": today_activity.get('total_workouts', 0),
                "sleep_quality": sleep_analysis.get('quality_score', 'sconosciuta')
            },
            "suggestion": suggestion,
            "goals": goals
        }

    except Exception as e:
        logger.error(f"Error suggesting workout: {e}")
        return {"success": False, "message": str(e)}


@function(
    name="track_nutrition",
    description="Traccia un pasto e stima calorie/macronutrienti usando AI",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            },
            "meal_description": {
                "type": "string",
                "description": "Descrizione del pasto (es: 'pasta al pomodoro 150g, petto di pollo 100g, insalata')"
            }
        },
        "required": ["user_id", "meal_description"]
    }
)
def track_nutrition(user_id: str, meal_description: str) -> Dict:
    """Track meal and estimate calories/macros using LLM."""
    try:
        import asyncio

        prompt = f"""Analizza questo pasto e fornisci una stima nutrizionale:

Pasto: {meal_description}

Fornisci (formato JSON):
{{
  "calories": <numero stimato>,
  "protein_g": <grammi proteine>,
  "carbs_g": <grammi carboidrati>,
  "fat_g": <grammi grassi>,
  "meal_type": "<colazione/pranzo/cena/snack>",
  "healthiness_score": <1-10>,
  "notes": "<eventuali note>"
}}
"""

        analysis = asyncio.run(_llm_analyze_health(prompt, ""))

        # Try to parse JSON from response
        try:
            import re
            json_match = re.search(r'\{[^{}]*\}', analysis, re.DOTALL)
            if json_match:
                nutrition_data = json.loads(json_match.group())
            else:
                nutrition_data = {
                    "calories": 0,
                    "notes": analysis
                }
        except:
            nutrition_data = {"notes": analysis}

        # Save to database as calories entry
        if nutrition_data.get('calories'):
            asyncio.run(_save_health_data(user_id, [{
                'timestamp': datetime.now().isoformat(),
                'metric_type': 'calories',
                'value': nutrition_data['calories'],
                'metadata': {
                    'source': 'manual_nutrition',
                    'meal': meal_description,
                    **nutrition_data
                }
            }]))

        return {
            "success": True,
            "meal": meal_description,
            **nutrition_data,
            "disclaimer": "Stima approssimativa. Non sostituisce consulenza nutrizionale professionale."
        }

    except Exception as e:
        logger.error(f"Error tracking nutrition: {e}")
        return {"success": False, "message": str(e)}


@function(
    name="set_health_goals",
    description="Imposta obiettivi di salute/fitness (passi giornalieri, peso target, allenamenti settimanali, ecc.)",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            },
            "goals": {
                "type": "object",
                "description": "Dizionario di obiettivi: {goal_type: target_value}",
                "additionalProperties": True
            }
        },
        "required": ["user_id", "goals"]
    }
)
def set_health_goals(user_id: str, goals: Dict[str, Any]) -> Dict:
    """Set health and fitness goals."""
    try:
        import asyncio

        async def save_goals():
            saved = []
            async with database.pg_pool.acquire() as conn:
                for goal_type, target_value in goals.items():
                    if goal_type not in GOAL_TYPES:
                        continue

                    await conn.execute(
                        """
                        INSERT INTO health_goals (user_id, goal_type, target_value, current_value)
                        VALUES ($1, $2, $3, 0)
                        ON CONFLICT (user_id, goal_type)
                        DO UPDATE SET target_value = EXCLUDED.target_value, updated_at = CURRENT_TIMESTAMP
                        """,
                        user_id, goal_type, float(target_value)
                    )
                    saved.append(goal_type)
            return saved

        saved_goals = asyncio.run(save_goals())

        return {
            "success": True,
            "message": f"Obiettivi impostati: {', '.join(saved_goals)}",
            "goals": goals
        }

    except Exception as e:
        logger.error(f"Error setting health goals: {e}")
        return {"success": False, "message": str(e)}


@function(
    name="generate_wellness_report",
    description="Genera un report completo di benessere per un periodo (oggi/settimana/mese)",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            },
            "period": {
                "type": "string",
                "enum": ["today", "week", "month"],
                "description": "Periodo del report",
                "default": "week"
            }
        },
        "required": ["user_id"]
    }
)
def generate_wellness_report(user_id: str, period: str = "week") -> Dict:
    """Generate comprehensive wellness report with AI insights."""
    try:
        import asyncio

        # Map period to days
        period_days = {"today": 1, "week": 7, "month": 30}
        days = period_days.get(period, 7)

        # Collect all health metrics
        sleep = get_sleep_analysis(user_id, days)
        activity = get_activity_summary(user_id)
        heart_rate = get_heart_rate_trends(user_id, days)

        # Get all goals progress
        async def get_goals_progress():
            async with database.pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT goal_type, target_value, current_value,
                           ROUND((current_value::float / target_value::float) * 100) as progress_pct
                    FROM health_goals
                    WHERE user_id = $1
                    """,
                    user_id
                )
                return [dict(row) for row in rows]

        goals_progress = asyncio.run(get_goals_progress())

        # Generate AI summary
        report_data = f"""
        PERIODO: {period} ({days} giorni)

        SONNO:
        - Media: {sleep.get('average_hours', 0):.1f} ore/notte
        - Qualità: {sleep.get('quality_score', 'N/A')}

        ATTIVITÀ FISICA:
        - Passi oggi: {activity.get('steps', 0)}
        - Allenamenti oggi: {activity.get('total_workouts', 0)}

        BATTITO CARDIACO:
        - Media: {heart_rate.get('average_bpm', 0):.0f} bpm
        - A riposo: {heart_rate.get('resting_bpm', 0):.0f} bpm

        OBIETTIVI:
        {chr(10).join([f"- {g['goal_type']}: {g['progress_pct']}% completato ({g['current_value']}/{g['target_value']})" for g in goals_progress])}
        """

        ai_summary = asyncio.run(_llm_analyze_health(
            f"Genera un report di benessere per il periodo '{period}'. "
            "Include: 1) Riepilogo generale, 2) Aree di forza, 3) Aree da migliorare, "
            "4) Raccomandazioni concrete, 5) Motivazione.",
            report_data
        ))

        return {
            "success": True,
            "period": period,
            "days": days,
            "generated_at": datetime.now().isoformat(),
            "metrics": {
                "sleep": sleep,
                "activity": activity,
                "heart_rate": heart_rate
            },
            "goals_progress": goals_progress,
            "ai_summary": ai_summary,
            "overall_score": _calculate_wellness_score(sleep, activity, heart_rate, goals_progress)
        }

    except Exception as e:
        logger.error(f"Error generating wellness report: {e}")
        return {"success": False, "message": str(e)}


@function(
    name="detect_anomalies",
    description="Rileva pattern anomali nei dati di salute (stress elevato, sonno insufficiente, battito irregolare)",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            }
        },
        "required": ["user_id"]
    }
)
def detect_anomalies(user_id: str) -> Dict:
    """Detect anomalous health patterns."""
    try:
        import asyncio

        anomalies = []

        # Check sleep
        sleep = get_sleep_analysis(user_id, days=7)
        if sleep.get('success') and sleep.get('average_hours', 0) < 6:
            anomalies.append({
                "type": "sleep_deficit",
                "severity": "high",
                "message": f"Sonno insufficiente: media {sleep['average_hours']:.1f}h/notte (raccomandato: 7-9h)",
                "recommendation": "Prioritizza il sonno. Vai a letto prima e mantieni orari regolari."
            })

        # Check heart rate
        hr = get_heart_rate_trends(user_id, days=7)
        if hr.get('success'):
            resting_hr = hr.get('resting_bpm', 70)
            if resting_hr > 100:
                anomalies.append({
                    "type": "elevated_resting_hr",
                    "severity": "medium",
                    "message": f"Battito a riposo elevato: {resting_hr:.0f} bpm (normale: 60-100 bpm)",
                    "recommendation": "Monitora nei prossimi giorni. Se persiste, consulta un medico."
                })
            elif resting_hr < 50:
                anomalies.append({
                    "type": "low_resting_hr",
                    "severity": "low",
                    "message": f"Battito a riposo basso: {resting_hr:.0f} bpm",
                    "recommendation": "Potrebbe indicare ottima forma fisica. Se hai sintomi, consulta un medico."
                })

        # Check activity
        activity = get_activity_summary(user_id)
        if activity.get('success') and activity.get('steps', 0) < 2000:
            anomalies.append({
                "type": "low_activity",
                "severity": "medium",
                "message": f"Attività fisica molto bassa oggi: {activity['steps']} passi",
                "recommendation": "Prova a fare una passeggiata di 15-20 minuti."
            })

        if not anomalies:
            return {
                "success": True,
                "anomalies_detected": False,
                "message": "Nessuna anomalia rilevata. I tuoi dati di salute sembrano nella norma!"
            }

        return {
            "success": True,
            "anomalies_detected": True,
            "count": len(anomalies),
            "anomalies": anomalies,
            "disclaimer": "Queste sono solo osservazioni automatiche. Consulta un medico per valutazioni mediche."
        }

    except Exception as e:
        logger.error(f"Error detecting anomalies: {e}")
        return {"success": False, "message": str(e)}


@function(
    name="correlate_with_memory",
    description="Correla metriche di salute con eventi/stati emotivi memorizzati dal sistema (es: sonno scarso dopo eventi stressanti)",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "ID dell'utente"
            },
            "metric": {
                "type": "string",
                "enum": ["sleep", "heart_rate", "activity", "all"],
                "description": "Metrica da correlare",
                "default": "all"
            },
            "days": {
                "type": "integer",
                "description": "Giorni da analizzare",
                "default": 14
            }
        },
        "required": ["user_id"]
    }
)
def correlate_with_memory(user_id: str, metric: str = "all", days: int = 14) -> Dict:
    """Correlate health metrics with memory/emotional states."""
    try:
        import asyncio

        # Get health data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        metrics_to_check = ["sleep", "heart_rate", "activity"] if metric == "all" else [metric]

        health_data = {}
        for m in metrics_to_check:
            health_data[m] = asyncio.run(_get_health_data(
                user_id, m, start_date, end_date
            ))

        # Get memories from same period
        async def get_memories():
            async with database.pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT snippet, category, created_at, importance
                    FROM memory_snippets
                    WHERE user_id = $1
                      AND created_at >= $2
                      AND created_at <= $3
                      AND (metadata->>'obsolete')::boolean IS NOT TRUE
                    ORDER BY created_at DESC
                    """,
                    user_id, start_date, end_date
                )
                return [
                    {
                        "snippet": row['snippet'],
                        "category": row['category'],
                        "date": row['created_at'].isoformat(),
                        "importance": row['importance']
                    }
                    for row in rows
                ]

        memories = asyncio.run(get_memories())

        # Prepare data for AI correlation analysis
        health_summary = "\n".join([
            f"{m.upper()}: {len(health_data[m])} misurazioni"
            for m in metrics_to_check
        ])

        memories_summary = "\n".join([
            f"- {mem['date'].split('T')[0]}: {mem['snippet']} (importanza: {mem['importance']})"
            for mem in memories[:10]
        ])

        correlation_analysis = asyncio.run(_llm_analyze_health(
            f"Analizza correlazioni tra dati di salute e eventi/stati emotivi dell'utente. "
            f"Cerca pattern (es: sonno peggiora dopo eventi stressanti, attività ridotta nei periodi tristi). "
            f"Fornisci insights concreti e suggerimenti.",
            f"SALUTE (ultimi {days} giorni):\n{health_summary}\n\n"
            f"EVENTI/MEMORIE:\n{memories_summary}"
        ))

        return {
            "success": True,
            "period_days": days,
            "health_metrics_analyzed": metrics_to_check,
            "memories_count": len(memories),
            "correlation_analysis": correlation_analysis,
            "sample_health_data": {
                m: health_data[m][:3] for m in metrics_to_check
            },
            "sample_memories": memories[:3]
        }

    except Exception as e:
        logger.error(f"Error correlating health with memory: {e}")
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_wellness_score(sleep: Dict, activity: Dict, heart_rate: Dict, goals: List[Dict]) -> int:
    """Calculate overall wellness score (0-100)."""
    score = 0

    # Sleep score (30 points)
    avg_sleep = sleep.get('average_hours', 0)
    if 7 <= avg_sleep <= 9:
        score += 30
    elif 6 <= avg_sleep < 7 or 9 < avg_sleep <= 10:
        score += 20
    else:
        score += 10

    # Activity score (30 points)
    steps = activity.get('steps', 0)
    if steps >= 10000:
        score += 30
    elif steps >= 7000:
        score += 20
    elif steps >= 5000:
        score += 10

    # Heart rate score (20 points)
    resting_hr = heart_rate.get('resting_bpm', 0)
    if 60 <= resting_hr <= 80:
        score += 20
    elif 50 <= resting_hr < 60 or 80 < resting_hr <= 90:
        score += 15
    elif resting_hr > 0:
        score += 5

    # Goals progress score (20 points)
    if goals:
        avg_progress = sum(g.get('progress_pct', 0) for g in goals) / len(goals)
        score += int(avg_progress * 0.2)

    return min(score, 100)
