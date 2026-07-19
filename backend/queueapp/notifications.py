import json
import logging
import re
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

from .phones import normalize_phone, to_sms_destination, validate_east_africa_phone
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
    "Three (3) passport photographs",
    "National ID (optional but recommended)",
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
    name = (full_name or "Student").strip() or "Student"
    docs = "\n".join(
        f"  {i}. {item}" for i, item in enumerate(REQUIRED_DOCUMENTS, start=1)
    )
    return (
        f"Dear {name},\n\n"
        f"This is to confirm your Kabale University document-verification "
        f"appointment via KabQue.\n\n"
        f"Appointment details\n"
        f"-------------------\n"
        f"Date: {date_str}\n"
        f"Queue number: {position}\n"
        f"Registration number: {registration_number}\n"
        f"Secret code (present at the desk): {secret_code}\n\n"
        f"Please bring the following original documents:\n"
        f"{docs}\n\n"
        f"Arrive on time and present your secret code to the desk supervisor. "
        f"Do not share your secret code with anyone.\n\n"
        f"Yours faithfully,\n"
        f"KabQue\n"
        f"Kabale University"
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
    first = (full_name or "Student").strip().split()[0] or "Student"
    # Formal, short lines — MySMSGate allows longer multipart SMS.
    return (
        f"KabQue · Kabale University\n"
        f"Dear {first},\n"
        f"Document verification: {date_str}.\n"
        f"Queue No: {position}\n"
        f"Code: {secret_code}\n"
        f"Reg: {registration_number}\n"
        f"Bring originals: admission letter; academic docs; previous school ID; "
        f"NCHE receipt; birth certificate; 3 passport photos; National ID if available.\n"
        f"Do not share your code."
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


def _looks_like_cloudflare_challenge(raw: str) -> bool:
    text = (raw or "").lower()
    return (
        "just a moment" in text
        or "cf-chl" in text
        or "challenges.cloudflare.com" in text
        or "cdn-cgi/challenge-platform" in text
        or ("<!doctype html" in text and "cloudflare" in text)
    )


def _mysmsgate_hint(status_code: int, detail: str) -> str:
    """Calm, non-technical copy for the desk — keep provider jargon in logs only."""
    lower = (detail or "").lower()

    if _looks_like_cloudflare_challenge(detail) or "cloudflare" in lower:
        return (
            "Text messages could not be sent from the live server right now. "
            "The SMS provider is blocking that connection — try again shortly, "
            "or ask the system admin to switch the SMS API address."
        )

    # Explicit key rejection only — do not treat every 401 as a bad key
    # (offline gateways sometimes return Unauthorized too).
    key_rejected = (
        "invalid api key" in lower
        or "invalid api" in lower
        or (
            "api key" in lower
            and ("invalid" in lower or "missing" in lower or "expired" in lower)
        )
    )
    if key_rejected:
        return (
            "Text messages could not be sent. SMS setup needs a quick check — "
            "ask the system admin if this keeps happening."
        )

    if (
        status_code in (401, 403)
        or "unauthorized" in lower
        or "no device" in lower
        or "offline" in lower
        or "not connected" in lower
        or "no online" in lower
        or "device not found" in lower
        or status_code in (404, 409, 422, 503)
    ):
        return (
            "Text messages could not be sent. Open the SMS gateway app on the "
            "phone, keep it online, then try again."
        )
    if "sim" in lower or "slot" in lower:
        return (
            "Text messages could not be sent from the SIM on the gateway phone. "
            "Check airtime and try again."
        )
    if "phone" in lower or "number" in lower or "invalid to" in lower or "recipient" in lower:
        return (
            "Text messages could not be sent — that student’s phone number looks "
            "incomplete. Update their profile and try again."
        )
    if "balance" in lower or "credit" in lower or "quota" in lower:
        return (
            "Text messages could not be sent right now. Try again a little later."
        )
    return (
        "Text messages could not be sent right now. Keep the gateway phone online "
        "and try again in a moment."
    )


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


def _mysmsgate_send_endpoints(configured: str) -> list[str]:
    """Candidate send URLs — API host first (avoids Cloudflare on www)."""
    primary = (configured or "").strip() or "https://api.mysmsgate.net/api/v1/send"
    candidates = [
        primary,
        "https://api.mysmsgate.net/api/v1/send",
        "https://mysmsgate.net/api/v1/send",
    ]
    seen = set()
    out = []
    for url in candidates:
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(url.rstrip("/"))
    return out


def _mysmsgate_post(
    endpoint: str,
    api_key: str,
    payload: dict,
    *,
    auth_mode: str = "bearer",
) -> tuple[bool, int, str, dict | None]:
    """POST JSON to MySMSGate. Returns (ok, status_code, error_or_empty, parsed)."""
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "KabQue-SMS/1.0 (+https://kabque.onrender.com)",
    }
    if auth_mode == "x-api-key":
        headers["X-API-KEY"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        endpoint,
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if _looks_like_cloudflare_challenge(raw):
                logger.error(
                    "MySMSGate blocked by Cloudflare challenge (HTTP %s) at %s",
                    resp.status,
                    endpoint,
                )
                return (
                    False,
                    resp.status,
                    _mysmsgate_hint(resp.status, raw),
                    None,
                )
            parsed = None
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
            if _mysmsgate_accepted(resp.status, parsed):
                logger.info(
                    "MySMSGate accepted SMS to %s (HTTP %s, status=%s, slot=%s, sms_id=%s, via=%s)",
                    payload.get("to"),
                    resp.status,
                    (parsed or {}).get("status", "ok"),
                    payload.get("slot"),
                    (parsed or {}).get("sms_id") or (parsed or {}).get("id"),
                    endpoint,
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
        if _looks_like_cloudflare_challenge(detail):
            logger.error(
                "MySMSGate Cloudflare challenge (HTTP %s) at %s — datacenter IP blocked",
                exc.code,
                endpoint,
            )
        else:
            logger.error(
                "MySMSGate SMS failed (%s) payload_keys=%s via=%s: %s",
                exc.code,
                sorted(payload.keys()),
                endpoint,
                detail[:400],
            )
        return (
            False,
            exc.code,
            _mysmsgate_hint(exc.code, _parse_mysmsgate_error(detail, detail)),
            None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("MySMSGate SMS network error via %s", endpoint)
        return False, 0, str(exc)[:160], None


def _mysmsgate_post_with_fallback(
    api_key: str, payload: dict, configured_url: str
) -> tuple[bool, int, str, dict | None]:
    """Try API host + auth header variants until one accepts JSON."""
    last = (False, 0, "SMS send failed", None)
    for endpoint in _mysmsgate_send_endpoints(configured_url):
        for auth_mode in ("bearer", "x-api-key"):
            ok, code, err, parsed = _mysmsgate_post(
                endpoint, api_key, payload, auth_mode=auth_mode
            )
            last = (ok, code, err, parsed)
            if ok:
                return last
            # Cloudflare on this host — try next host/auth immediately.
            if err and "blocking that connection" in err.lower():
                continue
            # Non-challenge auth failure on a host — still try other auth/host.
            continue
    return last


def _mysmsgate_poll_status(api_key: str, sms_id) -> str:
    """Return latest provider status string for an SMS id (best-effort)."""
    if sms_id in (None, ""):
        return ""
    for base in (
        "https://api.mysmsgate.net/api/v1/sms",
        "https://mysmsgate.net/api/v1/sms",
    ):
        url = f"{base}?id={sms_id}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "KabQue-SMS/1.0 (+https://kabque.onrender.com)",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if _looks_like_cloudflare_challenge(raw):
                    continue
                parsed = json.loads(raw) if raw else {}
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(parsed, dict):
            continue
        return str(
            parsed.get("status")
            or parsed.get("state")
            or (parsed.get("sms") or {}).get("status")
            or ""
        ).strip().lower()
    return ""


def _send_via_mysmsgate(to_phone: str, message: str) -> tuple[bool, str]:
    """
    Send one SMS via MySMSGate TO the student phone only.

    Your Android phone is only the *sender* (gateway). The recipient must be the
    student's registered number. If texts land in *your* inbox as received, that
    usually means the profile phone is actually one of your own SIMs (self-SMS
    on a dual-SIM phone) — not that KabQue rewrote the destination.
    """
    api_key = (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
    if api_key.lower().startswith("bearer "):
        api_key = api_key[7:].strip()
    if not api_key:
        return False, (
            "Text messages could not be sent. SMS is not fully set up yet — "
            "ask the system admin to finish setup, then try again."
        )

    # MySMSGate requires international E.164: +CC… (e.g. +2567XXXXXXXX).
    try:
        recipient = to_sms_destination(to_phone)
    except ValueError:
        return False, (
            "Text messages could not be sent — that student’s phone number looks "
            "incomplete. Update their profile and try again."
        )

    endpoint = (
        getattr(settings, "MYSMSGATE_API_URL", "") or "https://mysmsgate.net/api/v1/send"
    ).strip()

    device_id = (getattr(settings, "MYSMSGATE_DEVICE_ID", "") or "").strip()
    # Ignore obvious placeholders so a bad device id cannot poison auth/routing.
    if device_id.lower() in ("", "none", "null", "undefined", "your_device_id"):
        device_id = ""
    configured_slot = _parse_optional_sim_slot(
        getattr(settings, "MYSMSGATE_SIM_SLOT", None)
    )
    text = message[:1000]

    # Prefer the simple docs payload (no slot / optional device), then SIM fallbacks.
    preferred_slot = configured_slot
    fallback_slot = 1 if (preferred_slot or 0) == 0 else 0

    def _payload(*, slot=None, include_device: bool = True) -> dict:
        body = {"to": recipient, "message": text}
        if slot is not None:
            body["slot"] = int(slot)
        if include_device and device_id:
            body["device_id"] = device_id
        return body

    attempts = [
        _payload(include_device=True),
        _payload(include_device=False),
        _payload(slot=preferred_slot if preferred_slot is not None else 0),
        _payload(slot=fallback_slot),
    ]
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

    last_error = (
        "Text messages could not be sent right now. Keep the gateway phone online "
        "and try again in a moment."
    )
    for payload in unique:
        ok, _code, err, parsed = _mysmsgate_post_with_fallback(
            api_key, payload, endpoint
        )
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
                "Text messages could not be sent from the gateway phone. "
                "Check airtime, keep the SMS app online, then try again."
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

    return False, last_error


def send_sms_notification(phone: str, body: str) -> tuple[bool, str]:
    """
    Send SMS via MySMSGate to the student's profile phone.

    Always normalizes to E.164 with country code (+256… / +254… / etc.) before
    calling the gateway — MySMSGate rejects bare local numbers.
    """
    raw = (phone or "").strip()
    if not raw:
        return False, (
            "Text messages could not be sent — no telephone on that student’s profile."
        )
    try:
        to_phone = to_sms_destination(raw)
    except ValueError as exc:
        # Last chance: normalize local 07… → +256… then re-validate
        try:
            to_phone = to_sms_destination(normalize_phone(raw))
        except ValueError:
            return False, (
                "Text messages could not be sent — that student’s phone number must "
                "include a country code (e.g. Uganda +256…)."
            ) if "country" in str(exc).lower() else (
                "Text messages could not be sent — that student’s phone number looks "
                "incomplete. Update their profile and try again."
            )

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
