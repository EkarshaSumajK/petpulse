"""Builds a short pet-background note fed into media analysis prompts
(image/video/audio) so an ambiguous sound or sign gets interpreted with
actual awareness of the pet's known history — e.g. recognizing labored
breathing as consistent with a documented history of asthma, instead of
defaulting to a generic "possibly panting" with no context at all. This is
background only: the analysis prompts are still told never to diagnose or
invent findings from it, only to use it to sharpen what's actually
observed."""

from typing import Any


def build_pet_background_note(pet: dict[str, Any] | None) -> str:
    if not pet:
        return ""

    parts = []
    if pet.get("species"):
        parts.append(f"species={pet['species']}")
    if pet.get("breed"):
        parts.append(f"breed={pet['breed']}")
    if pet.get("chronic_conditions"):
        parts.append(f"known chronic conditions on file: {pet['chronic_conditions']}")
    if pet.get("allergies"):
        parts.append(f"known allergies on file: {pet['allergies']}")

    if not parts:
        return ""

    return (
        "Background on this pet, for context only — never diagnose or invent findings from this alone, "
        "only use it to sharpen what you actually observe/hear: " + "; ".join(parts) + ".\n"
    )
