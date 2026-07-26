"""Google Calendar client — single shared calendar for ALL vets (spec §2's
`CustResp - Compute Doctor Slots` note: this is a real simplification in
the live system, ported as-is rather than fixed; real per-vet availability
would need per-vet calendars or a `doctor_id` column on a proper
availability table).

Auth is OAuth2 user credentials (refresh-token flow), not a service
account — confirmed live that a bare GCP service account cannot generate
Google Meet links via conferenceData (`Invalid conference type value`,
since Meet auto-creation needs either a Google Workspace account with Meet
enabled, or a real user-authenticated session). A personal/work Google
account authenticated via OAuth2 does not have this restriction. Generate
the refresh token once with `scripts/get_google_refresh_token.py` (see
README) and set GOOGLE_CALENDAR_CLIENT_ID/SECRET/REFRESH_TOKEN — whichever
account you authenticate as owns the calendar `google_calendar_id` points
at ("primary" = that account's own default calendar).
"""

from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import Settings

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service(settings: Settings):
    creds = Credentials(
        token=None,
        refresh_token=settings.google_calendar_refresh_token,
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=CALENDAR_SCOPES,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_busy_events(settings: Settings, time_min: datetime, time_max: datetime) -> list[dict[str, Any]]:
    service = _get_service(settings)
    resp = (
        service.events()
        .list(
            calendarId=settings.google_calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return resp.get("items", [])


def create_event_with_meet(
    settings: Settings,
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    service = _get_service(settings)
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "conferenceData": {
            "createRequest": {
                "requestId": f"petpulse-{start.timestamp()}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }
    created = (
        service.events()
        .insert(calendarId=settings.google_calendar_id, body=event, conferenceDataVersion=1)
        .execute()
    )
    return created


def extract_meet_link(event: dict[str, Any]) -> str | None:
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    for entry_point in event.get("conferenceData", {}).get("entryPoints", []):
        if entry_point.get("entryPointType") == "video":
            return entry_point.get("uri")
    return None
