#!/usr/bin/env python3
"""
Setup script for Google Calendar OAuth
Run this once to authenticate with Google Calendar
"""

import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/calendar']

def setup_calendar():
    """Setup Google Calendar authentication"""
    creds = None
    token_path = 'calendar_token.pickle'
    credentials_path = os.getenv('GOOGLE_CALENDAR_CREDENTIALS_PATH', 'credentials.json')

    if not os.path.exists(credentials_path):
        print(f"❌ Error: credentials.json not found at {credentials_path}")
        print("\nTo setup Google Calendar:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project or select existing one")
        print("3. Enable Google Calendar API")
        print("4. Create OAuth 2.0 credentials (Desktop app)")
        print("5. Download credentials.json")
        print("6. Place it in the orchestrator directory")
        return False

    # Check if token exists
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            print("Starting OAuth flow...")
            print("A browser window will open for authentication.")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
        print(f"✅ Credentials saved to {token_path}")

    print("✅ Google Calendar setup complete!")
    print("\nYou can now use calendar functions:")
    print("  - 'quali sono i miei impegni?'")
    print("  - 'crea un evento domani alle 14'")
    print("  - 'quando sono libero questa settimana?'")

    return True

if __name__ == "__main__":
    setup_calendar()
