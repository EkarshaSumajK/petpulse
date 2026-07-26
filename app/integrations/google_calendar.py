"""Google Calendar client — delegates to n8n's "PetPulse - Calendar Bridge"
webhook (workflow `lW0L35AEoWQAxkNl`) rather than talking to Google's
Calendar API directly.

Why: confirmed live that a bare GCP service account cannot generate Google
Meet links (`Invalid conference type value` — Meet auto-creation needs
either a Google Workspace account or a real user-authenticated OAuth
session), and running our own OAuth2 consent flow for a personal account
requires Google app verification for anything beyond a pre-approved
test-user allowlist. n8n already has a working, already-authorized Google
Calendar OAuth2 credential — the one behind the real July 24th test
bookings — so this reuses it via a small bridge workflow instead of
duplicating that authorization from scratch. The bridge is protected by a
shared secret (`CALENDAR_BRIDGE_SECRET`), not n8n's own auth, since it's a
plain webhook.
"""

from datetime import datetime
from typing import Any

import httpx

from app.config import Settings


async def _call_bridge(settings: Settings, action: str, **params: Any) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            settings.calendar_bridge_url,
            json={"secret": settings.calendar_bridge_secret, "action": action, **params},
        )
        resp.raise_for_status()
        result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"Calendar bridge action '{action}' failed: {result}")
    return result


async def list_busy_events(settings: Settings, time_min: datetime, time_max: datetime) -> list[dict[str, Any]]:
    result = await _call_bridge(settings, "list_busy", time_min=time_min.isoformat(), time_max=time_max.isoformat())
    return result.get("busy", [])


async def create_event_with_meet(
    settings: Settings,
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    return await _call_bridge(
        settings,
        "create_event",
        summary=summary,
        description=description,
        start=start.isoformat(),
        end=end.isoformat(),
    )


def extract_meet_link(event: dict[str, Any]) -> str | None:
    return event.get("meet_link")
