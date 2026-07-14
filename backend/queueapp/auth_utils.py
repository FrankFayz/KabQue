"""Shared auth helpers for KabQue access rules."""

from django.contrib.auth import get_user_model

from .models import MAIN_ADMIN_USERNAME_MARKER, username_is_main_admin
from .phones import normalize_phone

KAB_EMAIL_DOMAIN = "kab.ac.ug"

# Re-export for callers
__all__ = [
    "KAB_EMAIL_DOMAIN",
    "MAIN_ADMIN_USERNAME_MARKER",
    "normalize_email",
    "is_kab_university_email",
    "kab_email_error_message",
    "username_is_main_admin",
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
    # Also catch legacy un-normalized duplicates of the same number
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
