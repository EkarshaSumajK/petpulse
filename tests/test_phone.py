from app.utils.phone import normalize_phone


def test_ten_digit_gets_india_prefix():
    assert normalize_phone("9876543210") == "919876543210"


def test_strips_leading_zeros():
    assert normalize_phone("09876543210") == "919876543210"


def test_strips_leading_00():
    assert normalize_phone("00919876543210") == "919876543210"


def test_strips_non_digits():
    assert normalize_phone("+91 98765-43210") == "919876543210"


def test_already_has_country_code():
    assert normalize_phone("919876543210") == "919876543210"


def test_too_short_is_invalid():
    assert normalize_phone("12345") is None


def test_empty_is_invalid():
    assert normalize_phone("") is None
    assert normalize_phone(None) is None
