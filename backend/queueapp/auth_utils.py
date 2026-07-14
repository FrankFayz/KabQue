"""Shared auth helpers for KabQue access rules."""

KAB_EMAIL_DOMAIN = "kab.ac.ug"


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_kab_university_email(email: str) -> bool:
    email = normalize_email(email)
    return bool(email) and email.endswith(f"@{KAB_EMAIL_DOMAIN}")


def kab_email_error_message() -> str:
    return "Access not granted."
