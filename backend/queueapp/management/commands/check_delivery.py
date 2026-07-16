"""
Check whether Brevo (email) and MySMSGate (SMS) keys are loaded.

Usage:
  python manage.py check_delivery
"""

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Show whether email/SMS delivery keys are configured on this server."

    def handle(self, *args, **options):
        brevo = (getattr(settings, "BREVO_API_KEY", "") or "").strip()
        sender = (getattr(settings, "BREVO_SENDER_EMAIL", "") or "").strip()
        sms = (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
        device = (getattr(settings, "MYSMSGATE_DEVICE_ID", "") or "").strip()
        slot = (getattr(settings, "MYSMSGATE_SIM_SLOT", "") or "").strip()

        def mask(value: str) -> str:
            if not value:
                return "(missing)"
            if len(value) <= 8:
                return "***"
            return f"{value[:6]}…{value[-4:]} ({len(value)} chars)"

        self.stdout.write("KabQue delivery config")
        self.stdout.write(f"  BREVO_API_KEY:        {mask(brevo)}")
        self.stdout.write(f"  BREVO_SENDER_EMAIL:   {sender or '(missing)'}")
        self.stdout.write(f"  MYSMSGATE_API_KEY:    {mask(sms)}")
        self.stdout.write(f"  MYSMSGATE_DEVICE_ID:  {mask(device)}")
        self.stdout.write(f"  MYSMSGATE_SIM_SLOT:   {slot or '(auto)'}")

        ok = True
        if not brevo:
            ok = False
            self.stderr.write(self.style.ERROR("Email will fail — set BREVO_API_KEY"))
        if not sender:
            ok = False
            self.stderr.write(self.style.ERROR("Email will fail — set BREVO_SENDER_EMAIL"))
        if not sms:
            ok = False
            self.stderr.write(self.style.ERROR("SMS will fail — set MYSMSGATE_API_KEY"))

        if ok:
            self.stdout.write(
                self.style.SUCCESS(
                    "Keys present. Keep MySMSGate app online; sender email must be "
                    "verified in Brevo. On Render, set these in Environment."
                )
            )
