import json
import logging
import re
import urllib.error
import urllib.parse
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

# --- Africa's Talking delivery-status vocabulary ---------------------------
# AT answers synchronously with one Recipients[] entry per number. It confirms
# the network ACCEPTED the message — it never confirms handset delivery, and it
# says so in the response. Anything that is not an explicit accept is a
# failure, so a broken sender ID or a typo'd number can never show a green tick.
AT_ACCEPTED_STATUS_CODES = (101, 102, 103)
AT_ACCEPTED_STATUS_WORDS = frozenset(
    {"success", "sentsuccess", "sent", "submitted", "queued"}
)

SMS_NOT_SET_UP_ERROR = (
    "Text messages could not be sent. SMS is not fully set up yet — "
    "ask the system admin to finish setup, then try again."
)
SMS_BAD_NUMBER_ERROR = (
    "Text messages could not be sent — that student’s phone number looks "
    "incomplete. Update their profile and try again."
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
    # Must stay under 160 characters so it is ONE SMS segment.
    #
    # A multipart (2-part) message is rejected by some East African networks
    # and costs double, while single-segment messages have always gone through.
    # The full document list stays in the email, which has no length pressure.
    return (
        f"KabQue: {first}, your Kabale University document check is "
        f"{date_str}, queue no {position}. Bring originals. "
        f"Your desk code is {secret_code}. Do not share it."
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


def _at_setting(name: str) -> str:
    return (getattr(settings, name, "") or "").strip()


def _at_is_sandbox() -> bool:
    return (_at_setting("AFRICAS_TALKING_ENVIRONMENT") or "sandbox").lower() != "production"


def _at_sender_id() -> str:
    """
    The `from` AT puts in front of the message.

    Live: your approved alphanumeric sender ID (e.g. "KabQue") or shortcode.

    Sandbox: return "" so the field is omitted entirely. The sandbox does NOT
    ignore `from` — it rejects every value, including "sandbox" and "", with
    `{"SMSMessageData": {"Message": "InvalidSenderId", "Recipients": []}}`.
    Verified live against api.sandbox.africastalking.com.
    """
    if _at_is_sandbox():
        return ""
    return _at_setting("AFRICAS_TALKING_SHORTCODE")


def _at_parse_error(raw: str, fallback: str = "Africa's Talking rejected the request") -> str:
    """AT reports failures as {"errorMessage": ..., "errorCode": ...}."""
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:400]
    if isinstance(parsed, dict):
        for key in ("errorMessage", "errorMessageId", "message", "error"):
            value = parsed.get(key)
            if value:
                return str(value)[:300]
    return str(parsed)[:300]


def _at_hint(status_code: int, detail: str) -> str:
    """Calm, non-technical copy for the desk — keep provider jargon in logs only."""
    lower = (detail or "").lower()

    # A bad request shape is a server bug, never a student's fault. Check this
    # before the number/network branches, because AT's own 415 text contains the
    # words "not supported" and would otherwise be blamed on the phone number.
    if (
        status_code in (405, 415)
        or "content-type" in lower
        or "not supported. expected" in lower
        or "unsupported media type" in lower
    ):
        return (
            "Text messages could not be sent because the SMS service is "
            "misconfigured on the server. Ask the system admin to check the SMS "
            "setup, then try again."
        )

    if "api key" in lower and any(
        word in lower for word in ("invalid", "missing", "unauthor", "not found", "401")
    ):
        return SMS_NOT_SET_UP_ERROR

    if "credit" in lower or "balance" in lower or "quota" in lower:
        return (
            "Text messages could not be sent because the SMS account has no credit "
            "left. Ask the system admin to top it up, then try again."
        )

    if "sandbox" in lower and any(
        word in lower for word in ("test", "not allowed", "unauthorised", "unauthorized", "not approved")
    ):
        return (
            "Text messages could not be sent — that number is not a registered test "
            "number for the SMS sandbox. Ask the system admin to add it, or switch "
            "the SMS account to the live service."
        )

    if "sender" in lower or "shortcode" in lower or "alphanumeric" in lower:
        return (
            "Text messages could not be sent because the SMS sender ID is not "
            "approved on the account. Ask the system admin to check the SMS setup."
        )

    if "sent to 0/" in lower:
        return SMS_BAD_NUMBER_ERROR

    if "network" in lower or "notsupportedbynetwork" in lower or "operator" in lower:
        return (
            "Text messages could not be sent — that student’s network does not "
            "accept the message. Check their phone number and try again."
        )

    if (
        status_code in (400, 404, 422)
        or "phone" in lower
        or "number" in lower
        or "recipient" in lower
        or "msisdn" in lower
    ):
        return SMS_BAD_NUMBER_ERROR

    if status_code in (401, 403) or "forbidden" in lower or "unauthorized" in lower:
        return SMS_NOT_SET_UP_ERROR

    return (
        "Text messages could not be sent right now. Try again in a moment, and ask "
        "the system admin to check the SMS account if it keeps happening."
    )


def _at_recipient_accepted(entry: dict) -> bool:
    """True only when AT explicitly accepted this number for the network."""
    code = entry.get("statusCode")
    if isinstance(code, str) and code.strip().isdigit():
        code = int(code)
    if isinstance(code, int) and code in AT_ACCEPTED_STATUS_CODES:
        return True
    word = str(entry.get("status") or "").strip().lower().replace("_", "").replace(" ", "")
    return word in AT_ACCEPTED_STATUS_WORDS


def _at_recipients(parsed) -> list[dict]:
    """Pull Recipients[] out of the SMSMessageData envelope."""
    if not isinstance(parsed, dict):
        return []
    data = parsed.get("SMSMessageData")
    if not isinstance(data, dict):
        return []
    recipients = data.get("Recipients")
    if not isinstance(recipients, list):
        return []
    return [item for item in recipients if isinstance(item, dict)]


def _at_message_data(parsed) -> dict:
    """The SMSMessageData envelope, which is where AT puts its verdict."""
    if not isinstance(parsed, dict):
        return {}
    data = parsed.get("SMSMessageData")
    return data if isinstance(data, dict) else {}


def _send_via_africas_talking(to_phone: str, message: str) -> tuple[bool, str]:
    """
    Send one SMS to one student through Africa's Talking.

    AT returns HTTP 200 with a per-recipient verdict inside SMSMessageData, so
    the response body — not the status code — decides success. Anything that is
    not an explicit accept is reported as a failure.
    """
    api_key = _at_setting("AFRICAS_TALKING_API_KEY")
    if not api_key:
        return False, SMS_NOT_SET_UP_ERROR

    username = _at_setting("AFRICAS_TALKING_USERNAME")
    if _at_is_sandbox() and not username:
        username = "sandbox"
    if not username:
        return False, SMS_NOT_SET_UP_ERROR

    # AT requires international E.164 with a country code (e.g. +2567XXXXXXXX).
    try:
        recipient = to_sms_destination(to_phone)
    except ValueError:
        return False, SMS_BAD_NUMBER_ERROR

    sender = _at_sender_id()
    if not _at_is_sandbox() and not sender:
        return False, (
            "Text messages could not be sent because no SMS sender ID is set on the "
            "server. Ask the system admin to finish the SMS setup, then try again."
        )

    # 1600 characters is AT's documented hard limit for a single request.
    text = (message or "").strip()[:1600]
    if not text:
        return False, "Text messages could not be sent — the message was empty."

    payload = {
        "username": username,
        "to": recipient,
        "message": text,
        "bulkSMSMode": 1,
    }
    # Omit `from` entirely in the sandbox — see _at_sender_id().
    if sender:
        payload["from"] = sender

    base_url = _at_setting("AFRICAS_TALKING_BASE_URL") or "https://api.africastalking.com"
    endpoint = f"{base_url.rstrip('/')}/version1/messaging"
    environment = "sandbox" if _at_is_sandbox() else "production"

    # AT's /version1/messaging endpoint accepts form encoding ONLY. Posting JSON
    # returns HTTP 415 "The request's Content-Type [application/json] is not
    # supported", which is a permanent server misconfiguration — not a student
    # number problem — so it must never be reported as one.
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "apiKey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "KabQue-SMS/1.0 (+https://kabque.onrender.com)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Africa's Talking SMS failed (HTTP %s, env=%s, to=%s, from=%r): %s",
            exc.code,
            environment,
            recipient,
            sender,
            detail[:400],
        )
        return False, _at_hint(exc.code, _at_parse_error(detail, detail))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Africa's Talking SMS network error to %s", recipient)
        return False, (
            "Text messages could not be sent right now — the SMS provider could not "
            "be reached. Try again in a moment."
        )

    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict) and (parsed.get("errorMessage") or parsed.get("errorCode")):
        detail = _at_parse_error(raw)
        logger.error(
            "Africa's Talking error envelope (env=%s, to=%s): %s", environment, recipient, detail
        )
        return False, _at_hint(0, detail)

    recipients = _at_recipients(parsed)
    if not recipients:
        # AT reports whole-request failures (e.g. "InvalidSenderId", "Sent to 0/1")
        # in SMSMessageData.Message with an EMPTY Recipients array, under HTTP 201.
        # That field is the only place the real reason appears.
        detail = str(_at_message_data(parsed).get("Message") or "").strip()
        logger.error(
            "Africa's Talking returned no recipient verdict (env=%s, to=%s, from=%r, message=%r): %s",
            environment,
            recipient,
            sender or "(omitted)",
            detail,
            raw[:400],
        )
        return False, _at_hint(0, detail or "no recipient verdict returned")

    for entry in recipients:
        if not _at_recipient_accepted(entry):
            detail = str(entry.get("status") or "Unknown")
            logger.warning(
                "Africa's Talking refused SMS to %s (env=%s, statusCode=%s, status=%s, messageId=%s)",
                recipient,
                environment,
                entry.get("statusCode"),
                entry.get("status"),
                entry.get("messageId"),
            )
            return False, _at_hint(0, detail)

    entry = recipients[0]
    logger.info(
        "Africa's Talking accepted SMS to %s (env=%s, from=%r, statusCode=%s, messageId=%s, cost=%s)",
        recipient,
        environment,
        sender,
        entry.get("statusCode"),
        entry.get("messageId"),
        entry.get("cost"),
    )
    return True, ""


def send_sms_notification(phone: str, body: str) -> tuple[bool, str]:
    """
    Send an SMS to the student's profile phone via Africa's Talking.

    Always normalizes to E.164 with a country code (+256… / +254… / etc.) before
    calling AT — AT rejects bare local numbers.
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
            if "country" in str(exc).lower():
                return False, (
                    "Text messages could not be sent — that student’s phone number must "
                    "include a country code (e.g. Uganda +256…)."
                )
            return False, SMS_BAD_NUMBER_ERROR

    return _send_via_africas_talking(to_phone, body)


def resolve_student_contacts(user) -> tuple[str, str]:
    """
    Email + phone the fresher saved on their profile (post-signup).
    Phone is always returned in E.164 with country code when valid
    (Africa's Talking needs +CC…, e.g. +2567XXXXXXXX).
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
                logger.info("KabQue SMS accepted for %s", phone)
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
