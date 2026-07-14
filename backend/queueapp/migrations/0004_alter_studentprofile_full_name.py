# Generated manually for profile-complete-after-signup flow

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("queueapp", "0003_studentprofile_joined_queue_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentprofile",
            name="full_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
    ]
