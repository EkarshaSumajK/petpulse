"""Ports `sYGLqwwB1Seix1Cs` — New Pet Parent Guide / `start_new_pet_parent_guide`
(spec §3.7)."""

import json
from datetime import date, datetime, timedelta
from typing import Any

from app.deps import AppContext
from app.ingestion.context import AgentContext
from app.integrations.openai_client import json_completion
from app.utils.pet_resolution import resolve_pet

GUIDE_SYSTEM_PROMPT = """You are writing a series of 4-6 short, warm WhatsApp messages welcoming a new pet \
parent and giving them personalized early-care guidance for their pet's life stage. Never state a specific \
vaccination date, dose, or medical fact as if it were on file — only give general life-stage guidance. \
Respond with strict JSON: {"life_stage": "puppy"|"kitten"|"young"|"young_adult"|"adult"|"senior"|"unknown", \
"messages": [string, ...]}"""


def _age_text(pet: dict[str, Any], age_override: str) -> str:
    dob = pet.get("date_of_birth")
    if dob:
        try:
            born = datetime.fromisoformat(dob).date()
            months = (date.today().year - born.year) * 12 + (date.today().month - born.month)
            return f"{months} months" if months < 24 else f"{months // 12} years"
        except ValueError:
            pass
    if age_override:
        return age_override
    if pet.get("age"):
        return str(pet["age"])
    return ""


async def start_new_pet_parent_guide(
    ctx: AppContext,
    agent_ctx: AgentContext,
    pet_id: str = "",
    species: str = "",
    pet_name: str = "",
    age: str = "",
    breed: str = "",
    extra_context: str = "",
) -> dict[str, Any]:
    resolution = resolve_pet(agent_ctx.pets, pet_id=pet_id, pet_name=pet_name, auto_resolve_single=True)
    pet = resolution.pet or {}
    species = species or pet.get("species", "")
    breed = breed or pet.get("breed", "")
    age_text = _age_text(pet, age)

    missing = []
    if not species:
        missing.append("species")
    if not age_text:
        missing.append("age")

    guide_row = ctx.supabase.table("new_parent_guides").insert(
        {
            "profile_id": agent_ctx.profile["id"],
            "pet_id": pet.get("id"),
            "species": species,
            "status": "awaiting_details" if missing else "generating",
        }
    ).execute().data[0]

    if missing:
        return {
            "success": True,
            "mode": "need_details",
            "missing": missing,
            "missing_text": " and ".join(missing),
            "note": "Ask conversationally for only these fields, then call save_onboarding_field then this tool again.",
        }

    user_prompt = f"Species: {species}\nBreed: {breed or 'unknown'}\nAge: {age_text}\nPet name: {pet_name or pet.get('name', 'your pet')}\nExtra context: {extra_context or 'none'}"
    try:
        raw = await json_completion(ctx.openai, ctx.settings, GUIDE_SYSTEM_PROMPT, user_prompt, reasoning_effort="medium")
        parsed = json.loads(raw)
        life_stage = parsed.get("life_stage", "unknown")
        messages = [m for m in parsed.get("messages", []) if m][:6]
    except Exception:
        life_stage = "unknown"
        messages = [f"Welcome to PetPulse! We're excited to help you take great care of {pet_name or 'your new pet'}. Feel free to ask me anything about their health, feeding, or routine."]

    phone = agent_ctx.profile["phone_number"]
    for msg in messages:
        await ctx.whatsapp.send_text(phone, msg)

    ctx.supabase.table("new_parent_guides").update({"status": "completed"}).eq("id", guide_row["id"]).execute()

    followups = [
        {
            "guide_id": guide_row["id"],
            "profile_id": agent_ctx.profile["id"],
            "followup_type": "check_in",
            "message_text": f"Just checking in — how's {pet_name or 'your pet'} settling in?",
            "due_at": (datetime.utcnow() + timedelta(days=3)).isoformat(),
        }
    ]
    if life_stage in ("puppy", "kitten", "young"):
        followups.append(
            {
                "guide_id": guide_row["id"],
                "profile_id": agent_ctx.profile["id"],
                "followup_type": "vaccination_reminder",
                "message_text": f"Reminder: check in with your vet about {pet_name or 'your pet'}'s next vaccination.",
                "due_at": (datetime.utcnow() + timedelta(days=14)).isoformat(),
            }
        )
    ctx.supabase.table("new_parent_followups").insert(followups).execute()

    return {"success": True, "mode": "new_parent_guide_sent", "life_stage": life_stage, "messages_sent": len(messages)}
