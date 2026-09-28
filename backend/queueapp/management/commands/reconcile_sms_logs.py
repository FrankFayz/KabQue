"""
Reconcile historical SMS NotificationLog rows against real MySMSGate delivery results.

Background
----------
Between 2026-07-20 and 2026-09-23, KabQue reported SMS as "sent" as soon as the
MySMSGate API returned HTTP 202 (queued) and a poll observed the in-flight state
"sending". The carrier then failed every one of those messages. That left the
queue desk showing a green tick for messages that were never delivered.

This command matches each stored SMS log against the gateway's own history and
flips the provably-false successes to failed. It corrects reporting only; it
never re-sends anything and never touches message bodies, students, or queues.

Safety
------
* Read-only by default. Pass --apply to write.
* Only rows the gateway positively reports as FAILED are changed.
* Genuine successes and rows with no gateway evidence are left untouched.
* Writes are idempotent, and --apply prints a summary of every change.

Usage:
  python manage.py reconcile_sms_logs
  python manage.py reconcile_sms_logs --apply
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from queueapp.models import NotificationLog

GATEWAY_HISTORY_URLS = (
    "https://mysmsgate.net/api/v1/history?direction=out&limit=200",
    "https://api.mysmsgate.net/api/v1/history?direction=out&limit=200",
)

# The gateway records the message a few seconds after we log it, so allow a
# generous window. 90s still matched every real row with a 4-13s offset.
MATCH_WINDOW = timedelta(seconds=90)

# Gateway statuses that are final, positive delivery outcomes.
DELIVERED_STATUSES = ("sent", "delivered")

CORRECTION_NOTE = (
    "Reconciled with MySMSGate delivery history on {date}: the gateway recorded "
    "this message as failed (carrier rejected it; status '{status}', gateway "
    "error {error!r}). It was previously reported as sent because the old code "
    "treated the queued 'sending' state as success. No new message was sent."
)


class Command(BaseCommand):
    help = (
        "Flip historical SMS logs that were marked sent but which the gateway "
        "recorded as failed. Read-only unless --apply is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write the corrections. Without this, nothing is saved.",
        )

    def _fetch_history(self):
        """Return gateway history rows that KabQue itself sent (source=api)."""
        api_key = (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
        if api_key.lower().startswith("bearer "):
            api_key = api_key[7:].strip()
        if not api_key:
            raise CommandError("MYSMSGATE_API_KEY is not set on this server.")

        last_error = None
        for url in GATEWAY_HISTORY_URLS:
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "User-Agent": "KabQue-Reconcile/1.0",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
            if "Just a moment" in raw or "challenges.cloudflare.com" in raw:
                last_error = "Cloudflare challenge page"
                continue
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError as exc:
                last_error = f"invalid JSON: {exc}"
                continue
            if not isinstance(parsed, dict):
                last_error = "unexpected response shape"
                continue
            rows = parsed.get("history") or []
            # Personal texts typed on the phone are not KabQue notifications and
            # must never be used to judge a KabQue log row.
            return [r for r in rows if str(r.get("source")) == "api"]
        raise CommandError(f"Could not read MySMSGate history: {last_error}")

    def handle(self, *args, **options):
        apply_changes = options.get("apply")
        rows = self._fetch_history()
        self.stdout.write(f"Gateway history: {len(rows)} api-sourced message(s)")

        candidates = list(
            NotificationLog.objects.filter(channel="sms", success=True).order_by("sent_at")
        )
        self.stdout.write(f"DB sms rows marked success=True: {len(candidates)}\n")

        used_ids, false_success, delivered, unmatched = set(), [], [], []
        for db_row in candidates:
            best, best_delta = None, None
            for gw in rows:
                if gw["id"] in used_ids:
                    continue
                if str(gw.get("phone_to")) != db_row.destination:
                    continue
                created = datetime.strptime(
                    str(gw.get("created_at"))[:19], "%Y-%m-%dT%H:%M:%S"
                ).replace(tzinfo=timezone.utc)
                delta = abs((created - db_row.sent_at).total_seconds())
                if delta <= MATCH_WINDOW.total_seconds() and (
                    best_delta is None or delta < best_delta
                ):
                    best, best_delta = gw, delta
            if best is None:
                unmatched.append(db_row)
                continue
            used_ids.add(best["id"])
            if str(best.get("status", "")).lower() in DELIVERED_STATUSES:
                delivered.append((db_row, best))
            else:
                false_success.append((db_row, best))

        self.stdout.write(self.style.MIGRATE_HEADING("MATCHED AND CONFIRMED DELIVERED"))
        for db_row, gw in delivered:
            self.stdout.write(f"  id={db_row.id} {db_row.destination} -> sent (leaving as is)")

        self.stdout.write(self.style.MIGRATE_HEADING("FALSE SUCCESS (gateway says failed)"))
        for db_row, gw in false_success:
            self.stdout.write(
                f"  id={db_row.id} {db_row.sent_at:%Y-%m-%d %H:%M} {db_row.destination} "
                f"gateway={gw['id']} status={gw.get('status')!r} "
                f"error={gw.get('error_message')!r}"
            )

        self.stdout.write(self.style.MIGRATE_HEADING("NO GATEWAY EVIDENCE (leaving as is)"))
        for db_row in unmatched:
            self.stdout.write(
                f"  id={db_row.id} {db_row.sent_at:%Y-%m-%d %H:%M} {db_row.destination}"
            )

        affected = {db_row.batch_id for db_row, _ in false_success}
        self.stdout.write("")
        self.stdout.write(
            f"{len(false_success)} row(s) to correct across {len(affected)} batch(es)."
        )

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING("DRY RUN. Nothing was changed. Re-run with --apply.")
            )
            return

        if not false_success:
            self.stdout.write(self.style.SUCCESS("Nothing to correct."))
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with transaction.atomic():
            for db_row, gw in false_success:
                db_row.success = False
                db_row.error_message = CORRECTION_NOTE.format(
                    date=today,
                    status=gw.get("status"),
                    error=gw.get("error_message") or "",
                )
                db_row.save(update_fields=["success", "error_message"])
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Corrected {len(false_success)} row(s) to failed.")
        )
