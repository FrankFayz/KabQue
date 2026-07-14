import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def build_approval_message(
    *,
    full_name: str,
    registration_number: str,
    scheduled_date,
    secret_code: str,
    position: int,
) -> str:
    date_str = scheduled_date.strftime("%A, %d %B %Y")
    return (
        f"Dear {full_name},\n\n"
        f"KabQue — Kabale University document approval notice.\n\n"
        f"Registration number: {registration_number}\n"
        f"Queue position: {position}\n"
        f"Please prepare and report for document approval on: {date_str}.\n\n"
        f"Your SECRET CODE (show this to the admin): {secret_code}\n\n"
        f"Bring all required documents. Do not share your secret code.\n\n"
        f"— KabQue / Kabale University"
    )


def _parse_from_email(value: str) -> tuple[str, str]:
    """Return (name, email) from 'Name <email@x.com>' or bare email."""
    value = (value or "").strip()
    match = re.match(r"^(.*?)\s*<([^>]+)>$", value)
    if match:
        name = match.group(1).strip().strip('"') or "KabQue"
        return name, match.group(2).strip()
    if "@" in value:
        return "KabQue", value
    return "KabQue", value


def _sender_identity() -> tuple[str, str]:
    name = (getattr(settings, "BREVO_SENDER_NAME", "") or "").strip() or "KabQue"
    email = (getattr(settings, "BREVO_SENDER_EMAIL", "") or "").strip()
    if email:
        return name, email
    return _parse_from_email(settings.DEFAULT_FROM_EMAIL)


def _send_via_brevo(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    api_key = (getattr(settings, "BREVO_API_KEY", "") or "").strip()
    if not api_key:
        return False, "BREVO_API_KEY not configured"

    sender_name, sender_email = _sender_identity()
    if not sender_email or "@" not in sender_email:
        return False, "BREVO_SENDER_EMAIL is missing or invalid"

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email.strip()}],
        "subject": subject,
        "textContent": body,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=data,
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            resp.read()
        return True, ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("Brevo email failed (%s): %s", exc.code, detail)
        return False, f"Brevo HTTP {exc.code}: {detail}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Brevo email failed")
        return False, str(exc)


def send_email_notification(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    to_email = (to_email or "").strip()
    if not to_email:
        return False, "No email address on student profile"

    # Prefer Brevo API when configured (production)
    if (getattr(settings, "BREVO_API_KEY", "") or "").strip():
        return _send_via_brevo(to_email, subject, body)

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
        return True, ""
    except Exception as exc:  # noqa: BLE001
        logger.exception("Email send failed")
        return False, str(exc)


def send_sms_notification(phone: str, body: str) -> tuple[bool, str]:
    """
    SMS via Africa's Talking when credentials are set; otherwise log to console.
    """
    if not phone:
        return False, "No phone number"

    username = settings.AFRICAS_TALKING_USERNAME
    api_key = settings.AFRICAS_TALKING_API_KEY

    if username and api_key:
        try:
            data = json.dumps(
                {
                    "username": username,
                    "to": phone,
                    "message": body[:480],
                }
            ).encode()
            req = urllib.request.Request(
                "https://api.africastalking.com/version1/messaging",
                data=data,
                headers={
                    "ApiKey": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp.read()
            return True, ""
        except Exception as exc:  # noqa: BLE001
            logger.exception("SMS send failed")
            return False, str(exc)

    # Dev fallback: print so you can still demo without an SMS gateway
    logger.info("SMS (console) to %s:\n%s", phone, body)
    print(f"\n=== KabQue SMS -> {phone} ===\n{body}\n============================\n")
    return True, "logged_to_console"
