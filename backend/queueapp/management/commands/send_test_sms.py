"""
Send one real test SMS through Africa's Talking and print the raw response.

Verifies the API key, host, encoding and sender ID against the live API
without going through the queue UI.

Usage:
  python manage.py send_test_sms +2567XXXXXXXX
  python manage.py send_test_sms +2567XXXXXXXX "Custom message"
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from queueapp.notifications import (
    _at_message_data,
    _at_recipients,
    _at_sender_id,
    send_sms_notification,
)

DEFAULT_MESSAGE = (
    "KabQue SMS test. Your Kabale University document check is 24 Sep 2026."
)


class Command(BaseCommand):
    help = "Send one real test SMS via Africa's Talking and show the raw response."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Recipient in international format, e.g. +2567XXXXXXXX")
        parser.add_argument("message", nargs="?", default=DEFAULT_MESSAGE)

    def handle(self, *args, **options):
        to = options["to"]
        message = options["message"]

        api_key = (getattr(settings, "AFRICAS_TALKING_API_KEY", "") or "").strip()
        if not api_key:
            raise CommandError("AFRICAS_TALKING_API_KEY is not set on this server.")

        username = (getattr(settings, "AFRICAS_TALKING_USERNAME", "") or "").strip()
        sender = _at_sender_id()
        base_url = (getattr(settings, "AFRICAS_TALKING_BASE_URL", "") or "").strip()

        payload = {"username": username, "to": to, "message": message, "bulkSMSMode": 1}
        # The sandbox rejects ANY `from` value with InvalidSenderId, so the field
        # is omitted entirely rather than sent blank.
        if sender:
            payload["from"] = sender

        endpoint = f"{base_url.rstrip('/')}/version1/messaging"

        self.stdout.write("Africa's Talking test send")
        self.stdout.write(f"  environment : {settings.AFRICAS_TALKING_ENVIRONMENT}")
        self.stdout.write(f"  endpoint    : {endpoint}")
        self.stdout.write(f"  username    : {username}")
        self.stdout.write(f"  from        : {sender or '(omitted — sandbox)'}")
        self.stdout.write(f"  to          : {to}")
        self.stdout.write(f"  api key     : {api_key[:6]}...{api_key[-4:]}")

        request = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={
                "apiKey": api_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Could not reach Africa's Talking: {exc}")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None

        self.stdout.write(f"  HTTP status : {status}")
        self.stdout.write("")
        self.stdout.write("  RAW RESPONSE")
        self.stdout.write(
            json.dumps(parsed, indent=2) if parsed is not None else f"  {raw[:600]}"
        )
        self.stdout.write("")

        summary = str(_at_message_data(parsed).get("Message") or "").strip()
        if summary:
            self.stdout.write(f"  AT summary  : {summary}")
        for entry in _at_recipients(parsed):
            self.stdout.write(
                "  recipient   : {number} status={status} code={statusCode} "
                "id={messageId} cost={cost}".format(
                    number=entry.get("number"),
                    status=entry.get("status"),
                    statusCode=entry.get("statusCode"),
                    messageId=entry.get("messageId"),
                    cost=entry.get("cost"),
                )
            )

        self.stdout.write("")
        ok, err = send_sms_notification(to, message)
        if ok:
            self.stdout.write(
                self.style.SUCCESS(
                    "  VERDICT: accepted by the network. Note: in the sandbox nothing "
                    "reaches a handset unless the number is a registered test number."
                )
            )
        else:
            self.stdout.write(self.style.ERROR(f"  VERDICT: not sent — {err}"))
