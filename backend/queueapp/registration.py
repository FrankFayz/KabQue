"""Kabale University student registration number rules."""

from __future__ import annotations

import re

__all__ = [
    "normalize_registration_number",
    "validate_kabale_registration_number",
    "REGISTRATION_NUMBER_HINT",
]

# YYYY/A/{PROGRAMME}/{SERIAL}/F
# YYYY/A/{PROGRAMME}/{SERIAL}/G/F  (government-sponsored full-time)
_KABALE_REG_RE = re.compile(
    r"""
    ^
    (?P<year>\d{4})
    /A/
    (?P<programme>[A-Z]{1,24})
    /
    (?P<serial>\d{1,10})
    (?:/G)?
    /F
    $
    """,
    re.VERBOSE,
)

REGISTRATION_NUMBER_HINT = (
    "Use your Kabale University number, e.g. 2026/A/BBA/3000/F "
    "or 2026/A/BBA/3000/G/F (government-sponsored)."
)

_INVALID_MSG = (
    "Invalid registration number. Kabale University format is "
    "YEAR/A/PROGRAMME/SERIAL/F or YEAR/A/PROGRAMME/SERIAL/G/F "
    "(example: 2026/A/BBA/3000/F or 2026/A/BBA/3000/G/F)."
)


def normalize_registration_number(value: str) -> str:
    """Uppercase, trim, collapse spaces, keep slash separators."""
    raw = (value or "").strip().upper()
    if not raw:
        return ""
    # Allow paste with spaces around slashes: 2026 / A / BBA / 3000 / F
    raw = re.sub(r"\s*/\s*", "/", raw)
    raw = re.sub(r"\s+", "", raw)
    return raw


def validate_kabale_registration_number(value: str) -> str:
    """
    Return normalized Kabale registration number or raise ValueError.

    Structure:
      - academic year (4 digits), e.g. 2026
      - /A/  (admitted)
      - programme code (letters, length varies), e.g. BBA
      - / serial (digits, length varies), e.g. 3000
      - /F  (full-time) OR /G/F (government-sponsored full-time)
    """
    reg = normalize_registration_number(value)
    if not reg:
        raise ValueError("Registration number is required.")

    match = _KABALE_REG_RE.fullmatch(reg)
    if not match:
        raise ValueError(_INVALID_MSG)

    year = int(match.group("year"))
    if year < 2000 or year > 2100:
        raise ValueError(
            "Registration year looks invalid. Use your admission year "
            "(e.g. 2026/A/BBA/3000/F)."
        )

    return reg
