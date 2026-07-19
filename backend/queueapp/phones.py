"""East African phone numbers normalized to E.164 for MySMSGate."""

from __future__ import annotations

import re

# iso -> (dial digits, min national len, max national len)
EAST_AFRICA_COUNTRIES = (
    ("UG", "256", 9, 9),
    ("KE", "254", 9, 9),
    ("TZ", "255", 9, 9),
    ("RW", "250", 9, 9),
    ("BI", "257", 8, 8),
    ("SS", "211", 9, 9),
    ("ET", "251", 9, 9),
    ("SO", "252", 8, 9),
    ("CD", "243", 9, 9),
    ("DJ", "253", 8, 8),
    ("ER", "291", 7, 7),
)

_DIAL_BY_LENGTH = sorted(
    ((dial, mn, mx) for _, dial, mn, mx in EAST_AFRICA_COUNTRIES),
    key=lambda item: len(item[0]),
    reverse=True,
)

_KNOWN_DIALS = {dial for _, dial, _, _ in EAST_AFRICA_COUNTRIES}


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def to_sms_destination(phone: str) -> str:
    """
    Final gate for MySMSGate: always E.164 with country code (+CC…).

    Examples: +2567XXXXXXXX (UG), +2547XXXXXXXX (KE).
    Raises ValueError if the number cannot be made international.
    """
    normalized = validate_east_africa_phone(phone)
    if not normalized:
        raise ValueError("Telephone number is required for SMS notifications.")
    # Strip spaces / dashes that might sneak in from older profiles
    compact = "+" + "".join(ch for ch in normalized[1:] if ch.isdigit())
    if not re.fullmatch(r"\+[1-9]\d{7,14}", compact):
        raise ValueError(
            "Phone must include a country code (select Uganda, Kenya, etc.)."
        )
    return compact


def normalize_phone(phone: str) -> str:
    """
    Normalize to E.164 (+CC…).

    Accepts already-international numbers, 00-prefix, or Uganda local 0… / 7…
    when no country code is present (legacy profiles).
    """
    raw = (phone or "").strip()
    if not raw:
        return ""

    if raw.startswith("00"):
        raw = f"+{raw[2:]}"

    if raw.startswith("+"):
        digits = _digits(raw)
        return f"+{digits}" if digits else ""

    digits = _digits(raw)
    if not digits:
        return ""

    # Already includes a known EA country code without '+'
    for dial, mn, mx in _DIAL_BY_LENGTH:
        if digits.startswith(dial):
            national = digits[len(dial) :]
            if mn <= len(national) <= mx + 1:
                return f"+{dial}{national.lstrip('0') if national.startswith('0') else national}"

    # Uganda local formats (common campus default)
    if digits.startswith("0") and len(digits) >= 9:
        return f"+256{digits.lstrip('0')}"
    if len(digits) in (9, 10) and digits[0] in "79":
        return f"+256{digits}"

    return f"+{digits}"


def validate_east_africa_phone(phone: str) -> str:
    """
    Return normalized E.164 or raise ValueError with a user-facing message.
    Empty string is allowed (optional contact).
    """
    raw = (phone or "").strip()
    if not raw:
        return ""

    normalized = normalize_phone(raw)
    if not normalized.startswith("+"):
        raise ValueError(
            "Phone must include a country code (select Uganda, Kenya, etc.)."
        )

    digits = normalized[1:]
    matched = None
    for dial, mn, mx in _DIAL_BY_LENGTH:
        if digits.startswith(dial):
            matched = (dial, mn, mx)
            break

    if not matched:
        raise ValueError(
            "Use an East African country code (Uganda +256, Kenya +254, "
            "Tanzania +255, Rwanda +250, and neighbours)."
        )

    dial, mn, mx = matched
    national = digits[len(dial) :]
    if national.startswith("0"):
        national = national.lstrip("0")
        normalized = f"+{dial}{national}"

    if not national.isdigit() or not (mn <= len(national) <= mx):
        raise ValueError(
            f"Enter a valid mobile number for +{dial} "
            f"({mn}–{mx} digits after the country code)."
        )

    return normalized
