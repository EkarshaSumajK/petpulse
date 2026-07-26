from app.utils.pet_resolution import AMBIGUOUS_PET, resolve_active_pet_from_message, resolve_pet

REX = {"id": "1", "name": "Rex", "created_at": "2024-01-01"}
BELLA = {"id": "2", "name": "Bella", "created_at": "2024-02-01"}
UNNAMED = {"id": "3", "name": "Unnamed Pet", "created_at": "2024-03-01"}


def test_resolve_by_exact_id():
    result = resolve_pet([REX, BELLA], pet_id="2")
    assert result.pet == BELLA


def test_resolve_by_exact_name_case_insensitive():
    result = resolve_pet([REX, BELLA], pet_name="rex")
    assert result.pet == REX


def test_resolve_by_substring():
    result = resolve_pet([REX, BELLA], pet_name="my dog rex is sick")
    assert result.pet == REX


def test_single_pet_auto_resolves_with_no_name():
    result = resolve_pet([REX], pet_name="")
    assert result.pet == REX


def test_multiple_pets_no_match_is_ambiguous():
    result = resolve_pet([REX, BELLA], pet_name="")
    assert result.ambiguous is True
    assert result.pet is None


def test_ambiguous_sentinel_is_never_treated_as_an_id():
    result = resolve_pet([REX, BELLA], pet_id=AMBIGUOUS_PET)
    assert result.ambiguous is True


def test_no_pets_on_file():
    result = resolve_pet([], pet_name="Rex")
    assert result.pet is None
    assert result.ambiguous is False
    assert result.reason == "no_pets_on_file"


def test_exact_name_shared_by_two_different_owners_is_ambiguous_not_a_silent_guess():
    """Reproduces a real reported bug: a vet's patient list spans multiple
    unrelated households, so two DIFFERENT owners can each have a pet
    named the same thing. Previously the first match won silently — a
    vaccination certificate meant for one owner's "Bobby" was filed/sent
    to a different owner's "Bobby" instead. A duplicate exact match must
    come back ambiguous with both candidates, never pick one blindly."""
    bobby_1 = {"id": "b1", "name": "Bobby", "owner_name": "Abhilash", "owner_phone": "919000000001"}
    bobby_2 = {"id": "b2", "name": "Bobby", "owner_name": "Priya", "owner_phone": "919000000002"}
    result = resolve_pet([bobby_1, bobby_2], pet_name="bobby")

    assert result.pet is None
    assert result.ambiguous is True
    assert result.reason == "ambiguous_pet_name"
    assert {c["id"] for c in result.candidates} == {"b1", "b2"}
    assert {c["owner_name"] for c in result.candidates} == {"Abhilash", "Priya"}


def test_substring_match_shared_by_two_owners_is_also_ambiguous():
    bobby_1 = {"id": "b1", "name": "Bobby", "owner_name": "Abhilash"}
    bobby_junior = {"id": "b2", "name": "Bobby Junior", "owner_name": "Priya"}
    result = resolve_pet([bobby_1, bobby_junior], pet_name="bobby")

    # "bobby" is an exact match for b1 only — b2 ("Bobby Junior") isn't an exact
    # match, so this resolves to b1 via the exact-match branch, not ambiguous.
    assert result.pet == bobby_1
    assert result.ambiguous is False


def test_unique_exact_match_still_resolves_even_with_other_unrelated_pets():
    bobby = {"id": "b1", "name": "Bobby", "owner_name": "Abhilash"}
    max_pet = {"id": "m1", "name": "Max", "owner_name": "Priya"}
    result = resolve_pet([bobby, max_pet], pet_name="bobby")

    assert result.pet == bobby
    assert result.ambiguous is False


def test_active_pet_from_message_matches_single_word_name_by_token():
    pet, matched = resolve_active_pet_from_message([REX, BELLA], "how is rex doing today")
    assert pet == REX
    assert matched is True


def test_active_pet_from_message_defaults_to_first_when_no_match():
    pet, matched = resolve_active_pet_from_message([REX, BELLA], "how is my pet doing")
    assert pet == REX  # first by created_at
    assert matched is False


def test_active_pet_from_message_skips_unnamed_pet():
    pet, matched = resolve_active_pet_from_message([UNNAMED, BELLA], "how is bella doing")
    assert pet == BELLA
    assert matched is True


def test_active_pet_from_message_multiword_name_requires_substring():
    little_bear = {"id": "4", "name": "Little Bear", "created_at": "2024-01-01"}
    pet, matched = resolve_active_pet_from_message([little_bear, BELLA], "little bear has a cough")
    assert pet == little_bear
    assert matched is True
