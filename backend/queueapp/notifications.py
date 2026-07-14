import logging

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


def send_email_notification(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    if not to_email:
        return False, "No email address"
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
            import urllib.request
            import json

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
