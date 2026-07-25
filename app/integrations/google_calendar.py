"""Google Calendar client — single shared calendar for ALL vets (spec §2's
`CustResp - Compute Doctor Slots` note: this is a real simplification in
the live system, ported as-is rather than fixed; real per-vet availability
would need per-vet calendars or a `doctor_id` column on a proper
availability table).

Auth is a Google service account (no interactive OAuth/refresh-token
flow). For a bare service account to see/write a human-owned calendar, that
calendar must be explicitly shared with the service account's
`client_email` (Settings > Share with specific people > "Make changes to
events"); otherwise it only has its own empty calendar. `settings.
google_calendar_id` should be set to that shared calendar's ID once that's
done — defaults to "primary" (the service account's own calendar) which
works out of the box for local testing but isn't the real shared calendar.
"""

from datetime import datetime
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import Settings

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service(settings: Settings):
    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file, scopes=CALENDAR_SCOPES
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
