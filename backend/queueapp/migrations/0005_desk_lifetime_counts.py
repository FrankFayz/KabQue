# Generated manually for KabQue desk outcomes + notification log SET_NULL
# Idempotent: columns may already exist from CampusSettings.ensure_lifetime_columns().

from django.db import migrations, models
import django.db.models.deletion


def seed_lifetime_counts(apps, schema_editor):
    QueueEntry = apps.get_model("queueapp", "QueueEntry")
    CampusSettings = apps.get_model("queueapp", "CampusSettings")
    campus, _ = CampusSettings.objects.get_or_create(pk=1)
    campus.lifetime_approved = QueueEntry.objects.filter(status="approved").count()
    campus.lifetime_rejected = QueueEntry.objects.filter(status="rejected").count()
    campus.save(update_fields=["lifetime_approved", "lifetime_rejected"])


class Migration(migrations.Migration):

    dependencies = [
        ("queueapp", "0004_alter_studentprofile_full_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="campussettings",
                    name="lifetime_approved",
                    field=models.PositiveIntegerField(default=0),
                ),
                migrations.AddField(
                    model_name="campussettings",
                    name="lifetime_rejected",
                    field=models.PositiveIntegerField(default=0),
                ),
                migrations.AlterField(
                    model_name="notificationlog",
                    name="queue_entry",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notifications",
                        to="queueapp.queueentry",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE queueapp_campussettings
                      ADD COLUMN IF NOT EXISTS lifetime_approved integer DEFAULT 0 NOT NULL;
                    ALTER TABLE queueapp_campussettings
                      ADD COLUMN IF NOT EXISTS lifetime_rejected integer DEFAULT 0 NOT NULL;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE queueapp_notificationlog
                      ALTER COLUMN queue_entry_id DROP NOT NULL;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
        migrations.RunPython(seed_lifetime_counts, migrations.RunPython.noop),
    ]
