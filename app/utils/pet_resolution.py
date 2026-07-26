"""Pet-name resolution algorithm, consolidated from ~5 near-identical copies
scattered across the n8n workflows (spec §2, §3.1, §3.3, §3.6, §3.8).

Resolution order, used everywhere a tool needs to figure out *which* pet a
turn is about:
  1. exact `pet_id` match if one was already supplied
  2. exact case-insensitive name match
  3. substring match (name appears in message, or message appears in name)
  4. if the caller allows it and exactly one pet exists, auto-resolve to it
  5. otherwise: ambiguous (caller decides how to signal that back)
"""

from dataclasses import dataclass, field
from typing import Any

AMBIGUOUS_PET = "__AMBIGUOUS_PET__"


@dataclass
class PetResolution:
    pet: dict[str, Any] | None
    ambiguous: bool = False
    reason: str | None = None
    # Populated whenever ambiguous=True — the actual candidates that tied, so the
    # caller can hand them back to the LLM (with each pet's owner_name/owner_phone,
    # see supabase_client.get_pets_for_profile) instead of guessing which one a
    # name match meant. The LLM decides, using conversation context; this function
    # never does.
    candidates: list[dict[str, Any]] = field(default_factory=list)


def resolve_pet(
    pets: list[dict[str, Any]],
    pet_id: str | None = None,
    pet_name: str | None = None,
    auto_resolve_single: bool = True,
) -> PetResolution:
    if not pets:
        return PetResolution(pet=None, ambiguous=False, reason="no_pets_on_file")

    if pet_id and pet_id != AMBIGUOUS_PET:
        for pet in pets:
            if str(pet.get("id")) == str(pet_id):
                return PetResolution(pet=pet)

    if pet_name:
        needle = pet_name.strip().lower()
        if needle:
            # A name match must be UNIQUE to resolve automatically — e.g. a vet's
            # patient list spans many unrelated households, and two different
            # owners can easily each have a pet named the same thing. Silently
            # returning the first match risks acting on/sending data to the
            # WRONG owner's pet (a real reported bug); multiple matches must
            # come back as ambiguous with all candidates, never a guess.
            exact = [p for p in pets if (p.get("name") or "").strip().lower() == needle]
            if len(exact) == 1:
                return PetResolution(pet=exact[0])
            if len(exact) > 1:
                return PetResolution(pet=None, ambiguous=True, reason="ambiguous_pet_name", candidates=exact)

            partial = [
                p for p in pets
                if (name := (p.get("name") or "").strip().lower()) and (needle in name or name in needle)
            ]
            if len(partial) == 1:
                return PetResolution(pet=partial[0])
            if len(partial) > 1:
                return PetResolution(pet=None, ambiguous=True, reason="ambiguous_pet_name", candidates=partial)

    if auto_resolve_single and len(pets) == 1:
        return PetResolution(pet=pets[0])

    if len(pets) > 1:
        return PetResolution(pet=None, ambiguous=True, reason="ambiguous_pet", candidates=pets)

    return PetResolution(pet=None, ambiguous=False, reason="not_found")


def resolve_active_pet_from_message(
    pets: list[dict[str, Any]], message_text: str
) -> tuple[dict[str, Any] | None, bool]:
    """Ports `Prepare Existing Pet Context`'s active-pet-from-message algorithm
    (spec §2): pets sorted by created_at ascending; message tokenized on
    [^a-z0-9]+; substring match for multi-word names, token match for
    single-word names; first hit wins; else defaults to the first pet.

    Returns (pet, matched_from_message) — the bool distinguishes an
    explicit name match from the "just default to pet_list[0]" fallback.
    """
    if not pets:
        return None, False

    ordered = sorted(pets, key=lambda p: p.get("created_at") or "")
    text = (message_text or "").lower()
    tokens = set(t for t in _tokenize(text) if t)

    for pet in ordered:
        name = (pet.get("name") or "").strip().lower()
        if not name or name == "unnamed pet":
            continue
        if " " in name:
            if name in text:
                return pet, True
        elif name in tokens:
            return pet, True

    return ordered[0], False


def _tokenize(text: str) -> list[str]:
    import re

    return re.split(r"[^a-z0-9]+", text)
