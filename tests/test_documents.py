"""Covers the pure vaccination-line formatting used by get_pet_passport —
must surface every field actually on file (manufacturer, batch/lot number,
next-due date), not just name + date, and flag overdue vaccinations."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.tools.documents import _format_vaccination_line, file_document, send_pet_document

TODAY = "2026-07-26"


def test_full_record_includes_manufacturer_batch_and_next_due():
    vax = {
        "vaccine_name": "Rabies",
        "date_administered": "2025-07-01",
        "manufacturer": "Zoetis",
        "batch_number": "LOT-4471B",
        "next_due_date": "2026-07-01",
    }
    line, overdue = _format_vaccination_line(vax, TODAY)
    assert "Rabies" in line
    assert "2025-07-01" in line
    assert "Zoetis" in line
    assert "Batch/Lot: LOT-4471B" in line
    assert "Next due: 2026-07-01" in line
    assert overdue is True
    assert "(OVERDUE)" in line


def test_not_yet_due_is_not_flagged_overdue():
    vax = {
        "vaccine_name": "DHPP",
        "date_administered": "2026-06-01",
        "next_due_date": "2027-06-01",
    }
    line, overdue = _format_vaccination_line(vax, TODAY)
    assert overdue is False
    assert "(OVERDUE)" not in line
    assert "Next due: 2027-06-01" in line


def test_missing_optional_fields_are_omitted_not_blank():
    vax = {"vaccine_name": "Bordetella", "date_administered": "2026-01-01"}
    line, overdue = _format_vaccination_line(vax, TODAY)
    assert overdue is False
    assert "Batch/Lot" not in line
    assert "Next due" not in line
    assert line == "- Bordetella — 2026-01-01"


def _pets_with_a_name_collision_across_two_owners():
    return [
        {"id": "b1", "name": "Bobby", "owner_name": "Abhilash", "owner_phone": "919000000001"},
        {"id": "b2", "name": "Bobby", "owner_name": "Priya", "owner_phone": "919000000002"},
    ]


@pytest.mark.asyncio
async def test_file_document_surfaces_owner_disambiguation_instead_of_guessing():
    """Reproduces a real reported bug: a vet's patient list spans multiple
    unrelated households, so "pet name bobby" matched TWO different
    owners' pets, and the document silently went to the wrong one. The
    tool must now hand the LLM the candidates (with owner_name/owner_phone)
    and refuse to pick — never file to a guessed pet."""
    agent_ctx = SimpleNamespace(
        pets=_pets_with_a_name_collision_across_two_owners(),
        pending_media=SimpleNamespace(document_bytes=b"fake-bytes", document_mime_type="image/jpeg", document_classification=None, media_context=""),
    )
    ctx = SimpleNamespace(supabase=None, whatsapp=None, settings=None, openai=None)

    result = await file_document(ctx, agent_ctx, pet_name="bobby")

    assert result["success"] is False
    assert result["error"] == "ambiguous_pet"
    assert {c["owner_name"] for c in result["candidates"]} == {"Abhilash", "Priya"}
    assert "owner_name" in result["instruction_to_llm"]


@pytest.mark.asyncio
async def test_file_document_files_to_the_exact_pet_id_once_disambiguated(monkeypatch):
    from tests.fake_supabase import FakeSupabaseClient

    supabase = FakeSupabaseClient()
    agent_ctx = SimpleNamespace(
        pets=_pets_with_a_name_collision_across_two_owners(),
        pending_media=SimpleNamespace(
            document_bytes=b"fake-bytes", document_mime_type="image/jpeg", document_classification=None, media_context="vaccination card",
        ),
        profile={"id": "vet-1"},
    )
    ctx = SimpleNamespace(supabase=supabase, whatsapp=None, settings=None, openai=AsyncMock())

    monkeypatch.setattr("app.agent.tools.documents.upload_to_storage", lambda *a, **k: None)
    monkeypatch.setattr("app.agent.tools.documents.json_completion", AsyncMock(return_value='{"record_kind": "none"}'))

    result = await file_document(ctx, agent_ctx, pet_id="b1", document_type="Vaccination Certificate")

    assert result["success"] is True
    assert result["pet_name"] == "Bobby"
    doc = supabase.rows("documents")[0]
    assert doc["pet_id"] == "b1"


@pytest.mark.asyncio
async def test_send_pet_document_surfaces_owner_disambiguation_instead_of_guessing():
    agent_ctx = SimpleNamespace(pets=_pets_with_a_name_collision_across_two_owners())
    ctx = SimpleNamespace(supabase=None, whatsapp=None, settings=None, openai=None)

    result = await send_pet_document(ctx, agent_ctx, pet_name="bobby")

    assert result["success"] is False
    assert result["error"] == "ambiguous_pet"
    assert {c["owner_name"] for c in result["candidates"]} == {"Abhilash", "Priya"}
