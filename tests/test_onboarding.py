"""Reproduces and verifies the fix for a real reported bug: registering a
new pet via several save_onboarding_field calls in one turn (name, then
species/breed/age — exactly what the system prompt tells the agent to do)
silently dropped every field after the first, because agent_ctx.pets was
loaded once at turn start and never saw the pet just created moments
earlier in the same turn."""

from types import SimpleNamespace

import pytest

from app.agent.tools.onboarding import save_onboarding_field
from tests.fake_supabase import FakeSupabaseClient


def _make_ctx():
    return SimpleNamespace(supabase=FakeSupabaseClient())


def _make_agent_ctx(pets=None):
    return SimpleNamespace(profile={"id": "profile-1", "phone_number": "919876543210"}, pets=pets if pets is not None else [])


@pytest.mark.asyncio
async def test_naming_a_new_pet_then_setting_species_in_the_same_turn_succeeds():
    ctx = _make_ctx()
    agent_ctx = _make_agent_ctx(pets=[])

    name_result = await save_onboarding_field(ctx, agent_ctx, field="pet_name", value="Max")
    assert name_result["success"] is True
    assert name_result.get("created_pet") is True

    # Same agent_ctx, same turn — species call must now be able to find "Max"
    # without a fresh build_context() reload.
    species_result = await save_onboarding_field(ctx, agent_ctx, field="species", value="dog", pet_name="Max")
    assert species_result["success"] is True
    assert species_result["savedValue"] == "Dog"

    breed_result = await save_onboarding_field(ctx, agent_ctx, field="breed", value="Labrador", pet_name="Max")
    assert breed_result["success"] is True

    stored_pet = ctx.supabase.rows("pets")[0]
    assert stored_pet["name"] == "Max"
    assert stored_pet["species"] == "Dog"
    assert stored_pet["breed"] == "Labrador"


@pytest.mark.asyncio
async def test_created_pet_is_appended_to_agent_ctx_pets_in_place():
    ctx = _make_ctx()
    agent_ctx = _make_agent_ctx(pets=[])

    await save_onboarding_field(ctx, agent_ctx, field="pet_name", value="Rex")

    assert len(agent_ctx.pets) == 1
    assert agent_ctx.pets[0]["name"] == "Rex"


@pytest.mark.asyncio
async def test_renaming_existing_pet_updates_agent_ctx_pets_in_place_too():
    ctx = _make_ctx()
    existing_pet = {"id": "pet-1", "name": "Buddy", "species": "Dog"}
    agent_ctx = _make_agent_ctx(pets=[existing_pet])
    ctx.supabase._store["pets"] = [dict(existing_pet)]

    result = await save_onboarding_field(ctx, agent_ctx, field="breed", value="Beagle", pet_name="Buddy")

    assert result["success"] is True
    assert agent_ctx.pets[0]["breed"] == "Beagle"
