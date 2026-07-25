"""Supabase client + a handful of thin, reused repo helpers.

Uses the official `supabase-py` client (service-role key) against the exact
same 24-table schema the n8n workflows use — no migration. The
`pets?select=*,pet_members!inner()&pet_members.profile_id=eq.{id}` join
pattern (spec §2, duplicated raw-REST in 5+ n8n workflows) is the real
multi-owner access-control mechanism throughout the system; it's
consolidated here as `get_pets_for_profile` instead of being re-typed at
every call site.
"""

from typing import Any

from supabase import Client, create_client

from app.config import Settings


def make_supabase_client(settings: Settings) -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_pets_for_profile(client: Client, profile_id: str) -> list[dict[str, Any]]:
    """A pet is visible to a profile iff a `pet_members` row links them —
    this is the actual access-control boundary (owner, family, caregiver,
    vet), not `pets.profile_id` alone."""
    resp = (
        client.table("pets")
        .select("*, pet_members!inner(profile_id, role, is_primary)")
        .eq("pet_members.profile_id", profile_id)
        .eq("is_active", True)
        .order("created_at")
        .execute()
    )
    return resp.data or []


def get_profile_by_phone(client: Client, phone_number: str) -> dict[str, Any] | None:
    resp = client.table("profiles").select("*").eq("phone_number", phone_number).limit(1).execute()
    return resp.data[0] if resp.data else None


def get_or_create_profile(client: Client, phone_number: str, sender_name: str) -> dict[str, Any]:
    existing = get_profile_by_phone(client, phone_number)
    if existing:
        return existing
    resp = (
        client.table("profiles")
        .insert({"phone_number": phone_number, "full_name": sender_name, "role": "customer"})
        .execute()
    )
    return resp.data[0]


def claim_message_id(client: Client, message_id: str) -> bool:
    """Dedup: attempt to INSERT into `processed_messages` (PK=message_id).
    Returns False (already processed) on a unique-violation, True on a
    fresh claim. Mirrors n8n's `Claim Message Id` -> `Duplicate - Skip`."""
    try:
        client.table("processed_messages").insert({"message_id": message_id}).execute()
        return True
    except Exception as exc:  # postgrest raises on unique-violation (23505)
        if "23505" in str(exc) or "duplicate key" in str(exc).lower():
            return False
        raise


def sign_storage_url(client: Client, bucket: str, object_path: str, expires_in: int = 3600) -> str:
    result = client.storage.from_(bucket).create_signed_url(object_path, expires_in)
    return result["signedURL"] if "signedURL" in result else result.get("signedUrl", "")


def upload_to_storage(client: Client, bucket: str, object_path: str, data: bytes, mime_type: str) -> None:
    client.storage.from_(bucket).upload(
        object_path, data, file_options={"content-type": mime_type, "upsert": "true"}
    )
