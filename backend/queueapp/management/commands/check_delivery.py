"""
Check whether Brevo (email) and Africa's Talking (SMS) keys are loaded.

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
        at_key = (getattr(settings, "AFRICAS_TALKING_API_KEY", "") or "").strip()
        at_env = (getattr(settings, "AFRICAS_TALKING_ENVIRONMENT", "") or "sandbox").strip()
        at_user = (getattr(settings, "AFRICAS_TALKING_USERNAME", "") or "").strip()
        at_from = (getattr(settings, "AFRICAS_TALKING_SHORTCODE", "") or "").strip()

        def mask(value: str) -> str:
            if not value:
                return "(missing)"
            if len(value) <= 8:
                return "***"
            return f"{value[:6]}…{value[-4:]} ({len(value)} chars)"

        self.stdout.write("KabQue delivery config")
        self.stdout.write(f"  BREVO_API_KEY:               {mask(brevo)}")
        self.stdout.write(f"  BREVO_SENDER_EMAIL:          {sender or '(missing)'}")
        self.stdout.write(f"  AFRICAS_TALKING_API_KEY:     {mask(at_key)}")
        self.stdout.write(f"  AFRICAS_TALKING_ENVIRONMENT: {at_env}")
        self.stdout.write(f"  AFRICAS_TALKING_USERNAME:    {at_user or '(missing)'}")
        if at_env == "sandbox":
            self.stdout.write("  AFRICAS_TALKING_SHORTCODE:   (ignored in sandbox — sends as 'sandbox')")
        else:
            self.stdout.write(f"  AFRICAS_TALKING_SHORTCODE:   {at_from or '(missing)'}")

        ok = True
        if not brevo:
            ok = False
            self.stderr.write(self.style.ERROR("Email will fail — set BREVO_API_KEY"))
        if not sender:
            ok = False
            self.stderr.write(self.style.ERROR("Email will fail — set BREVO_SENDER_EMAIL"))
        if not at_key:
            ok = False
            self.stderr.write(
                self.style.ERROR("SMS will fail — set AFRICAS_TALKING_API_KEY")
            )
        if at_env == "production" and not at_from:
            ok = False
            self.stderr.write(
                self.style.ERROR(
                    "SMS will fail — set AFRICAS_TALKING_SHORTCODE to your approved "
                    "alphanumeric sender ID or shortcode"
                )
            )

        if ok and at_env == "sandbox":
            self.stdout.write(
                self.style.WARNING(
                    "SMS is in SANDBOX. Only numbers registered as test numbers in the "
                    "Africa's Talking dashboard receive these, and they show as "
                    "'sandbox'. Real students will NOT get these texts. Set "
                    "AFRICAS_TALKING_ENVIRONMENT=production to go live."
                )
            )
        elif ok:
            self.stdout.write(
                self.style.SUCCESS(
                    "Keys present. Africa's Talking is live — real students will "
                    "receive real SMS and you are billed per message. The sender "
                    "email must be verified in Brevo."
                )
            )
