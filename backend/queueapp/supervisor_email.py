"""Account email ownership verification (signup OTP).

Uses User.email_verification_* fields only.
Never shares storage with password_reset_* (forgot-password OTPs).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.utils import timezone

from .notifications import send_email_notification

CODE_TTL_MINUTES = 30
RESEND_COOLDOWN_SECONDS = 60
MAX_VERIFY_ATTEMPTS = 5


def generate_email_code(length: int = 6) -> str:
    """Numeric code that is easy to type from email."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def _clear_password_reset_side(user) -> list[str]:
    """Drop any active forgot-password OTP so codes never mix purposes."""
    user.password_reset_code_hash = ""
    user.password_reset_expires_at = None
    user.password_reset_attempts = 0
    return [
        "password_reset_code_hash",
        "password_reset_expires_at",
        "password_reset_attempts",
    ]


def issue_email_verification_code(user) -> tuple[str, str | None]:
    """
    Create a fresh signup verification code, store it, and email it.
    Returns (code, send_error). send_error is None when delivery succeeded.
    """
    code = generate_email_code()
    user.email_verification_code = code
    user.email_verification_expires_at = timezone.now() + timedelta(
        minutes=CODE_TTL_MINUTES
    )
    user.email_verification_attempts = 0
    user.email_verified = False
    update_fields = [
        "email_verification_code",
        "email_verification_expires_at",
        "email_verification_attempts",
        "email_verified",
        *_clear_password_reset_side(user),
    ]
    user.save(update_fields=update_fields)

    if getattr(user, "is_main_admin", False):
        subject = "KabQue: verify your email"
        body = (
            f"You registered a KabQue account with this email.\n\n"
            f"Your verification code is: {code}\n\n"
            f"Enter this code in KabQue within {CODE_TTL_MINUTES} minutes to "
            f"confirm the address is yours. After that you can sign in.\n\n"
            f"If you did not register for KabQue, ignore this message.\n\n"
            f"— KabQue / Kabale University"
        )
    else:
        subject = "KabQue: verify your Kabale University email"
        body = (
            f"Dear colleague,\n\n"
            f"You registered a KabQue staff account with this email.\n\n"
            f"Your verification code is: {code}\n\n"
            f"Enter this code in KabQue within {CODE_TTL_MINUTES} minutes to confirm "
            f"the email belongs to you.\n\n"
            f"After email verification, approval is still required before you can "
            f"use the desk.\n\n"
            f"If you did not register for KabQue, ignore this message.\n\n"
            f"— KabQue / Kabale University"
        )

    ok, err = send_email_notification(user.email, subject, body)
    return code, (None if ok else (err or "Could not send verification email"))


# Backwards-compatible alias used by existing call sites
issue_supervisor_email_code = issue_email_verification_code


def can_resend_email_code(user) -> tuple[bool, str]:
    if getattr(user, "email_verified", False):
        return False, "This email is already verified."
    expires = user.email_verification_expires_at
    if expires:
        issued_at = expires - timedelta(minutes=CODE_TTL_MINUTES)
        wait = RESEND_COOLDOWN_SECONDS - (timezone.now() - issued_at).total_seconds()
        if wait > 0:
            return False, f"Wait {int(wait)} seconds before requesting another code."
    return True, ""


can_resend_supervisor_code = can_resend_email_code


def verify_email_code(user, raw_code: str) -> tuple[bool, str]:
    """
    Validate the signup verification code.
    Supervisors still need Main Admin approval after this.
    Main Admins may sign in immediately after this.
    """
    is_main = bool(getattr(user, "is_main_admin", False))

    if getattr(user, "email_verified", False):
        if is_main:
            return True, "Email already verified. You can sign in."
        return True, "Email already verified. Wait for approval to sign in."

    code = "".join(ch for ch in (raw_code or "") if ch.isdigit())
    if not code:
        return False, "Enter the verification code from your email."

    if len(code) > 8:
        code = code[:8]

    if user.email_verification_attempts >= MAX_VERIFY_ATTEMPTS:
        return (
            False,
            "Too many incorrect attempts. Request a new verification code.",
        )

    if not user.email_verification_code or not user.email_verification_expires_at:
        return False, "No verification code is active. Request a new code."

    if timezone.now() > user.email_verification_expires_at:
        return False, "This code has expired. Request a new verification code."

    if code != user.email_verification_code:
        user.email_verification_attempts = int(user.email_verification_attempts or 0) + 1
        user.save(update_fields=["email_verification_attempts"])
        left = MAX_VERIFY_ATTEMPTS - user.email_verification_attempts
        if left <= 0:
            return (
                False,
                "Too many incorrect attempts. Request a new verification code.",
            )
        return False, f"Incorrect code. {left} attempt{'s' if left != 1 else ''} left."

    user.email_verified = True
    user.email_verification_code = ""
    user.email_verification_expires_at = None
    user.email_verification_attempts = 0
    update_fields = [
        "email_verified",
        "email_verification_code",
        "email_verification_expires_at",
        "email_verification_attempts",
        *_clear_password_reset_side(user),
    ]

    if is_main:
        user.is_approved = True
        update_fields.append("is_approved")
        user.save(update_fields=update_fields)
        return True, "Email verified. You can now sign in."

    # Supervisor: desk access still blocked until approval
    user.is_approved = False
    update_fields.append("is_approved")
    user.save(update_fields=update_fields)
    return (
        True,
        "Email verified. Your account still needs approval before you can sign in.",
    )


verify_supervisor_email_code = verify_email_code
