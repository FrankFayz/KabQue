import queueapp.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("queueapp", "0006_batch_position_on_notify"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("student", "Student"),
                    ("admin", "Supervisor"),
                    ("main_admin", "Main Admin"),
                ],
                default="student",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="is_approved",
            field=models.BooleanField(
                default=True,
                help_text="False until a Main Admin confirms Kabale staff membership.",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="username",
            field=models.CharField(
                error_messages={"unique": "A user with that username already exists."},
                help_text="Required. Letters, digits and @/./+/-/_/# only.",
                max_length=150,
                unique=True,
                validators=[queueapp.models.UsernameWithHashValidator()],
            ),
        ),
        # Existing supervisors were created before approval gating — keep them active.
        migrations.RunSQL(
            sql="UPDATE queueapp_user SET is_approved = TRUE WHERE role = 'admin';",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
