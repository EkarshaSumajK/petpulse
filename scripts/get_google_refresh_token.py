"""One-time interactive script to obtain a Google OAuth2 refresh token for
Calendar access — run this LOCALLY (needs a real browser), not on a server.

Why this exists: Calendar bookings need to auto-generate a Google Meet link
via conferenceData, which a bare GCP service account cannot do (confirmed
live: "Invalid conference type value") — Meet link creation requires either
a Google Workspace account with Meet enabled, or a real user-authenticated
OAuth2 session. This script performs that one-time user login and prints a
refresh token that never expires (unless revoked), so the deployed app can
keep creating Calendar events + Meet links without further interaction.

Setup (one time, in Google Cloud Console — same project the existing
service account already lives in is fine, or a new one):
  1. APIs & Services > Enabled APIs > enable "Google Calendar API" if not
     already enabled (it should be, the service account already used it).
  2. APIs & Services > OAuth consent screen > configure it (External is
     fine for testing; add yourself as a test user if it's in "Testing"
     publishing status).
  3. APIs & Services > Credentials > Create Credentials > OAuth client ID
     > Application type "Desktop app" > any name > Create.
  4. Download the client ID/secret (or just copy them from the console) and
     pass them as arguments below, or paste into the CLIENT_ID/CLIENT_SECRET
     constants.

Usage:
  pip install google-auth-oauthlib   # if not already installed
  python scripts/get_google_refresh_token.py

This opens a browser window — log in with whichever Google account should
own the calendar (its "primary" calendar is what GOOGLE_CALENDAR_ID=primary
will point at). After granting access, the refresh token prints to the
terminal — put it in .env as GOOGLE_CALENDAR_REFRESH_TOKEN, along with
GOOGLE_CALENDAR_CLIENT_ID/GOOGLE_CALENDAR_CLIENT_SECRET from step 3/4.
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/get_google_refresh_token.py <client_id> <client_secret>")
        sys.exit(1)

    client_id, client_secret = sys.argv[1], sys.argv[2]
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # access_type=offline + prompt=consent is required to force Google to
    # actually issue a refresh_token (it's silently omitted on repeat
    # consents otherwise).
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    print("\n--- Success ---")
    print(f"GOOGLE_CALENDAR_CLIENT_ID={client_id}")
    print(f"GOOGLE_CALENDAR_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_CALENDAR_REFRESH_TOKEN={creds.refresh_token}")
    print("\nPaste the three lines above into .env (and your deployment platform's env vars).")


if __name__ == "__main__":
    main()
