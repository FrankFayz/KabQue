from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from queueapp.models import CampusSettings

User = get_user_model()


class Command(BaseCommand):
    help = "Create KabQue supervisor (@kab.ac.ug) and ensure campus settings exist."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="admin@kab.ac.ug")
        parser.add_argument("--password", default="admin123")
        parser.add_argument("--full-name", default="KabQue Supervisor")

    def handle(self, *args, **options):
        CampusSettings.get_solo()
        email = options["email"].strip().lower()
        password = options["password"]
        full_name = options["full_name"].strip()
        parts = full_name.split()
        first = parts[0] if parts else "KabQue"
        last = " ".join(parts[1:]) if len(parts) > 1 else "Supervisor"

        user, created = User.objects.get_or_create(
            username=email,
            defaults={
                "email": email,
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "first_name": first,
                "last_name": last,
            },
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created supervisor '{email}'"))
        else:
            user.email = email
            user.role = User.Role.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.first_name = first
            user.last_name = last
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.WARNING(f"Updated existing supervisor '{email}'"))

        # Keep legacy username=admin usable if it still exists (migrate email)
        legacy = User.objects.filter(username="admin").exclude(pk=user.pk).first()
        if legacy:
            legacy.email = email
            legacy.role = User.Role.ADMIN
            legacy.is_staff = True
            legacy.set_password(password)
            legacy.save(update_fields=["email", "role", "is_staff", "password"])
            self.stdout.write(self.style.WARNING("Also updated legacy username 'admin'"))

        self.stdout.write(f"Supervisor login: email={email} password={password}")
