"""Shared auth helpers for KabQue access rules."""

from django.contrib.auth import get_user_model

from .models import MAIN_ADMIN_USERNAME_MARKER, username_is_main_admin
from .phones import normalize_phone
from .registration import normalize_registration_number

KAB_EMAIL_DOMAIN = "kab.ac.ug"

__all__ = [
    "KAB_EMAIL_DOMAIN",
    "MAIN_ADMIN_USERNAME_MARKER",
    "normalize_email",
    "normalize_registration_number",
    "is_kab_university_email",
    "kab_email_error_message",
    "username_is_main_admin",
    "parse_main_admin_identifier",
    "main_admin_contact_email",
    "email_already_registered",
    "phone_already_registered",
]


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_kab_university_email(email: str) -> bool:
    email = normalize_email(email)
    return bool(email) and email.endswith(f"@{KAB_EMAIL_DOMAIN}")


def kab_email_error_message() -> str:
    return "Access not granted."


def parse_main_admin_identifier(value: str) -> tuple[str, str] | None:
    """
    Main Admin login/signup must be: local@kab.ac.ug#@admin@#

    Returns (normalized_username, contact_email) or None if invalid.
    contact_email is the real inbox (marker stripped) used for password resets.
    Plain kab.ac.ug email without the marker is never accepted for Main Admin.
    """
    raw = (value or "").strip()
    if not username_is_main_admin(raw):
        return None

    marker = MAIN_ADMIN_USERNAME_MARKER
    idx = raw.find(marker)
    if idx < 0:
        return None
    email_part = normalize_email(raw[:idx])
    trailing = raw[idx + len(marker) :]
    if trailing.strip():
        # Nothing allowed after the marker
        return None
    if not is_kab_university_email(email_part):
        return None

    username = f"{email_part}{marker}"
    return username, email_part


def main_admin_contact_email(user) -> str:
    """Best inbox for a Main Admin (stored email, else parse from username)."""
    email = normalize_email(getattr(user, "email", "") or "")
    if is_kab_university_email(email):
        return email
    parsed = parse_main_admin_identifier(getattr(user, "username", "") or "")
    if parsed:
        return parsed[1]
    return ""


def email_already_registered(email: str, *, exclude_user_id=None) -> bool:
    """True if a non-empty email is already tied to another account."""
    email = normalize_email(email)
    if not email:
        return False
    User = get_user_model()
    qs = User.objects.filter(email__iexact=email)
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    return qs.exists()


def phone_already_registered(phone: str, *, exclude_user_id=None) -> bool:
    """True if a non-empty phone is already tied to another account."""
    phone = normalize_phone(phone or "")
    if not phone:
        return False
    User = get_user_model()
    qs = User.objects.filter(phone=phone)
    if exclude_user_id is not None:
        qs = qs.exclude(pk=exclude_user_id)
    if qs.exists():
        return True
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return False
    legacy = User.objects.exclude(phone="").exclude(phone=phone)
    if exclude_user_id is not None:
        legacy = legacy.exclude(pk=exclude_user_id)
    for other in legacy.only("id", "phone").iterator():
        other_norm = normalize_phone(other.phone)
        if other_norm == phone:
            return True
    return False
