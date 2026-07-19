"""Password reset via emailed one-time codes (Option A)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .auth_utils import (
    is_kab_university_email,
    main_admin_contact_email,
    normalize_email,
    normalize_registration_number,
    parse_main_admin_identifier,
    username_is_main_admin,
)
from .email_async import send_email_in_background
from .models import StudentProfile

User = get_user_model()

CODE_TTL_MINUTES = 15
RESEND_COOLDOWN_SECONDS = 60
MAX_VERIFY_ATTEMPTS = 5
GENERIC_OK = (
    "If an account exists and can receive email, a reset code has been sent. "
    "Check your inbox."
)


def _hash_code(code: str) -> str:
    material = f"{settings.SECRET_KEY}:kabque-pw-reset:{code.strip()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def generate_reset_code(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def resolve_reset_target(identifier: str) -> tuple[object | None, str]:
    """
    Resolve (user, destination_email) for a forgot-password identifier.
    Returns (None, '') when not eligible — callers still return GENERIC_OK.
    """
    raw = (identifier or "").strip()
    if not raw:
        return None, ""

    # Main Admin: name@kab.ac.ug#@admin@#
    if username_is_main_admin(raw):
        parsed = parse_main_admin_identifier(raw)
        if not parsed:
            return None, ""
        username, contact = parsed
        user = User.objects.filter(username__iexact=username).first()
        if user is None or not user.is_main_admin:
            return None, ""
        if not user.is_active:
            return None, ""
        email = main_admin_contact_email(user) or contact
        if not is_kab_university_email(email):
            return None, ""
        return user, email

    # Email identifier (supervisor kab mail, Main Admin contact, or student profile email)
    if "@" in raw:
        email = normalize_email(raw)
        user = User.objects.filter(email__iexact=email).first()
        if user is None or not user.is_active:
            return None, ""
        if user.is_main_admin:
            # Main Admin must use email#@admin@# — never bare Kabale email
            return None, ""
        if user.role == User.Role.ADMIN or user.is_staff:
            if not is_kab_university_email(email):
                return None, ""
            return user, email
        # Fresher: any email saved on their profile
        if user.role == User.Role.STUDENT and email:
            return user, email
        return None, ""

    # Student registration number
    reg = normalize_registration_number(raw) or raw.strip().upper()
    profile = (
        StudentProfile.objects.filter(registration_number__iexact=reg)
        .select_related("user")
        .first()
    )
    if profile is None:
        return None, ""
    user = profile.user
    if not user.is_active:
        return None, ""
    email = normalize_email(user.email or "")
    if not email or "@" not in email:
        return None, ""
    return user, email


def can_resend_reset_code(user) -> tuple[bool, str]:
    expires = getattr(user, "password_reset_expires_at", None)
    if expires:
        issued_at = expires - timedelta(minutes=CODE_TTL_MINUTES)
        wait = RESEND_COOLDOWN_SECONDS - (timezone.now() - issued_at).total_seconds()
        if wait > 0:
            return False, f"Wait {int(wait)} seconds before requesting another code."
    return True, ""


def issue_password_reset_code(user, destination_email: str) -> tuple[bool, str]:
    """
    Store hashed OTP and email it. Returns (ok, error_message).

    Uses password_reset_* fields only (never email_verification_*).
    Clears any active signup-verification code so OTPs never mix purposes.
    """
    code = generate_reset_code()
    user.password_reset_code_hash = _hash_code(code)
    user.password_reset_expires_at = timezone.now() + timedelta(minutes=CODE_TTL_MINUTES)
    user.password_reset_attempts = 0
    # Clear signup OTP channel (separate store — explicit wipe avoids confusion)
    user.email_verification_code = ""
    user.email_verification_expires_at = None
    user.email_verification_attempts = 0
    user.save(
        update_fields=[
            "password_reset_code_hash",
            "password_reset_expires_at",
            "password_reset_attempts",
            "email_verification_code",
            "email_verification_expires_at",
            "email_verification_attempts",
        ]
    )

    subject = "KabQue: password reset code"
    body = (
        f"You requested a password reset for KabQue.\n\n"
        f"Your reset code is: {code}\n\n"
        f"Enter this code in KabQue within {CODE_TTL_MINUTES} minutes, then choose "
        f"a new password.\n\n"
        f"If you did not request this, ignore this email. Your password will stay "
        f"the same.\n\n"
        f"— KabQue / Kabale University"
    )
    send_email_in_background(destination_email, subject, body)
    return True, ""


def clear_password_reset(user) -> None:
    user.password_reset_code_hash = ""
    user.password_reset_expires_at = None
    user.password_reset_attempts = 0
    user.save(
        update_fields=[
            "password_reset_code_hash",
            "password_reset_expires_at",
            "password_reset_attempts",
        ]
    )


def verify_and_set_password(user, raw_code: str, new_password: str) -> tuple[bool, str]:
    code = "".join(ch for ch in (raw_code or "") if ch.isdigit())
    if len(code) != 6:
        return False, "Enter the 6-digit code from your email."

    if not (new_password or "").strip() or len(new_password) < 6:
        return False, "Password must be at least 6 characters."

    if not user.password_reset_code_hash or not user.password_reset_expires_at:
        return False, "No reset code is active. Request a new code."

    if timezone.now() > user.password_reset_expires_at:
        return False, "This code has expired. Request a new reset code."

    if user.password_reset_attempts >= MAX_VERIFY_ATTEMPTS:
        return False, "Too many incorrect attempts. Request a new reset code."

    if _hash_code(code) != user.password_reset_code_hash:
        user.password_reset_attempts = int(user.password_reset_attempts or 0) + 1
        user.save(update_fields=["password_reset_attempts"])
        left = MAX_VERIFY_ATTEMPTS - user.password_reset_attempts
        if left <= 0:
            return False, "Too many incorrect attempts. Request a new reset code."
        return False, f"Incorrect code. {left} attempt{'s' if left != 1 else ''} left."

    user.set_password(new_password)
    user.password_reset_code_hash = ""
    user.password_reset_expires_at = None
    user.password_reset_attempts = 0
    user.save(
        update_fields=[
            "password",
            "password_reset_code_hash",
            "password_reset_expires_at",
            "password_reset_attempts",
        ]
    )
    return True, "Password updated. You can sign in with your new password."
