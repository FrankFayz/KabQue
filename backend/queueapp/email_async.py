"""Fire-and-forget email delivery so auth responses do not wait on Brevo."""

from __future__ import annotations

import logging
import threading

from django.db import close_old_connections

logger = logging.getLogger(__name__)


def send_email_in_background(to_email: str, subject: str, body: str) -> None:
    """Queue an email send on a daemon thread; never blocks the HTTP response."""

    def _run() -> None:
        close_old_connections()
        try:
            from .notifications import send_email_notification

            ok, err = send_email_notification(to_email, subject, body)
            if not ok:
                logger.warning(
                    "Background email to %s failed: %s",
                    to_email,
                    (err or "unknown")[:200],
                )
        except Exception:  # noqa: BLE001
            logger.exception("Background email to %s crashed", to_email)
        finally:
            close_old_connections()

    threading.Thread(
        target=_run,
        name="kabque-email",
        daemon=True,
    ).start()
