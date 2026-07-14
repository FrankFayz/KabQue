from django.db import migrations, models


def dedupe_user_contacts(apps, schema_editor):
    """Keep the earliest account; clear later duplicate emails/phones."""
    User = apps.get_model("queueapp", "User")

    # Emails (case-insensitive)
    seen_emails = {}
    for user in User.objects.exclude(email="").order_by("id").iterator():
        key = (user.email or "").strip().lower()
        if not key:
            if user.email:
                user.email = ""
                user.save(update_fields=["email"])
            continue
        if key in seen_emails:
            user.email = ""
            user.save(update_fields=["email"])
        else:
            seen_emails[key] = user.id
            if user.email != key:
                user.email = key
                user.save(update_fields=["email"])

    # Phones — exact match after light normalize (digits / leading +)
    def light_norm(raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return ""
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return ""
        if text.startswith("+"):
            return f"+{digits}"
        if text.startswith("00"):
            return f"+{digits}"
        return f"+{digits}" if not digits.startswith("0") else f"+256{digits.lstrip('0')}"

    seen_phones = {}
    for user in User.objects.exclude(phone="").order_by("id").iterator():
        key = light_norm(user.phone)
        if not key:
            user.phone = ""
            user.save(update_fields=["phone"])
            continue
        if key in seen_phones:
            user.phone = ""
            user.save(update_fields=["phone"])
        else:
            seen_phones[key] = user.id
            if user.phone != key:
                user.phone = key
                user.save(update_fields=["phone"])


class Migration(migrations.Migration):

    dependencies = [
        ("queueapp", "0007_main_admin_and_approval"),
    ]

    operations = [
        migrations.RunPython(dedupe_user_contacts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="phone",
            field=models.CharField(blank=True, db_index=True, default="", max_length=20),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("email", ""), _negated=True),
                fields=("email",),
                name="uniq_user_email_when_set",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("phone", ""), _negated=True),
                fields=("phone",),
                name="uniq_user_phone_when_set",
            ),
        ),
    ]
