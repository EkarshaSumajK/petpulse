"""Covers _attach_owner_info — the piece that lets a vet's cross-household
patient list carry each pet's actual owner name/phone, so the agent (not
code) can tell two same-named pets from different owners apart."""

from app.integrations.supabase_client import _attach_owner_info
from tests.fake_supabase import FakeSupabaseClient


def test_attach_owner_info_fills_in_each_pets_primary_owner():
    supabase = FakeSupabaseClient(
        initial={
            "pet_members": [
                {"pet_id": "b1", "profile_id": "owner-1", "is_primary": True},
                {"pet_id": "b1", "profile_id": "vet-1", "is_primary": False},
                {"pet_id": "b2", "profile_id": "owner-2", "is_primary": True},
            ],
            "profiles": [
                {"id": "owner-1", "full_name": "Abhilash", "phone_number": "919000000001"},
                {"id": "owner-2", "full_name": "Priya", "phone_number": "919000000002"},
                {"id": "vet-1", "full_name": "Dr. Rao", "phone_number": "919111111111"},
            ],
        }
    )
    pets = [{"id": "b1", "name": "Bobby"}, {"id": "b2", "name": "Bobby"}]

    _attach_owner_info(supabase, pets)

    by_id = {p["id"]: p for p in pets}
    assert by_id["b1"]["owner_name"] == "Abhilash"
    assert by_id["b1"]["owner_phone"] == "919000000001"
    assert by_id["b2"]["owner_name"] == "Priya"
    assert by_id["b2"]["owner_phone"] == "919000000002"


def test_attach_owner_info_handles_no_pets():
    supabase = FakeSupabaseClient()
    pets = []
    _attach_owner_info(supabase, pets)  # must not raise
    assert pets == []
