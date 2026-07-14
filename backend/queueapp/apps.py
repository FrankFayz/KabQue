from django.apps import AppConfig


class QueueappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "queueapp"

    def ready(self):
        # Heal production schema if migrate lagged behind deploy
        try:
            from .models import CampusSettings, QueueEntry

            CampusSettings.ensure_lifetime_columns()
            QueueEntry.ensure_nullable_position()
        except Exception:
            # DB may not be ready during first migrate / collectstatic
            pass
