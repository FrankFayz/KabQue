import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

from .phones import normalize_phone
from .auth_utils import normalize_email

logger = logging.getLogger(__name__)

__all__ = [
    "build_approval_message",
    "build_approval_sms",
    "normalize_phone",
    "normalize_notify_channel",
    "resolve_student_contacts",
    "deliver_student_notification",
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
        f"Your Kabale University document-approval visit has been scheduled.\n\n"
        f"Come on: {date_str}\n"
        f"Your queue number: {position}\n"
        f"Registration number: {registration_number}\n"
        f"Secret code (show at the desk): {secret_code}\n\n"
        f"Bring all required documents. Do not share your secret code.\n\n"
        f"— KabQue · Kabale University"
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
    first = (full_name or "Student").strip().split()[0]
    # Keep short and direct — one clear action + the 3 facts they need at the desk
    return (
        f"KabQue: {first}, come for document approval on {date_str}. "
        f"Queue #{position}. Code {secret_code}. "
        f"Bring your documents. Reg {registration_number}."
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
    if email and "@" in email:
        return name, email
    return _parse_from_email(settings.DEFAULT_FROM_EMAIL)


def _parse_brevo_error(raw: str, status_code: int = 0) -> str:
    text = (raw or "").strip()
    lower = text.lower()
    if "sender" in lower and (
        "not valid" in lower or "invalid" in lower or "not found" in lower
    ):
        return (
            "Brevo rejected the sender email. Set BREVO_SENDER_EMAIL to a verified "
            "sender in your Brevo account."
        )
    if status_code in (401, 403) or "unauthorized" in lower or "api-key" in lower:
        return "Invalid Brevo API key"
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            msg = parsed.get("message") or parsed.get("error") or ""
            if msg:
                return str(msg)[:200]
    except json.JSONDecodeError:
        pass
    return (text[:200] if text else f"Brevo HTTP {status_code}") or "Email send failed"


def _send_via_brevo(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    api_key = (getattr(settings, "BREVO_API_KEY", "") or "").strip()
    if not api_key:
        return False, "BREVO_API_KEY not configured"

    sender_name, sender_email = _sender_identity()
    if not sender_email or "@" not in sender_email:
        return False, "BREVO_SENDER_EMAIL is missing or invalid"

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email.strip().lower()}],
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
            raw = resp.read().decode("utf-8", errors="replace")
            logger.info(
                "Brevo accepted email to %s from %s (HTTP %s)",
                to_email,
                sender_email,
                resp.status,
            )
            if raw:
                try:
                    parsed = json.loads(raw)
                    if parsed.get("messageId") or parsed.get("messageIds"):
                        return True, ""
                except json.JSONDecodeError:
                    pass
        return True, ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("Brevo email failed (%s): %s", exc.code, detail)
        return False, _parse_brevo_error(detail, exc.code)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Brevo email failed")
        return False, str(exc)[:160]


def send_email_notification(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    to_email = normalize_email(to_email or "")
    if not to_email or "@" not in to_email:
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
        or "device not found" in lower
    ):
        return "MySMSGate device offline — open the app on the gateway phone and keep it online"
    if "sim" in lower or "slot" in lower:
        return "Wrong SIM slot on server (clear MYSMSGATE_SIM_SLOT, or use 0 for SIM 1)"
    if "phone" in lower or "number" in lower or "invalid to" in lower or "recipient" in lower:
        return "Invalid recipient phone on student profile"
    if "balance" in lower or "credit" in lower or "quota" in lower:
        return "MySMSGate account limit reached — check the dashboard"
    if detail:
        return detail[:160]
    return "SMS send failed"


def _mysmsgate_accepted(status_code: int, parsed: dict | None) -> bool:
    """HTTP 200/202 with success != false (MySMSGate queues as pending)."""
    if status_code not in (200, 201, 202):
        return False
    if not isinstance(parsed, dict):
        return True
    if parsed.get("success") is False:
        return False
    if str(parsed.get("status", "")).lower() in ("failed", "error"):
        return False
    return True


def _parse_optional_sim_slot(raw) -> int | None:
    """
    MySMSGate slot: 0 = SIM 1, 1 = SIM 2.
    Empty / unset → None (let the gateway pick automatically).
    """
    text = str(raw if raw is not None else "").strip()
    if text == "":
        return None
    try:
        slot = int(text)
    except (TypeError, ValueError):
        return None
    if slot in (0, 1):
        return slot
    return None


def _mysmsgate_post(endpoint: str, api_key: str, payload: dict) -> tuple[bool, int, str]:
    """POST JSON to MySMSGate. Returns (ok, status_code, error_or_empty)."""
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
            parsed = None
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
            if _mysmsgate_accepted(resp.status, parsed):
                logger.info(
                    "MySMSGate accepted SMS to %s (HTTP %s, status=%s, keys=%s)",
                    payload.get("to") or payload.get("number"),
                    resp.status,
                    (parsed or {}).get("status", "ok"),
                    sorted(k for k in payload if k not in ("to", "number", "message")),
                )
                return True, resp.status, ""
            return (
                False,
                resp.status,
                _mysmsgate_hint(resp.status, _parse_mysmsgate_error(raw or "")),
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "MySMSGate SMS failed (%s) payload_keys=%s: %s",
            exc.code,
            sorted(payload.keys()),
            detail,
        )
        return False, exc.code, _mysmsgate_hint(exc.code, _parse_mysmsgate_error(detail, detail))
    except Exception as exc:  # noqa: BLE001
        logger.exception("MySMSGate SMS network error")
        return False, 0, str(exc)[:160]


def _send_via_mysmsgate(to_phone: str, message: str) -> tuple[bool, str]:
    api_key = (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
    if not api_key:
        return False, (
            "MySMSGate API key missing on server — set MYSMSGATE_API_KEY "
            "(e.g. on Render Environment)"
        )

    if not to_phone.startswith("+"):
        return False, f"Phone must start with country code (+…), got: {to_phone}"

    endpoint = (
        getattr(settings, "MYSMSGATE_API_URL", "") or "https://mysmsgate.net/api/v1/send"
    ).strip()

    device_id = (getattr(settings, "MYSMSGATE_DEVICE_ID", "") or "").strip()
    configured_slot = _parse_optional_sim_slot(
        getattr(settings, "MYSMSGATE_SIM_SLOT", None)
    )
    text = message[:1000]

    # Official shape first: {to, message}. Then device. Slot last (and only if set).
    # Never force SIM 2 — empty SIM slot = auto.
    attempts: list[dict] = [
        {"to": to_phone, "message": text},
    ]
    if device_id:
        attempts.append({"to": to_phone, "message": text, "device_id": device_id})
    if configured_slot is not None:
        attempts.append({"to": to_phone, "message": text, "slot": configured_slot})
        if device_id:
            attempts.append(
                {
                    "to": to_phone,
                    "message": text,
                    "device_id": device_id,
                    "slot": configured_slot,
                }
            )

    # De-dupe
    seen = set()
    unique: list[dict] = []
    for payload in attempts:
        key = tuple(sorted((k, str(v)) for k, v in payload.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(payload)

    last_error = "SMS send failed"
    for payload in unique:
        ok, _code, err = _mysmsgate_post(endpoint, api_key, payload)
        if ok:
            return True, ""
        if err:
            last_error = err

    if "offline" not in last_error.lower() and "api key" not in last_error.lower():
        last_error = (
            f"{last_error}. Keep the MySMSGate Android app open and online, "
            "then try SMS again."
        )
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


def resolve_student_contacts(user) -> tuple[str, str]:
    """
    Email + phone the fresher saved on their profile (post-signup).
    Always read the latest values from the user record.
    """
    email = normalize_email(getattr(user, "email", "") or "")
    phone = normalize_phone(getattr(user, "phone", "") or "")
    return email, phone


def normalize_notify_channel(channel: str) -> str:
    """Supervisor pick → exact send mode: email | sms | both."""
    raw = (channel or "both").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "email": "email",
        "email_only": "email",
        "mail": "email",
        "sms": "sms",
        "sms_only": "sms",
        "text": "sms",
        "both": "both",
        "email_sms": "both",
        "email_and_sms": "both",
        "all": "both",
    }
    return aliases.get(raw, "both")


def deliver_student_notification(
    *,
    user,
    channel: str,
    subject: str,
    email_body: str,
    sms_body: str,
) -> list[dict]:
    """
    Send exactly what the supervisor chose:
      email → email only
      sms   → SMS only
      both  → email and SMS
    Never cross-sends the other channel.
    """
    try:
        user.refresh_from_db(fields=["email", "phone"])
    except Exception:  # noqa: BLE001
        pass

    email, phone = resolve_student_contacts(user)
    mode = normalize_notify_channel(channel)
    results: list[dict] = []

    if mode in ("email", "both"):
        if email:
            ok, err = send_email_notification(email, subject, email_body)
            results.append(
                {
                    "channel": "email",
                    "destination": email,
                    "success": ok,
                    "error": err,
                }
            )
            if ok:
                logger.info("KabQue email delivered to %s", email)
            else:
                logger.warning("KabQue email failed to %s: %s", email, err)
        else:
            results.append(
                {
                    "channel": "email",
                    "destination": "",
                    "success": False,
                    "error": "Student has no email on their profile",
                }
            )

    if mode in ("sms", "both"):
        if phone:
            ok, err = send_sms_notification(phone, sms_body)
            results.append(
                {
                    "channel": "sms",
                    "destination": phone,
                    "success": ok,
                    "error": err,
                }
            )
            if ok:
                logger.info("KabQue SMS delivered to %s", phone)
            else:
                logger.warning("KabQue SMS failed to %s: %s", phone, err)
        else:
            results.append(
                {
                    "channel": "sms",
                    "destination": "",
                    "success": False,
                    "error": "Student has no phone on their profile",
                }
            )

    return results
