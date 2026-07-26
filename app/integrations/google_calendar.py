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

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

BRIDGE_MAX_ATTEMPTS = 3
BRIDGE_RETRY_BACKOFF_SECONDS = 1.0


async def _call_bridge(settings: Settings, action: str, **params: Any) -> dict[str, Any]:
    """Confirmed live: a single transient hiccup calling this n8n webhook (cold
    start, a slow Google Calendar API response, a dropped connection) was
    enough to throw select_doctor's whole compute_doctor_slots call, forcing
    the customer to re-tap and redo part of the booking flow. Retries only
    network-level failures and 5xx responses — a deterministic 4xx or a
    real `{"success": false}` business response (invalid_secret,
    unknown_action) is never worth retrying, so those raise immediately."""
    last_exc: Exception | None = None
    for attempt in range(1, BRIDGE_MAX_ATTEMPTS + 1):
        try:
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
        except httpx.TransportError as exc:
            last_exc = exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise
            last_exc = exc

        if attempt < BRIDGE_MAX_ATTEMPTS:
            logger.warning("Calendar bridge action '%s' failed (attempt %d/%d): %s", action, attempt, BRIDGE_MAX_ATTEMPTS, last_exc)
            await asyncio.sleep(BRIDGE_RETRY_BACKOFF_SECONDS * attempt)
    raise last_exc


async def list_busy_events(settings: Settings, time_min: datetime, time_max: datetime) -> list[dict[str, Any]]:
    result = await _call_bridge(settings, "list_busy", time_min=time_min.isoformat(), time_max=time_max.isoformat())
    return result.get("busy", [])


async def create_event_with_meet(
    settings: Settings,
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    return await _call_bridge(
        settings,
        "create_event",
        summary=summary,
        description=description,
        start=start.isoformat(),
        end=end.isoformat(),
        attendees=attendees or [],
    )


async def update_event_time(
    settings: Settings, event_id: str, start: datetime, end: datetime, attendees: list[str] | None = None
) -> dict[str, Any]:
    """Moves an EXISTING event to a new time, preserving its id/Meet link —
    used for rescheduling an already-confirmed session, so it doesn't leave
    a duplicate/orphaned calendar entry behind (confirmed live: same
    event_id and meet_link come back, only start/end change)."""
    return await _call_bridge(
        settings, "update_event", event_id=event_id, start=start.isoformat(), end=end.isoformat(), attendees=attendees or []
    )


async def delete_event(settings: Settings, event_id: str) -> None:
    await _call_bridge(settings, "delete_event", event_id=event_id)


def extract_meet_link(event: dict[str, Any]) -> str | None:
    return event.get("meet_link")
