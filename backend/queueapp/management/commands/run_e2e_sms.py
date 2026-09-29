"""
REAL end-to-end test of the KabQue SMS module.

Deliberately NOT part of `manage.py test` — it calls the live paid Africa's
Talking API and writes a real NotificationLog row. It exercises exactly the
functions the Notify button uses, with no mocking anywhere in the path:

    deliver_approval_notice()   -> deliver_student_notification()
                                -> send_sms_notification()
                                -> _send_via_africas_talking()  [real HTTP]

Usage:
  python manage.py run_e2e_sms +256754691773
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from queueapp.models import NotificationBatch, NotificationLog, QueueEntry, StudentProfile
from queueapp.views import deliver_approval_notice, log_delivery_attempts

User = get_user_model()

PHONE = "+256754691773"


class Command(BaseCommand):
    help = "Run the real Notify delivery path end-to-end against Africa's Talking."

    def add_arguments(self, parser):
        parser.add_argument("phone", nargs="?", default=PHONE)

    def handle(self, *args, **options):
        phone = options["phone"]
        self.stdout.write(self.style.WARNING("=" * 70))
        self.stdout.write(self.style.WARNING("REAL E2E SMS TEST — sends an actual SMS"))
        self.stdout.write(self.style.WARNING("=" * 70))

        stamp = f"e2e{phone[-4:]}"
        user = User.objects.create_user(
            username=stamp,
            email=f"{stamp}@example.test",
            password="x",
            role=User.Role.STUDENT,
            phone=phone,
        )
        profile = StudentProfile.objects.create(
            user=user,
            registration_number="2026/A/KCS/9999/F",
            full_name="KabQue End To End",
        )
        entry = QueueEntry.objects.create(student=profile, position=7)
        batch = NotificationBatch.objects.create(
            created_by=user,
            scheduled_date=date(2026, 9, 24),
            batch_size=1,
            channel="sms",
        )

        secret = entry.secret_code or "E2ETEST"

        self.stdout.write(f"\n  user       : {user.username}  phone={user.phone}")
        self.stdout.write(f"  student    : {profile.full_name}  {profile.registration_number}")
        self.stdout.write(f"  queue no   : {entry.position}   desk code: {secret}")
        self.stdout.write(f"  batch      : #{batch.id}  channel=sms")

        self.stdout.write("\n  --- calling the REAL production functions ---")
        attempts = deliver_approval_notice(
            entry,
            scheduled_date=date(2026, 9, 24),
            code=secret,
            position=entry.position,
            channel="sms",
        )
        self.stdout.write(f"  deliver_approval_notice() -> {attempts}")

        log_delivery_attempts(
            batch,
            entry,
            scheduled_date=date(2026, 9, 24),
            code=secret,
            position=entry.position,
            channels_tried=attempts,
        )

        self.stdout.write("\n  --- NotificationLog rows actually written ---")
        rows = list(NotificationLog.objects.filter(batch=batch))
        if not rows:
            raise CommandError("No NotificationLog row was written — module is broken.")
        for row in rows:
            self.stdout.write(
                f"  id={row.id} channel={row.channel} destination={row.destination} "
                f"success={row.success} error={row.error_message!r}"
            )
            self.stdout.write(f"    body: {row.body}")
            self.stdout.write(f"    body length: {len(row.body)} chars")

        sms_rows = [r for r in rows if r.channel == "sms"]
        if not sms_rows:
            raise CommandError("No SMS row written.")
        row = sms_rows[0]
        self.stdout.write("\n  " + "=" * 66)
        if row.success:
            self.stdout.write(
                self.style.SUCCESS(
                    "  RESULT: PASS — the module really sent an SMS and recorded success=True"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"  RESULT: FAIL — recorded failure: {row.error_message}")
            )
        self.stdout.write("  " + "=" * 66)

        # Batch first (it has created_by -> user), then the user, which cascades
        # to the profile and its QueueEntry. Rows already inspected above.
        NotificationBatch.objects.filter(pk=batch.pk).delete()
        User.objects.filter(pk=user.pk).delete()
        self.stdout.write(
            f"\n  test rows cleaned up (user={not User.objects.filter(pk=user.pk).exists()}, "
            f"batch={not NotificationBatch.objects.filter(pk=batch.pk).exists()})."
        )

        if not row.success:
            raise CommandError("E2E send did not succeed.")
