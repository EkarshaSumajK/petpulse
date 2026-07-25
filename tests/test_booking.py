"""Reproduces and verifies the fix for a real reported bug: a customer with
an open vet-choice request for one pet was completely blocked from
starting a booking for a DIFFERENT pet, because the "already have an open
booking" guard only checked profile_id, never pet_id. Also covers the
naive-timestamp bug (a proposed/preferred time with no UTC offset landing
5.5 hours off once stored)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.tools.booking import _normalize_to_ist, propose_time, request_doctor_session
from app.availability.slots import IST
from tests.fake_supabase import FakeSupabaseClient


def _make_ctx(supabase=None):
    whatsapp = SimpleNamespace(send_interactive_list=AsyncMock(), send_interactive_buttons=AsyncMock(), send_text=AsyncMock())
    return SimpleNamespace(supabase=supabase or FakeSupabaseClient(), whatsapp=whatsapp, settings=object())


def _make_agent_ctx(pets):
    return SimpleNamespace(profile={"id": "profile-1", "phone_number": "919876543210"}, pets=pets)


@pytest.mark.asyncio
async def test_pending_request_for_one_pet_does_not_block_a_different_pet():
    pet_a = {"id": "pet-a", "name": "Max"}
    pet_b = {"id": "pet-b", "name": "Luna"}
    supabase = FakeSupabaseClient(
        initial={
            "doctor_sessions": [
                {
                    "id": "session-a",
                    "profile_id": "profile-1",
                    "pet_id": "pet-a",
                    "doctor_phone": "pending_doctor_choice",
                    "status": "pending",
                }
            ],
            "profiles": [{"id": "vet-1", "role": "vet", "phone_number": "919000000001", "full_name": "Dr. Rao"}],
        }
    )
    ctx = _make_ctx(supabase)
    agent_ctx = _make_agent_ctx(pets=[pet_a, pet_b])

    result = await request_doctor_session(ctx, agent_ctx, pet_name="Luna", case_summary="routine checkup")

    assert result["success"] is True
    assert result["mode"] == "doctor_catalogue_sent"
    # A brand new session for pet_b must have been created, not blocked by pet_a's.
    sessions_for_luna = [s for s in supabase.rows("doctor_sessions") if s.get("pet_id") == "pet-b"]
    assert len(sessions_for_luna) == 1
    ctx.whatsapp.send_interactive_list.assert_awaited_once()


@pytest.mark.asyncio
async def test_pending_request_for_the_same_pet_resends_the_list_with_session_id():
    pet_a = {"id": "pet-a", "name": "Max"}
    supabase = FakeSupabaseClient(
        initial={
            "doctor_sessions": [
                {
                    "id": "session-a",
                    "profile_id": "profile-1",
                    "pet_id": "pet-a",
                    "doctor_phone": "pending_doctor_choice",
                    "status": "pending",
                }
            ],
            "profiles": [{"id": "vet-1", "role": "vet", "phone_number": "919000000001", "full_name": "Dr. Rao"}],
        }
    )
    ctx = _make_ctx(supabase)
    agent_ctx = _make_agent_ctx(pets=[pet_a])

    result = await request_doctor_session(ctx, agent_ctx, pet_name="Max", case_summary="routine checkup")

    assert result["success"] is True
    assert result["mode"] == "doctor_catalogue_sent"
    assert result["session_id"] == "session-a"
    # No duplicate session row created for the same pet.
    sessions_for_max = [s for s in supabase.rows("doctor_sessions") if s.get("pet_id") == "pet-a"]
    assert len(sessions_for_max) == 1
    ctx.whatsapp.send_interactive_list.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_session_resolves_pet_id_instead_of_dropping_it():
    pet_a = {"id": "pet-a", "name": "Max"}
    supabase = FakeSupabaseClient(
        initial={"profiles": [{"id": "vet-1", "role": "vet", "phone_number": "919000000001", "full_name": "Dr. Rao"}]}
    )
    ctx = _make_ctx(supabase)
    agent_ctx = _make_agent_ctx(pets=[pet_a])

    result = await request_doctor_session(ctx, agent_ctx, pet_name="Max", case_summary="limping")

    assert result["success"] is True
    session = supabase.rows("doctor_sessions")[0]
    assert session["pet_id"] == "pet-a"


def test_normalize_to_ist_adds_offset_when_missing():
    normalized = _normalize_to_ist("2026-07-28T14:00:00")
    dt = datetime.fromisoformat(normalized)
    assert dt.tzinfo is not None
    assert dt.utcoffset() == IST.utcoffset(None)
    assert dt.hour == 14  # stays 14:00 IST, not reinterpreted as UTC


def test_normalize_to_ist_preserves_explicit_offset():
    normalized = _normalize_to_ist("2026-07-28T14:00:00+05:30")
    assert normalized == "2026-07-28T14:00:00+05:30"


def test_normalize_to_ist_rejects_garbage():
    assert _normalize_to_ist("not a time") is None
    assert _normalize_to_ist("") is None


@pytest.mark.asyncio
async def test_propose_time_stores_offset_aware_timestamp():
    supabase = FakeSupabaseClient(
        initial={
            "doctor_sessions": [{"id": "session-a", "profile_id": "profile-1", "doctor_phone": "919000000001"}],
            "profiles": [{"id": "profile-1", "phone_number": "919876543210", "full_name": "Jane"}],
        }
    )
    ctx = _make_ctx(supabase)
    agent_ctx = _make_agent_ctx(pets=[])

    result = await propose_time(ctx, agent_ctx, session_id="session-a", proposed_time="2026-07-28T14:00:00", proposed_by="customer")

    assert result["success"] is True
    session = supabase.rows("doctor_sessions")[0]
    assert "+05:30" in session["preferred_time"]
