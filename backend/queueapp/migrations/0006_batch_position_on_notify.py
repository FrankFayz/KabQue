# Nullable batch position — numbers assigned only when supervisor notifies a batch

from django.db import migrations, models


def clear_waiting_positions(apps, schema_editor):
    QueueEntry = apps.get_model("queueapp", "QueueEntry")
    QueueEntry.objects.filter(status="waiting").update(position=None)


class Migration(migrations.Migration):

    dependencies = [
        ("queueapp", "0005_desk_lifetime_counts"),
    ]

    operations = [
        migrations.AlterField(
            model_name="queueentry",
            name="position",
            field=models.PositiveIntegerField(
                blank=True,
                db_index=True,
                help_text="Batch queue number assigned when the supervisor notifies a day batch.",
                null=True,
            ),
        ),
        migrations.AlterModelOptions(
            name="queueentry",
            options={
                "ordering": ["created_at", "id"],
                "verbose_name_plural": "Queue entries",
            },
        ),
        migrations.RunPython(clear_waiting_positions, migrations.RunPython.noop),
    ]
