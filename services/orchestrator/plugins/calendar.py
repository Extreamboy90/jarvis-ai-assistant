"""
Calendar plugin - Google Calendar integration
"""

from plugins import function
from datetime import datetime, timedelta
import os
from typing import Optional

# Le credenziali verranno configurate tramite variabili d'ambiente
# GOOGLE_CALENDAR_CREDENTIALS_PATH - path al file credentials.json

@function(
    name="list_events",
    description="List upcoming calendar events for a specified time range",
    parameters={
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "Number of days ahead to look for events (default: 7)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to return (default: 10)"
            }
        },
        "required": []
    }
)
def list_events(days_ahead: int = 7, max_results: int = 10):
    """List upcoming calendar events"""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import pickle

        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

        creds = None
        token_path = '/app/calendar_token.pickle'
        credentials_path = os.getenv('GOOGLE_CALENDAR_CREDENTIALS_PATH', '/app/credentials.json')

        # Check if token exists
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        # If no valid credentials, return error message
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
            else:
                return {
                    "success": False,
                    "error": "Calendar not configured. Please run setup_calendar first."
                }

        # Build service
        service = build('calendar', 'v3', credentials=creds)

        # Get events
        now = datetime.utcnow().isoformat() + 'Z'
        end_date = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=end_date,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "success": True,
                "events": [],
                "message": "No upcoming events found"
            }

        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))

            formatted_events.append({
                "summary": event.get('summary', 'No title'),
                "start": start,
                "end": end,
                "location": event.get('location', ''),
                "description": event.get('description', '')
            })

        return {
            "success": True,
            "events": formatted_events,
            "count": len(formatted_events)
        }

    except ImportError:
        return {
            "success": False,
            "error": "Google Calendar libraries not installed. Run: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Calendar error: {str(e)}"
        }


@function(
    name="create_event",
    description="Create a new calendar event",
    parameters={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Event title/summary"
            },
            "start_time": {
                "type": "string",
                "description": "Start time in ISO format (YYYY-MM-DDTHH:MM:SS)"
            },
            "end_time": {
                "type": "string",
                "description": "End time in ISO format (YYYY-MM-DDTHH:MM:SS)"
            },
            "description": {
                "type": "string",
                "description": "Event description (optional)"
            },
            "location": {
                "type": "string",
                "description": "Event location (optional)"
            }
        },
        "required": ["summary", "start_time", "end_time"]
    }
)
def create_event(summary: str, start_time: str, end_time: str,
                 description: str = "", location: str = ""):
    """Create a new calendar event"""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import pickle

        token_path = '/app/calendar_token.pickle'

        if not os.path.exists(token_path):
            return {
                "success": False,
                "error": "Calendar not configured. Please run setup_calendar first."
            }

        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

        service = build('calendar', 'v3', credentials=creds)

        event = {
            'summary': summary,
            'location': location,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'Europe/Rome',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Europe/Rome',
            },
        }

        created_event = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        return {
            "success": True,
            "event_id": created_event.get('id'),
            "link": created_event.get('htmlLink'),
            "message": f"Event '{summary}' created successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to create event: {str(e)}"
        }


@function(
    name="find_free_slots",
    description="Find free time slots in the calendar",
    parameters={
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "Number of days ahead to search (default: 7)"
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Required duration in minutes (default: 60)"
            },
            "work_hours_only": {
                "type": "boolean",
                "description": "Only search during work hours 9-18 (default: true)"
            }
        },
        "required": []
    }
)
def find_free_slots(days_ahead: int = 7, duration_minutes: int = 60,
                    work_hours_only: bool = True):
    """Find available free time slots"""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import pickle
        from datetime import datetime, timedelta

        token_path = '/app/calendar_token.pickle'

        if not os.path.exists(token_path):
            return {
                "success": False,
                "error": "Calendar not configured."
            }

        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

        service = build('calendar', 'v3', credentials=creds)

        # Get busy times
        now = datetime.utcnow()
        end_date = now + timedelta(days=days_ahead)

        body = {
            "timeMin": now.isoformat() + 'Z',
            "timeMax": end_date.isoformat() + 'Z',
            "items": [{"id": "primary"}]
        }

        freebusy_result = service.freebusy().query(body=body).execute()
        busy_times = freebusy_result['calendars']['primary']['busy']

        # Find free slots
        free_slots = []
        current = now

        while current < end_date and len(free_slots) < 10:
            if work_hours_only:
                if current.hour < 9:
                    current = current.replace(hour=9, minute=0)
                elif current.hour >= 18:
                    current = (current + timedelta(days=1)).replace(hour=9, minute=0)
                    continue

            slot_end = current + timedelta(minutes=duration_minutes)

            # Check if slot is free
            is_free = True
            for busy in busy_times:
                busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))

                if (current < busy_end and slot_end > busy_start):
                    is_free = False
                    current = busy_end
                    break

            if is_free:
                free_slots.append({
                    "start": current.strftime("%Y-%m-%d %H:%M"),
                    "end": slot_end.strftime("%Y-%m-%d %H:%M"),
                    "day": current.strftime("%A")
                })
                current += timedelta(minutes=30)  # Move forward

        return {
            "success": True,
            "free_slots": free_slots,
            "duration_minutes": duration_minutes
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error finding free slots: {str(e)}"
        }


@function(
    name="get_today_schedule_summary",
    description="Get a concise summary of today's calendar events (for daily briefing)",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_today_schedule_summary():
    """Get today's calendar summary for Mission Control dashboard"""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import pickle

        token_path = '/app/calendar_token.pickle'

        if not os.path.exists(token_path):
            return {
                "success": False,
                "error": "Calendar not configured"
            }

        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

        service = build('calendar', 'v3', credentials=creds)

        # Get today's events
        from datetime import datetime
        today_start = datetime.now().replace(hour=0, minute=0, second=0).isoformat() + 'Z'
        today_end = datetime.now().replace(hour=23, minute=59, second=59).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=today_start,
            timeMax=today_end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return {
                "success": True,
                "events": [],
                "total_events": 0,
                "summary": "Nessun evento in calendario oggi"
            }

        # Format events
        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            formatted_events.append({
                "summary": event.get('summary', 'Evento senza titolo'),
                "start": start,
                "location": event.get('location', ''),
                "description": event.get('description', '')[:100]  # Truncate description
            })

        # Generate summary text
        count = len(formatted_events)
        if count == 1:
            summary = f"1 evento oggi: {formatted_events[0]['summary']}"
        else:
            summary = f"{count} eventi oggi"

        return {
            "success": True,
            "events": formatted_events,
            "total_events": count,
            "summary": summary
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error getting today's schedule: {str(e)}"
        }
