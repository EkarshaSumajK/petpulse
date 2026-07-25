"""Covers build_pet_background_note — the fix for media analysis (image/
video/audio) having zero awareness of a pet's known chronic conditions,
which meant ambiguous sounds/signs (e.g. labored breathing on a pet with a
documented history of asthma) got described with no clinical context at
all."""

from app.media_pipeline.pet_context import build_pet_background_note


def test_no_pet_returns_empty_string():
    assert build_pet_background_note(None) == ""


def test_pet_with_no_relevant_fields_returns_empty_string():
    assert build_pet_background_note({"name": "Rex", "id": "1"}) == ""


def test_chronic_condition_is_included():
    note = build_pet_background_note({"species": "Dog", "breed": "Beagle", "chronic_conditions": "asthma"})
    assert "asthma" in note
    assert "species=Dog" in note
    assert "breed=Beagle" in note


def test_note_explicitly_forbids_diagnosing_from_it_alone():
    note = build_pet_background_note({"chronic_conditions": "asthma"})
    assert "never diagnose" in note.lower()


def test_allergies_included_when_present():
    note = build_pet_background_note({"allergies": "chicken, pollen"})
    assert "chicken, pollen" in note
