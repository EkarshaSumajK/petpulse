import re


def normalize_phone(raw: str) -> str | None:
    """Port of the Add Pet Member phone-normalization logic (spec §3.8).

    India-only assumption, carried over from the live n8n system: a bare
    10-digit number is assumed to be a local Indian mobile number and gets
    '91' prepended. Flagged here rather than fixed, since fixing it is a
    product decision (multi-country support), not a porting bug.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    digits = re.sub(r"^00", "", digits)
    digits = re.sub(r"^0+", "", digits)
    if len(digits) == 10:
        digits = "91" + digits
    if len(digits) < 10 or len(digits) > 15:
        return None
    return digits
