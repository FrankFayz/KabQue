"""Shared auth helpers for KabQue access rules."""

from .models import MAIN_ADMIN_USERNAME_MARKER, username_is_main_admin

KAB_EMAIL_DOMAIN = "kab.ac.ug"

# Re-export for callers
__all__ = [
    "KAB_EMAIL_DOMAIN",
    "MAIN_ADMIN_USERNAME_MARKER",
    "normalize_email",
    "is_kab_university_email",
    "kab_email_error_message",
    "username_is_main_admin",
]


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_kab_university_email(email: str) -> bool:
    email = normalize_email(email)
    return bool(email) and email.endswith(f"@{KAB_EMAIL_DOMAIN}")


def kab_email_error_message() -> str:
    return "Access not granted."
