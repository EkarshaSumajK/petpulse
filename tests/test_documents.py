"""Covers the pure vaccination-line formatting used by get_pet_passport —
must surface every field actually on file (manufacturer, batch/lot number,
next-due date), not just name + date, and flag overdue vaccinations."""

from app.agent.tools.documents import _format_vaccination_line

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
