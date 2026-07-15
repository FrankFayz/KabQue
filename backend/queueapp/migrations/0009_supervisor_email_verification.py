# Generated manually for supervisor email verification

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("queueapp", "0008_unique_user_email_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(
                default=True,
                help_text="False until the supervisor enters the email verification code.",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verification_code",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verification_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verification_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
