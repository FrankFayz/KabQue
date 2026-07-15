from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("queueapp", "0010_password_reset_codes"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="desk_outcome",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="approved | rejected | empty",
                max_length=20,
            ),
        ),
    ]
