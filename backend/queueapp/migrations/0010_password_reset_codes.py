from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("queueapp", "0009_supervisor_email_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="password_reset_code_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="user",
            name="password_reset_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="password_reset_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
