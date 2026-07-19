import json
import logging
import re
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

from .phones import normalize_phone, validate_east_africa_phone
from .auth_utils import normalize_email

logger = logging.getLogger(__name__)

__all__ = [
    "REQUIRED_DOCUMENTS",
    "required_documents_payload",
    "build_approval_message",
    "build_approval_sms",
    "normalize_phone",
    "normalize_notify_channel",
    "resolve_student_contacts",
    "deliver_student_notification",
    "send_email_notification",
    "send_sms_notification",
]

# Documents students should bring to the KabQue approval desk.
REQUIRED_DOCUMENTS = (
    "Original admission letter",
    "Original academic documents (result slips, certificates, or transcripts)",
    "Identity card(s) from your previous school, college, or institution",
    "National Council for Higher Education (NCHE) payment receipt",
    "Original birth certificate",
    "National ID (optional but relevant)",
)


def required_documents_payload() -> list[str]:
    """Same checklist for email, SMS context, and the student dashboard."""
    return list(REQUIRED_DOCUMENTS)


def build_approval_message(
    *,
    full_name: str,
    registration_number: str,
    scheduled_date,
    secret_code: str,
    position: int,
) -> str:
    date_str = scheduled_date.strftime("%A, %d %B %Y")
    docs = "\n".join(f"  {i}. {item}" for i, item in enumerate(REQUIRED_DOCUMENTS, start=1))
    return (
        f"Dear {full_name},\n\n"
        f"Your Kabale University document-approval visit has been scheduled.\n\n"
        f"Come on: {date_str}\n"
        f"Your queue number: {position}\n"
        f"Registration number: {registration_number}\n"
        f"Secret code (show at the desk): {secret_code}\n\n"
        f"Bring these documents (originals):\n"
        f"{docs}\n\n"
        f"Do not share your secret code.\n\n"
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
    # Compact but concrete — full list is in email + KabQue dashboard
    return (
        f"KabQue: {first}, document approval on {date_str}. "
        f"Queue #{position}. Code {secret_code}. "
        f"Bring originals: admission letter, academic docs, previous school ID, "
        f"NCHE receipt, birth certificate; National ID if available. "
        f"Reg {registration_number}."
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
        with urllib.request.urlopen(req, timeout=10) as resp:
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


def _mysmsgate_post(endpoint: str, api_key: str, payload: dict) -> tuple[bool, int, str, dict | None]:
    """POST JSON to MySMSGate. Returns (ok, status_code, error_or_empty, parsed)."""
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
                    "MySMSGate accepted SMS to %s (HTTP %s, status=%s, slot=%s, sms_id=%s)",
                    payload.get("to"),
                    resp.status,
                    (parsed or {}).get("status", "ok"),
                    payload.get("slot"),
                    (parsed or {}).get("sms_id") or (parsed or {}).get("id"),
                )
                return True, resp.status, "", parsed if isinstance(parsed, dict) else None
            return (
                False,
                resp.status,
                _mysmsgate_hint(resp.status, _parse_mysmsgate_error(raw or "")),
                parsed if isinstance(parsed, dict) else None,
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "MySMSGate SMS failed (%s) payload_keys=%s: %s",
            exc.code,
            sorted(payload.keys()),
            detail,
        )
        return (
            False,
            exc.code,
            _mysmsgate_hint(exc.code, _parse_mysmsgate_error(detail, detail)),
            None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("MySMSGate SMS network error")
        return False, 0, str(exc)[:160], None


def _mysmsgate_poll_status(api_key: str, sms_id) -> str:
    """Return latest provider status string for an SMS id (best-effort)."""
    if sms_id in (None, ""):
        return ""
    url = f"https://mysmsgate.net/api/v1/sms?id={sms_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(parsed, dict):
        return ""
    return str(
        parsed.get("status")
        or parsed.get("state")
        or (parsed.get("sms") or {}).get("status")
        or ""
    ).strip().lower()


def _send_via_mysmsgate(to_phone: str, message: str) -> tuple[bool, str]:
    """
    Send one SMS via MySMSGate TO the student phone only.

    Your Android phone is only the *sender* (gateway). The recipient must be the
    student's registered number. If texts land in *your* inbox as received, that
    usually means the profile phone is actually one of your own SIMs (self-SMS
    on a dual-SIM phone) — not that KabQue rewrote the destination.
    """
    api_key = (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
    if not api_key:
        return False, (
            "MySMSGate API key missing on server — set MYSMSGATE_API_KEY "
            "(e.g. on Render Environment)"
        )

    # MySMSGate requires international format: +CC… (e.g. +2567XXXXXXXX).
    try:
        recipient = validate_east_africa_phone(to_phone)
    except ValueError as exc:
        return False, str(exc)
    if not recipient.startswith("+"):
        return False, f"Phone must start with country code (+…), got: {to_phone}"

    endpoint = (
        getattr(settings, "MYSMSGATE_API_URL", "") or "https://mysmsgate.net/api/v1/send"
    ).strip()

    device_id = (getattr(settings, "MYSMSGATE_DEVICE_ID", "") or "").strip()
    configured_slot = _parse_optional_sim_slot(
        getattr(settings, "MYSMSGATE_SIM_SLOT", None)
    )
    text = message[:1000]

    # This gateway phone reports default_sim_slot=1 (SIM 2). Auto/empty then
    # uses SIM 2, which often queues locally but never reaches students.
    # Prefer SIM 1 (slot 0) unless the operator explicitly sets a slot.
    preferred_slot = 0 if configured_slot is None else configured_slot
    fallback_slot = 1 if preferred_slot == 0 else 0

    def _payload(slot: int) -> dict:
        # Official MySMSGate shape: to must be E.164 with country code.
        body = {"to": recipient, "message": text, "slot": slot}
        if device_id:
            body["device_id"] = device_id
        return body

    attempts = [_payload(preferred_slot), _payload(fallback_slot)]
    seen = set()
    unique: list[dict] = []
    for payload in attempts:
        if payload.get("to") != recipient:
            continue
        key = tuple(sorted((k, str(v)) for k, v in payload.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(payload)

    last_error = "SMS send failed"
    for payload in unique:
        ok, _code, err, parsed = _mysmsgate_post(endpoint, api_key, payload)
        if not ok:
            if err:
                last_error = err
            continue

        sms_id = None
        if isinstance(parsed, dict):
            sms_id = parsed.get("sms_id") or parsed.get("id")

        # Brief poll — catch carrier/SIM failures that still returned HTTP 202.
        final_status = ""
        if sms_id not in (None, ""):
            for _ in range(3):
                time.sleep(1.2)
                final_status = _mysmsgate_poll_status(api_key, sms_id)
                if final_status in ("failed", "error", "sent", "delivered", "sending"):
                    break

        if final_status in ("failed", "error"):
            last_error = (
                f"MySMSGate marked SMS failed on SIM {int(payload.get('slot', 0)) + 1}. "
                "Put airtime on the SIM that should send, set MYSMSGATE_SIM_SLOT to that "
                "SIM (0 = SIM 1, 1 = SIM 2), and keep the app online."
            )
            logger.warning(
                "MySMSGate SMS to %s failed after accept (sms_id=%s, status=%s, slot=%s)",
                recipient,
                sms_id,
                final_status,
                payload.get("slot"),
            )
            continue

        logger.info(
            "MySMSGate SMS to student %s ok (sms_id=%s, status=%s, slot=%s)",
            recipient,
            sms_id,
            final_status or (parsed or {}).get("status"),
            payload.get("slot"),
        )
        return True, ""

    if "offline" not in last_error.lower() and "api key" not in last_error.lower():
        last_error = (
            f"{last_error}. Keep the MySMSGate Android app open and online, "
            "use SIM 1 for SMS (MYSMSGATE_SIM_SLOT=0), and confirm each student "
            "phone is THEIR number — not the gateway phone."
        )
    return False, last_error


def send_sms_notification(phone: str, body: str) -> tuple[bool, str]:
    """
    Send SMS via MySMSGate to the student's profile phone.

    Always normalizes to E.164 with country code (+256… / +254… / etc.) before
    calling the gateway — MySMSGate rejects bare local numbers.
    """
    raw = (phone or "").strip()
    if not raw:
        return False, "No phone on student profile"
    try:
        to_phone = validate_east_africa_phone(raw)
    except ValueError as exc:
        # Last chance: normalize local 07… → +256… then re-validate
        try:
            to_phone = validate_east_africa_phone(normalize_phone(raw))
        except ValueError:
            return False, str(exc)

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
    Phone is always returned in E.164 with country code when valid
    (MySMSGate needs +CC…, e.g. +2567XXXXXXXX).
    """
    email = normalize_email(getattr(user, "email", "") or "")
    raw_phone = getattr(user, "phone", "") or ""
    try:
        phone = validate_east_africa_phone(raw_phone) if raw_phone.strip() else ""
    except ValueError:
        phone = normalize_phone(raw_phone)
        if phone and not phone.startswith("+"):
            phone = ""
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
