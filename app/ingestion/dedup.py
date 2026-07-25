"""Ports `Claim Message Id` -> `Duplicate - Skip` (spec §2): Meta retries
webhook deliveries, so every message_id is claimed exactly once via the
processed_messages PK before any further processing happens."""

from supabase import Client

from app.integrations.supabase_client import claim_message_id


def claim(client: Client, message_id: str) -> bool:
    """Returns True if this is the first time we've seen message_id."""
    return claim_message_id(client, message_id)
