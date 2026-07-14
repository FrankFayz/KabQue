import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

from .phones import normalize_phone

logger = logging.getLogger(__name__)

__all__ = [
    "build_approval_message",
    "build_approval_sms",
    "normalize_phone",
    "send_email_notification",
    "send_sms_notification",
]


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
        f"Queue number for your approval day: {position}\n"
        f"Please prepare and report for document approval on: {date_str}.\n\n"
        f"Your SECRET CODE (show this to the admin): {secret_code}\n\n"
        f"Bring all required documents. Do not share your secret code.\n\n"
        f"— KabQue / Kabale University"
    )


def build_approval_sms(
    *,
    full_name: str,
    registration_number: str,
    scheduled_date,
    secret_code: str,
    position: int,
) -> str:
    date_str = scheduled_date.strftime("%d %b %Y")
    first = (full_name or "student").strip().split()[0]
    return (
        f"KabQue: Hi {first}, report for document approval on {date_str}. "
        f"Reg {registration_number}, queue number #{position}. "
        f"SECRET CODE: {secret_code}. Do not share. — Kabale University"
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


def _parse_mysmsgate_error(raw: str, fallback: str = "MySMSGate request failed") -> str:
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:400]
    if isinstance(parsed, dict):
        for key in ("message", "error", "detail", "reason"):
            val = parsed.get(key)
            if val:
                return str(val)
        return str(parsed)[:400]
    return str(parsed)[:400]


def _mysmsgate_hint(status_code: int, detail: str) -> str:
    """Short operator-facing codes (not long browser essays)."""
    lower = (detail or "").lower()
    if status_code in (401, 403) or "unauthorized" in lower or "invalid api" in lower:
        return "Invalid MySMSGate API key on server"
    if (
        status_code in (404, 409, 422, 503)
        or "no device" in lower
        or "offline" in lower
        or "not connected" in lower
        or "no online" in lower
    ):
        return "MySMSGate device offline"
    if "phone" in lower or "number" in lower or "invalid to" in lower:
        return "Invalid recipient phone"
    if detail:
        return detail[:120]
    return "SMS send failed"


def _send_via_mysmsgate(to_phone: str, message: str) -> tuple[bool, str]:
    api_key = (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
    if not api_key:
        return False, "MySMSGate API key missing on server"

    if not to_phone.startswith("+"):
        return False, f"Phone must start with country code (+…), got: {to_phone}"

    endpoint = (
        getattr(settings, "MYSMSGATE_API_URL", "") or "https://mysmsgate.net/api/v1/send"
    ).strip()

    base_payload = {
        "to": to_phone,
        "message": message[:1000],
    }
    device_id = (getattr(settings, "MYSMSGATE_DEVICE_ID", "") or "").strip()
    sim_slot = getattr(settings, "MYSMSGATE_SIM_SLOT", None)

    attempts = []
    if device_id:
        attempts.append({"device_id": device_id})
    # Always try without a pinned device (uses first online device on the account)
    attempts.append({})

    last_error = "SMS send failed"
    for extra in attempts:
        payload = {**base_payload, **extra}
        if sim_slot is not None and str(sim_slot).strip() != "":
            try:
                slot = int(sim_slot)
                payload["slot"] = slot
            except (TypeError, ValueError):
                pass

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                logger.info(
                    "MySMSGate accepted SMS to %s (HTTP %s)", to_phone, resp.status
                )
                if raw:
                    try:
                        parsed = json.loads(raw)
                        if parsed.get("success") is False:
                            last_error = _mysmsgate_hint(
                                resp.status,
                                _parse_mysmsgate_error(raw),
                            )
                            continue
                    except json.JSONDecodeError:
                        pass
            return True, ""
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            parsed_detail = _parse_mysmsgate_error(detail, detail)
            last_error = _mysmsgate_hint(exc.code, parsed_detail)
            logger.error(
                "MySMSGate SMS failed to %s (%s): %s", to_phone, exc.code, detail
            )
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception("MySMSGate SMS failed to %s", to_phone)
            last_error = str(exc)[:120]
            continue

    return False, last_error


def send_sms_notification(phone: str, body: str) -> tuple[bool, str]:
    """Send SMS via MySMSGate to the student's profile phone (E.164 +country)."""
    to_phone = normalize_phone(phone)
    if not to_phone:
        return False, "No phone on student profile"
    if not to_phone.startswith("+"):
        return False, "Student phone needs country code (+256…)"

    if (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip():
        return _send_via_mysmsgate(to_phone, body)

    username = getattr(settings, "AFRICAS_TALKING_USERNAME", "") or ""
    api_key = getattr(settings, "AFRICAS_TALKING_API_KEY", "") or ""

    if username and api_key:
        try:
            data = json.dumps(
                {
                    "username": username,
                    "to": to_phone,
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
            return False, str(exc)[:120]

    return False, "MySMSGate API key missing on server"
