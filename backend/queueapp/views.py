from datetime import timedelta
import logging
import threading

from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CampusSettings, NotificationBatch, NotificationLog, QueueEntry, StudentProfile
from .notifications import (
    build_approval_message,
    build_approval_sms,
    deliver_student_notification,
    normalize_notify_channel,
    required_documents_payload,
    resolve_student_contacts,
)

logger = logging.getLogger(__name__)

from .auth_utils import (
    is_kab_university_email,
    normalize_email,
    normalize_registration_number,
    parse_main_admin_identifier,
    username_is_main_admin,
)
from .password_reset import (
    GENERIC_OK as PASSWORD_RESET_GENERIC_OK,
    can_resend_reset_code,
    issue_password_reset_code,
    resolve_reset_target,
    verify_and_set_password,
)
from .serializers import (
    AdminQueueEntrySerializer,
    ApproveSupervisorSerializer,
    CampusSettingsSerializer,
    CompleteStudentProfileSerializer,
    CompleteVerificationSerializer,
    ForgotPasswordSerializer,
    JoinQueueSerializer,
    LecturerRegisterSerializer,
    LoginSerializer,
    MainAdminLockUserSerializer,
    MainAdminRegisterSerializer,
    MainAdminUserIdSerializer,
    NotificationBatchSerializer,
    NotifyBatchSerializer,
    QueueEntryIdSerializer,
    QueueEntrySerializer,
    BatchRescheduleSerializer,
    RescheduleSerializer,
    ResendPasswordResetSerializer,
    ResendSupervisorEmailCodeSerializer,
    ResetPasswordSerializer,
    StudentProfileSerializer,
    StudentRegisterSerializer,
    VerifyCodeSerializer,
    VerifySupervisorEmailSerializer,
)
from .supervisor_email import (
    can_resend_supervisor_code,
    issue_supervisor_email_code,
    verify_supervisor_email_code,
)

User = get_user_model()


ACCOUNT_LOCKED_MESSAGE = (
    "This account has been locked by a Main Admin. You cannot sign in."
)

INVALID_LOGIN_MESSAGE = (
    "That account or password does not match. Check and try again."
)


def _authenticate_user(user_obj, password: str):
    """
    Verify password against an already-loaded user (skips ModelBackend’s
    second DB fetch that django.contrib.auth.authenticate performs).
    """
    if user_obj is None or not password:
        return None
    if not user_obj.is_active:
        return None
    if not user_obj.check_password(password):
        return None
    return user_obj


def _reject_if_locked(user_obj, password):
    """If password is correct but account is locked, return a Response; else None."""
    if user_obj is None:
        return None
    if user_obj.is_active:
        return None
    if not user_obj.check_password(password):
        return None
    return Response(
        {"detail": ACCOUNT_LOCKED_MESSAGE, "account_locked": True},
        status=status.HTTP_403_FORBIDDEN,
    )


class IsQueueAdmin(permissions.BasePermission):
    """Approved desk supervisors only (not Main Admin, not students)."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_queue_admin
        )


class IsMainAdmin(permissions.BasePermission):
    """System Main Admins only."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_main_admin
        )


class IsStudent(permissions.BasePermission):
    """Fresher accounts only."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_student_user", False)
        )


def tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": user_public_payload(user),
    }


def user_public_payload(user):
    """Auth user fields without minting new JWT tokens."""
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "is_approved": user.is_approved,
        "email_verified": bool(getattr(user, "email_verified", True)),
        "is_main_admin": user.is_main_admin,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
        "full_name": user.get_full_name() or user.username,
    }
    if hasattr(user, "profile"):
        data["profile_complete"] = user.profile.is_profile_complete
        data["registration_number"] = user.profile.registration_number
        outcome = (user.profile.desk_outcome or "").strip().lower()
        if outcome in ("approved", "rejected"):
            data["desk_outcome"] = outcome
    return data


def get_queue_entry(profile):
    return QueueEntry.objects.filter(student=profile).select_related(
        "student", "student__user"
    ).first()


def renumber_queue_positions():
    """No-op: batch numbers are fixed at notify time and must not reshuffle."""
    return


def waiting_ahead_count(entry) -> int:
    """How many waiters joined before this student (arrival order)."""
    if entry.status != QueueEntry.Status.WAITING:
        return 0
    return QueueEntry.objects.filter(
        status=QueueEntry.Status.WAITING,
        created_at__lt=entry.created_at,
    ).count()


def has_batch_queue_number(entry) -> bool:
    """True only after supervisor notify assigns 1…N for that batch."""
    if entry is None:
        return False
    if entry.status == QueueEntry.Status.WAITING:
        return False
    return entry.position is not None


def clear_waiting_batch_numbers():
    """Waiting students must not keep leftover batch numbers from prior bugs/deploys."""
    QueueEntry.ensure_nullable_position()
    QueueEntry.objects.filter(status=QueueEntry.Status.WAITING).exclude(
        position=None
    ).update(position=None)


ACTIVE_BATCH_STATUSES = (
    QueueEntry.Status.NOTIFIED,
    QueueEntry.Status.CHECKED_IN,
    QueueEntry.Status.SKIPPED,
)

# Placeholder NotificationLog channel: keeps a student visible in the batch table
# until email/SMS delivery records replace it.
BATCH_MEMBERSHIP_CHANNEL = "pending"


def detach_entry_from_batches(entry):
    """Drop batch-table links so finalized / deferred students leave the batch view."""
    NotificationLog.ensure_nullable_queue_entry()
    NotificationLog.objects.filter(queue_entry_id=entry.id).update(queue_entry=None)


def detach_entries_from_batch(batch_id, entry_ids):
    """Clear links on a source batch before moving students to a new day."""
    if not entry_ids:
        return
    NotificationLog.ensure_nullable_queue_entry()
    NotificationLog.objects.filter(
        batch_id=batch_id, queue_entry_id__in=list(entry_ids)
    ).update(queue_entry=None)


def ensure_batch_membership(
    batch,
    entry,
    *,
    scheduled_date,
    code,
    position,
):
    """
    Link a student to a batch inside the same DB transaction as notify/reschedule.

    Visibility in “Awaiting desk approval” depends on NotificationLog.queue_entry.
    Creating this row immediately (before Brevo/MySMSGate) prevents students from
    vanishing when delivery is async or when soft-refresh runs early.
    """
    NotificationLog.ensure_nullable_queue_entry()
    if NotificationLog.objects.filter(batch=batch, queue_entry_id=entry.id).exists():
        return
    body = build_approval_message(
        full_name=entry.student.full_name,
        registration_number=entry.student.registration_number,
        scheduled_date=scheduled_date,
        secret_code=code or entry.secret_code or "",
        position=position,
    )
    NotificationLog.objects.create(
        batch=batch,
        queue_entry=entry,
        channel=BATCH_MEMBERSHIP_CHANNEL,
        destination="",
        body=body,
        success=False,
        error_message="Delivery queued",
    )


def live_batch_entries(batch_id):
    """
    Students still linked to this batch and not yet approved/rejected.
    Approved (or rejected) students leave the live queue and are detached from
    batch logs — they must not appear in the batch result table.
    """
    logs = (
        NotificationLog.objects.filter(batch_id=batch_id, queue_entry__isnull=False)
        .select_related(
            "queue_entry", "queue_entry__student", "queue_entry__student__user"
        )
        .order_by("queue_entry__position", "queue_entry__id", "id")
    )
    seen = set()
    entries = []
    for log in logs:
        entry = log.queue_entry
        if not entry or entry.id in seen:
            continue
        seen.add(entry.id)
        if entry.status in ACTIVE_BATCH_STATUSES:
            entries.append(entry)
    return entries


def repair_orphaned_batch_entries(*, created_by=None) -> dict:
    """
    Heal students left NOTIFIED/checked_in/skipped with no batch membership
    (detach-before-delivery bug). Re-link them and re-queue email/SMS once.

    Returns {repaired, batch_id} for desk messaging.
    """
    linked_ids = (
        NotificationLog.objects.filter(queue_entry__isnull=False)
        .values_list("queue_entry_id", flat=True)
        .distinct()
    )
    orphans = list(
        QueueEntry.objects.filter(status__in=ACTIVE_BATCH_STATUSES)
        .exclude(id__in=linked_ids)
        .select_related("student", "student__user")
        .order_by("scheduled_date", "position", "id")
    )
    if not orphans:
        return {"repaired": 0, "batch_id": None}

    # Prefer the date already on the orphaned rows; fall back to today.
    today = timezone.localdate()
    scheduled_date = orphans[0].scheduled_date or today
    # If mixed dates, use the first orphan's date; others still get a link + notice.
    channel = "both"
    prepared = []
    new_batch_id = None

    with transaction.atomic():
        # Re-lock after the outer scan (status may have changed).
        locked = list(
            QueueEntry.objects.select_for_update()
            .select_related("student", "student__user")
            .filter(
                pk__in=[o.id for o in orphans],
                status__in=ACTIVE_BATCH_STATUSES,
            )
            .exclude(
                id__in=NotificationLog.objects.filter(
                    queue_entry__isnull=False
                ).values_list("queue_entry_id", flat=True)
            )
            .order_by("scheduled_date", "position", "id")
        )
        if not locked:
            return {"repaired": 0, "batch_id": None}

        scheduled_date = locked[0].scheduled_date or today
        batch = NotificationBatch.objects.create(
            created_by=created_by,
            scheduled_date=scheduled_date,
            batch_size=len(locked),
            channel=channel,
            message_template="Repair orphaned awaiting-desk students",
        )
        new_batch_id = batch.id

        for index, entry in enumerate(locked, start=1):
            # Keep existing day when set; otherwise use batch day.
            day = entry.scheduled_date or scheduled_date
            code = entry.secret_code or entry.assign_secret_code()
            if entry.position != index or not entry.secret_code or entry.scheduled_date != day:
                entry.secret_code = code
                entry.scheduled_date = day
                entry.position = index
                entry.status = QueueEntry.Status.NOTIFIED
                if not entry.notified_at:
                    entry.notified_at = timezone.now()
                entry.save(
                    update_fields=[
                        "secret_code",
                        "scheduled_date",
                        "position",
                        "status",
                        "notified_at",
                        "updated_at",
                    ]
                )
            ensure_batch_membership(
                batch,
                entry,
                scheduled_date=day,
                code=code,
                position=index,
            )
            prepared.append({"entry_id": entry.id, "code": code, "number": index})

    queue_prepared_notices(
        batch_id=new_batch_id,
        prepared_items=prepared,
        scheduled_date=scheduled_date,
        channel=channel,
    )
    return {"repaired": len(prepared), "batch_id": new_batch_id}


def recompact_batch_positions(batch_id):
    """Keep contiguous #1…K on remaining (unapproved) students after others leave."""
    QueueEntry.ensure_nullable_position()
    for index, entry in enumerate(live_batch_entries(batch_id), start=1):
        if entry.position != index:
            entry.position = index
            entry.save(update_fields=["position", "updated_at"])


def count_batch_leftovers():
    """
    Fast leftover count for desk stats — same people as collect_batch_leftovers(),
    without walking every batch on each refresh.
    """
    return (
        NotificationLog.objects.filter(
            queue_entry__isnull=False,
            queue_entry__status__in=ACTIVE_BATCH_STATUSES,
        )
        .values("queue_entry_id")
        .distinct()
        .count()
    )


def collect_batch_leftovers(exclude_batch_ids=None):
    """
    Unapproved students still sitting in any open batch result table.
    Ordered oldest batch first, then position — fair carry into the next schedule.
    """
    exclude = set(exclude_batch_ids or [])
    seen = set()
    leftovers = []
    for batch in NotificationBatch.objects.order_by("created_at", "id"):
        if batch.id in exclude:
            continue
        for entry in live_batch_entries(batch.id):
            if entry.id in seen:
                continue
            seen.add(entry.id)
            leftovers.append(entry)
    return leftovers


def serialize_batch_student(entry, *, channels=None):
    profile_email, profile_phone = resolve_student_contacts(entry.student.user)
    scheduled = entry.scheduled_date.isoformat() if entry.scheduled_date else None
    return {
        "queue_entry_id": entry.id,
        "position": entry.position,
        "registration_number": entry.student.registration_number,
        "full_name": entry.student.full_name,
        "email": profile_email,
        "phone": profile_phone,
        "secret_code": entry.secret_code or "",
        "scheduled_date": scheduled,
        "status": entry.status,
        "channels": channels or [],
    }


def build_live_batch_payload(batch, *, message=None, rescheduled=False, extras=None):
    students = [serialize_batch_student(e) for e in live_batch_entries(batch.id)]
    remaining_waiting = QueueEntry.objects.filter(
        status=QueueEntry.Status.WAITING
    ).count()
    payload = {
        "batch": NotificationBatchSerializer(batch).data,
        "channel": normalize_notify_channel(getattr(batch, "channel", None) or "both"),
        "message": message
        or (
            f"{len(students)} student{'s' if len(students) != 1 else ''} still in this "
            f"batch (not yet approved). Approved students leave the result table; "
            f"reschedule remaining ones onto a new day when ready."
        ),
        "requested": batch.batch_size,
        "available": len(students),
        "notified_count": len(students),
        "emails_sent": 0,
        "emails_failed": 0,
        "sms_sent": 0,
        "sms_failed": 0,
        "sms_errors": [],
        "shortage": False,
        "remaining": remaining_waiting,
        "students": students,
        "rescheduled": rescheduled,
        "remaining_in_batch": len(students),
    }
    if extras:
        payload.update(extras)
    return payload


def batch_ids_for_entry(entry_id):
    return list(
        NotificationLog.objects.filter(queue_entry_id=entry_id)
        .values_list("batch_id", flat=True)
        .distinct()
    )


def can_reschedule_entry(entry) -> bool:
    if entry is None:
        return False
    if entry.status in (
        QueueEntry.Status.APPROVED,
        QueueEntry.Status.REJECTED,
        QueueEntry.Status.WAITING,
    ):
        return False
    return entry.status in (
        QueueEntry.Status.NOTIFIED,
        QueueEntry.Status.CHECKED_IN,
        QueueEntry.Status.SKIPPED,
    ) or bool(entry.scheduled_date)


def _place_waiting_near_front(entry):
    """
    Priority return: never dump to the end of waiting.
    Sit behind ~20% of current waiters (near the front), ahead of the rest.
    """
    waiters = list(
        QueueEntry.objects.filter(status=QueueEntry.Status.WAITING)
        .exclude(pk=entry.pk)
        .order_by("created_at", "id")
    )
    if not waiters:
        return

    slot = max(0, len(waiters) // 5)
    if slot == 0:
        entry.created_at = waiters[0].created_at - timedelta(milliseconds=1)
        return

    left = waiters[slot - 1].created_at
    if slot >= len(waiters):
        entry.created_at = waiters[-1].created_at + timedelta(milliseconds=1)
        return

    right = waiters[slot].created_at
    delta = right - left
    entry.created_at = left + (delta / 2 if delta.total_seconds() > 0 else timedelta(milliseconds=1))


def return_student_to_waiting_queue(entry):
    """
    Clear day / # / secret and return to waiting for a future notify.
    Placed nearer the front of waiting (priority queue) — not at the end.
    """
    # Leave today's batch result table; they wait for a future notify, not this day
    detach_entry_from_batches(entry)
    QueueEntry.ensure_nullable_position()
    entry.status = QueueEntry.Status.WAITING
    entry.position = None
    entry.secret_code = ""
    entry.scheduled_date = None
    entry.notified_at = None
    entry.checked_in_at = None
    entry.verified_at = None
    entry.verification_notes = ""
    _place_waiting_near_front(entry)
    entry.save(
        update_fields=[
            "status",
            "position",
            "secret_code",
            "scheduled_date",
            "notified_at",
            "checked_in_at",
            "verified_at",
            "verification_notes",
            "created_at",
            "updated_at",
        ]
    )
    clear_waiting_batch_numbers()
    return entry


def apply_reschedule(entry, scheduled_date, *, notify=True, channel="both", position=None):
    """
    Assign secret code + approval day. When notify=True, send only on the
    supervisor channel (email | sms | both).
    Prefer notify=False inside a DB transaction, then call
    deliver_approval_notice() after commit so Brevo/MySMSGate are not held
    behind row locks.
    """
    channel = normalize_notify_channel(channel)
    code = entry.assign_secret_code()
    entry.status = QueueEntry.Status.NOTIFIED
    entry.scheduled_date = scheduled_date
    entry.notified_at = timezone.now()
    entry.checked_in_at = None
    entry.verified_at = None
    entry.verification_notes = ""
    update_fields = [
        "secret_code",
        "status",
        "scheduled_date",
        "notified_at",
        "checked_in_at",
        "verified_at",
        "verification_notes",
        "updated_at",
    ]
    if position is not None:
        entry.position = position
        update_fields.append("position")
    entry.save(update_fields=update_fields)

    channels = []
    if notify:
        channels = deliver_approval_notice(
            entry,
            scheduled_date=scheduled_date,
            code=code,
            position=entry.position,
            channel=channel,
        )

    return code, channels


def deliver_approval_notice(entry, *, scheduled_date, code, position, channel="both"):
    """Send the approval notice for one student (call after DB commit)."""
    channel = normalize_notify_channel(channel)
    body = build_approval_message(
        full_name=entry.student.full_name,
        registration_number=entry.student.registration_number,
        scheduled_date=scheduled_date,
        secret_code=code,
        position=position,
    )
    sms_body = build_approval_sms(
        full_name=entry.student.full_name,
        registration_number=entry.student.registration_number,
        scheduled_date=scheduled_date,
        secret_code=code,
        position=position,
    )
    subject = f"KabQue: Document approval on {scheduled_date.isoformat()}"
    return deliver_student_notification(
        user=entry.student.user,
        channel=channel,
        subject=subject,
        email_body=body,
        sms_body=sms_body,
    )


def log_delivery_attempts(batch, entry, *, scheduled_date, code, position, channels_tried):
    """Persist NotificationLog rows for attempted channels; keep membership if none."""
    email_body = build_approval_message(
        full_name=entry.student.full_name,
        registration_number=entry.student.registration_number,
        scheduled_date=scheduled_date,
        secret_code=code,
        position=position,
    )
    sms_body = build_approval_sms(
        full_name=entry.student.full_name,
        registration_number=entry.student.registration_number,
        scheduled_date=scheduled_date,
        secret_code=code,
        position=position,
    )

    wrote = False
    for attempt in channels_tried or []:
        NotificationLog.objects.create(
            batch=batch,
            queue_entry=entry,
            channel=attempt["channel"],
            destination=attempt.get("destination") or "",
            body=email_body if attempt["channel"] == "email" else sms_body,
            success=attempt["success"],
            error_message=attempt.get("error") or "",
        )
        wrote = True

    if wrote:
        # Real delivery rows exist — drop the placeholder membership row.
        NotificationLog.objects.filter(
            batch=batch,
            queue_entry_id=entry.id,
            channel=BATCH_MEMBERSHIP_CHANNEL,
        ).delete()
    else:
        # Never leave a student without a batch link if gateways returned nothing.
        ensure_batch_membership(
            batch,
            entry,
            scheduled_date=scheduled_date,
            code=code,
            position=position,
        )


def _deliver_prepared_notices(*, batch_id, prepared_items, scheduled_date, channel):
    """Send Brevo / MySMSGate for a prepared batch (runs off the HTTP thread)."""
    close_old_connections()
    try:
        batch = NotificationBatch.objects.filter(pk=batch_id).first()
        if not batch:
            return
        for item in prepared_items:
            try:
                entry = (
                    QueueEntry.objects.select_related("student", "student__user")
                    .filter(pk=item["entry_id"])
                    .first()
                )
                if entry is None:
                    continue
                channels_tried = deliver_approval_notice(
                    entry,
                    scheduled_date=scheduled_date,
                    code=item["code"],
                    position=item["number"],
                    channel=channel,
                )
                log_delivery_attempts(
                    batch,
                    entry,
                    scheduled_date=scheduled_date,
                    code=item["code"],
                    position=item["number"],
                    channels_tried=channels_tried,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Delivery failed for queue_entry=%s batch=%s — membership kept",
                    item.get("entry_id"),
                    batch_id,
                )
                # Re-assert membership so soft-refresh never orphans this student.
                try:
                    entry = QueueEntry.objects.filter(pk=item["entry_id"]).first()
                    if entry is not None:
                        ensure_batch_membership(
                            batch,
                            entry,
                            scheduled_date=scheduled_date,
                            code=item.get("code") or entry.secret_code or "",
                            position=item.get("number") or entry.position,
                        )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Could not re-link queue_entry=%s to batch=%s",
                        item.get("entry_id"),
                        batch_id,
                    )
    finally:
        close_old_connections()


def queue_prepared_notices(*, batch_id, prepared_items, scheduled_date, channel):
    """Schedule notification delivery after the DB transaction commits."""
    if not prepared_items:
        return
    items = list(prepared_items)
    sd = scheduled_date
    ch = normalize_notify_channel(channel)
    bid = batch_id

    def _start():
        threading.Thread(
            target=_deliver_prepared_notices,
            kwargs={
                "batch_id": bid,
                "prepared_items": items,
                "scheduled_date": sd,
                "channel": ch,
            },
            daemon=True,
        ).start()

    transaction.on_commit(_start)


def batch_results_from_prepared(prepared):
    """Build batch table rows without waiting on email/SMS gateways."""
    if not prepared:
        return []
    ids = [item["entry_id"] for item in prepared]
    entries = {
        e.id: e
        for e in QueueEntry.objects.select_related("student", "student__user").filter(
            pk__in=ids
        )
    }
    results = []
    for item in prepared:
        entry = entries.get(item["entry_id"])
        if entry is not None:
            results.append(serialize_batch_student(entry, channels=[]))
    return results


def pending_delivery_note(channel) -> str:
    mode = normalize_notify_channel(channel)
    if mode in ("email", "sms", "both"):
        return " Notifications are being sent in the background."
    return ""

def tally_delivery_attempts(channels_tried, *, email_ok, email_fail, sms_ok, sms_fail, sms_errors):
    """Accumulate delivery counters from one student's channel attempt list."""
    for attempt in channels_tried or []:
        if attempt.get("channel") == "email":
            if attempt.get("success"):
                email_ok += 1
            else:
                email_fail += 1
        elif attempt.get("channel") == "sms":
            if attempt.get("success"):
                sms_ok += 1
            else:
                sms_fail += 1
                err = attempt.get("error") or ""
                if err and err not in sms_errors:
                    sms_errors.append(err)
    return email_ok, email_fail, sms_ok, sms_fail, sms_errors


def channel_delivery_summary(channel, *, email_ok, email_fail, sms_ok, sms_fail) -> str:
    """Human summary that only mentions channels the supervisor selected."""
    mode = normalize_notify_channel(channel)
    parts = []
    if mode in ("email", "both"):
        parts.append(f"Emails: {email_ok}")
        if email_fail:
            parts.append(f"Email failed: {email_fail}")
    if mode in ("sms", "both"):
        parts.append(f"SMS: {sms_ok}")
        if sms_fail:
            parts.append(f"SMS failed: {sms_fail}")
    return (" " + ". ".join(parts) + ".") if parts else ""


def delivery_configured() -> dict:
    """Whether Brevo / MySMSGate keys are present on this server."""
    return {
        "email_configured": bool(
            (getattr(settings, "BREVO_API_KEY", "") or "").strip()
        ),
        "sms_configured": bool(
            (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
        ),
    }


def build_student_day_progress(entry):
    """
    Live progress for a fresher who has been notified for a specific approval day.

    total   = students still counted for that batch (shrinks on voluntary leave)
    finished = desk clears today (approve / reject / defer) = total − remaining
    remaining = still expected at the desk for that session

    Only for students currently on a notified day — never while merely waiting.
    """
    if entry is None:
        return None
    if entry.status == QueueEntry.Status.WAITING:
        return None
    if entry.status in (
        QueueEntry.Status.APPROVED,
        QueueEntry.Status.REJECTED,
    ):
        return None
    if not entry.scheduled_date or not has_batch_queue_number(entry):
        return None

    batch = None
    bids = batch_ids_for_entry(entry.id)
    if bids:
        batch = (
            NotificationBatch.objects.filter(id__in=list(bids))
            .order_by("-created_at", "-id")
            .first()
        )

    your_pos = entry.position
    ahead_today = 0

    if batch is not None:
        total = max(1, int(batch.batch_size or 1))
        live = live_batch_entries(batch.id)
        remaining = len(live)
        for peer in live:
            if peer.id == entry.id:
                continue
            if (
                peer.position is not None
                and your_pos is not None
                and peer.position < your_pos
            ):
                ahead_today += 1
    else:
        live_qs = QueueEntry.objects.filter(
            scheduled_date=entry.scheduled_date,
            status__in=ACTIVE_BATCH_STATUSES,
        )
        remaining = live_qs.count()
        total = max(remaining, int(your_pos or remaining or 1), 1)
        if your_pos is not None:
            ahead_today = live_qs.filter(position__lt=your_pos).exclude(id=entry.id).count()

    finished = max(0, min(total, total - remaining))
    percent = int(round((finished / total) * 100)) if total else 0
    percent = max(0, min(100, percent))

    return {
        "scheduled_date": entry.scheduled_date.isoformat(),
        "total": total,
        "finished": finished,
        "remaining": remaining,
        "percent": percent,
        "your_number": your_pos,
        "ahead_today": ahead_today,
        "batch_id": batch.id if batch else None,
    }


def remove_queue_entry(entry):
    """Delete live queue row; keep notification logs by nulling their FK first."""
    NotificationLog.ensure_nullable_queue_entry()
    NotificationLog.objects.filter(queue_entry_id=entry.id).update(queue_entry=None)
    profile = entry.student
    entry_id = entry.id
    entry.delete()
    profile.joined_queue_at = None
    profile.save(update_fields=["joined_queue_at"])
    renumber_queue_positions()
    return profile


def build_queue_counts():
    """
    Desk counts with a clear queue rule:

      In queue  = WAITING only (joined, not yet scheduled)
      Scheduled = notified / checked_in / skipped (left the waiting queue;
                  they sit on a day/batch instead)
      Approved  = all-time desk approvals (profile desk_outcome + any live rows)

    Join adds to In queue. Notify moves that student out of In queue into Scheduled.
    """
    CampusSettings.ensure_lifetime_columns()
    scheduled_statuses = (
        QueueEntry.Status.NOTIFIED,
        QueueEntry.Status.CHECKED_IN,
        QueueEntry.Status.SKIPPED,
    )
    counts = QueueEntry.objects.aggregate(
        waiting=Count("id", filter=Q(status=QueueEntry.Status.WAITING)),
        notified=Count("id", filter=Q(status=QueueEntry.Status.NOTIFIED)),
        checked_in=Count("id", filter=Q(status=QueueEntry.Status.CHECKED_IN)),
        approved_live=Count("id", filter=Q(status=QueueEntry.Status.APPROVED)),
        rejected_live=Count("id", filter=Q(status=QueueEntry.Status.REJECTED)),
        skipped=Count("id", filter=Q(status=QueueEntry.Status.SKIPPED)),
        scheduled=Count("id", filter=Q(status__in=scheduled_statuses)),
        live_all=Count("id"),
    )
    approved_live = counts.pop("approved_live") or 0
    rejected_live = counts.pop("rejected_live") or 0
    waiting = counts.get("waiting") or 0

    approved_profiles = StudentProfile.objects.filter(desk_outcome="approved").count()
    rejected_profiles = StudentProfile.objects.filter(desk_outcome="rejected").count()

    counts["approved"] = approved_profiles + approved_live
    counts["rejected"] = rejected_profiles + rejected_live
    # Canonical: the waiting queue only
    counts["in_queue"] = waiting
    counts["unscheduled"] = waiting
    counts["remaining"] = waiting
    counts["total"] = waiting  # desk "In queue" / legacy clients
    counts["scheduled"] = counts.get("scheduled") or 0
    counts["live_all"] = counts.pop("live_all") or 0
    leftover_n = count_batch_leftovers()
    counts["batch_leftovers"] = leftover_n
    counts["notify_pool"] = waiting + leftover_n
    return counts


def profile_payload(profile, request=None):
    return StudentProfileSerializer(profile, context={"request": request}).data


class RegisterView(APIView):
    """
    One signup form. Backend decides the role:
    - local@kab.ac.ug#@admin@# → Main Admin (system control)
    - registration number → fresher (student dashboard)
    - email ending @kab.ac.ug → supervisor (pending Main Admin approval)
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        identifier = (
            request.data.get("identifier")
            or request.data.get("registration_number")
            or request.data.get("email")
            or request.data.get("username")
            or ""
        )
        identifier = str(identifier).strip()
        password = request.data.get("password")
        account_type = (request.data.get("account_type") or "").strip().lower()

        # Main Admin: Kabale email + #@admin@# marker — verify inbox before access
        if username_is_main_admin(identifier) or account_type == "main_admin":
            serializer = MainAdminRegisterSerializer(
                data={"username": identifier, "password": password}
            )
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            user = result["user"]
            _, send_error = issue_supervisor_email_code(user)
            message = (
                "Account created. We sent a verification code to your Kabale email. "
                "Enter that code to confirm your address, then sign in."
            )
            if send_error:
                message = (
                    "Account created, but we could not send the verification email yet. "
                    "Use Resend code in a moment, or check that your Kabale email is correct."
                )
            return Response(
                {
                    "pending_email_verification": True,
                    "pending_approval": False,
                    "email": user.email,
                    "email_sent": not bool(send_error),
                    "message": message,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "username": user.username,
                        "role": user.role,
                        "is_approved": True,
                        "email_verified": False,
                        "is_main_admin": True,
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        # Prefer explicit type when provided; otherwise detect from identifier
        if not account_type:
            account_type = "lecturer" if "@" in identifier else "student"

        # Plain @kab.ac.ug is supervisor signup only — never Main Admin without #@admin@#
        if account_type in ("lecturer", "supervisor", "admin") and username_is_main_admin(
            identifier
        ):
            return Response(
                {
                    "detail": (
                        "Main Admin signup must use your Kabale email followed by #@admin@# "
                        "(example: name@kab.ac.ug#@admin@#)."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if account_type in ("lecturer", "supervisor", "admin"):
            payload = {
                "email": identifier or request.data.get("email"),
                "password": password,
                "full_name": request.data.get("full_name", ""),
            }
            serializer = LecturerRegisterSerializer(data=payload)
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            user = result["user"]
            _, send_error = issue_supervisor_email_code(user)
            message = (
                "Account created. We sent a verification code to your Kabale email. "
                "Enter that code to confirm the address is yours. "
                "Approval is still required before you can use the desk."
            )
            if send_error:
                message = (
                    "Account created, but we could not send the verification email yet. "
                    "Use Resend code in a moment, or check that your Kabale email is correct."
                )
            # Do NOT issue tokens — email verify + Main Admin approval still required
            return Response(
                {
                    "pending_email_verification": True,
                    "pending_approval": True,
                    "email": user.email,
                    "email_sent": not bool(send_error),
                    "message": message,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "role": user.role,
                        "is_approved": False,
                        "email_verified": False,
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        if account_type != "student":
            return Response(
                {"detail": "Unable to create account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "@" in identifier:
            return Response(
                {"detail": "Unable to create account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = StudentRegisterSerializer(
            data={
                "registration_number": identifier
                or request.data.get("registration_number"),
                "password": password,
            }
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        data = tokens_for_user(result["user"])
        data["in_queue"] = False
        data["profile_complete"] = False
        data["message"] = "Welcome to KabQue."
        return Response(data, status=status.HTTP_201_CREATED)


class VerifySupervisorEmailView(APIView):
    """Confirm supervisor or Main Admin owns their email via emailed signup code."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifySupervisorEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not (user.is_supervisor or user.is_main_admin):
            return Response(
                {"detail": "No account found for that email."},
                status=status.HTTP_404_NOT_FOUND,
            )

        ok, message = verify_supervisor_email_code(user, code)
        if not ok:
            return Response(
                {"detail": message, "pending_email_verification": True, "email": email},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.refresh_from_db()
        return Response(
            {
                "message": message,
                "pending_email_verification": False,
                "pending_approval": (
                    False if user.is_main_admin else (not user.is_approved)
                ),
                "email_verified": True,
                "email": user.email,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "role": user.role,
                    "is_approved": user.is_approved,
                    "email_verified": True,
                    "is_main_admin": user.is_main_admin,
                },
            }
        )


class ResendSupervisorEmailCodeView(APIView):
    """Resend signup email verification code (rate-limited)."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendSupervisorEmailCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not (user.is_supervisor or user.is_main_admin):
            return Response(
                {"detail": "No account found for that email."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if user.email_verified:
            if user.is_main_admin:
                return Response(
                    {
                        "detail": "Email already verified. You can sign in.",
                        "email_verified": True,
                        "pending_approval": False,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    "detail": (
                        "Email already verified. Wait for approval before signing in."
                    ),
                    "email_verified": True,
                    "pending_approval": not user.is_approved,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed, reason = can_resend_supervisor_code(user)
        if not allowed:
            return Response(
                {"detail": reason, "pending_email_verification": True, "email": email},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        _, send_error = issue_supervisor_email_code(user)
        if send_error:
            return Response(
                {
                    "detail": (
                        "We could not send the verification email just now. "
                        "Please try again in a moment."
                    ),
                    "pending_email_verification": True,
                    "email": email,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {
                "message": "A new verification code was sent to your email.",
                "pending_email_verification": True,
                "email": email,
            }
        )


class ForgotPasswordView(APIView):
    """Request a password-reset code (Brevo email). Always returns a generic OK."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]

        user, destination = resolve_reset_target(identifier)
        if user is None or not destination:
            return Response({"message": PASSWORD_RESET_GENERIC_OK})

        allowed, reason = can_resend_reset_code(user)
        if not allowed:
            return Response(
                {"detail": reason},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ok, _err = issue_password_reset_code(user, destination)
        if not ok:
            # Soft-fail: same message whether or not email sent (no account leak)
            return Response({"message": PASSWORD_RESET_GENERIC_OK, "email_sent": False})
        return Response({"message": PASSWORD_RESET_GENERIC_OK, "email_sent": True})


class ResetPasswordView(APIView):
    """Confirm OTP and set a new password."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        code = serializer.validated_data["code"]
        new_password = serializer.validated_data["new_password"]

        user, _ = resolve_reset_target(identifier)
        if user is None:
            return Response(
                {"detail": "Invalid or expired reset code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ok, message = verify_and_set_password(user, code, new_password)
        if not ok:
            return Response(
                {"detail": message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"message": message})


class ResendPasswordResetView(APIView):
    """Resend password-reset code (rate-limited). Generic success when eligible."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]

        user, destination = resolve_reset_target(identifier)
        if user is None or not destination:
            return Response({"message": PASSWORD_RESET_GENERIC_OK})

        allowed, reason = can_resend_reset_code(user)
        if not allowed:
            return Response(
                {"detail": reason},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ok, _err = issue_password_reset_code(user, destination)
        if not ok:
            return Response({"message": PASSWORD_RESET_GENERIC_OK, "email_sent": False})
        return Response({"message": PASSWORD_RESET_GENERIC_OK, "email_sent": True})


class LoginView(APIView):
    """
    One sign-in form. Backend decides access:
    - local@kab.ac.ug#@admin@# → Main Admin
    - registration number → fresher
    - @kab.ac.ug email → supervisor (must be approved)
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip()
        password = serializer.validated_data["password"]
        user = None

        # Main Admin: must be Kabale email + #@admin@#
        if username_is_main_admin(identifier):
            parsed = parse_main_admin_identifier(identifier)
            if not parsed:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            username, _ = parsed
            user_obj = User.objects.filter(username__iexact=username).first()
            if user_obj is None:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            locked = _reject_if_locked(user_obj, password)
            if locked:
                return locked
            user = _authenticate_user(user_obj, password)
            if user is None or not user.is_main_admin:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not getattr(user, "email_verified", False):
                return Response(
                    {
                        "detail": (
                            "Verify your Kabale email first. Enter the code we sent "
                            "when you registered, then sign in."
                        ),
                        "pending_email_verification": True,
                        "email": user.email,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            data = tokens_for_user(user)
            return Response(data)

        if "@" in identifier:
            email = normalize_email(identifier)
            # Only official Kabale staff emails may sign in via email
            if not is_kab_university_email(email):
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            user_obj = User.objects.filter(email__iexact=email).first()
            if user_obj is None:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            locked = _reject_if_locked(user_obj, password)
            if locked:
                return locked
            user = _authenticate_user(user_obj, password)
            if user is None:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            # Main Admin must NEVER sign in with email alone — always Kabale email + #@admin@#
            # Use generic invalid-login text so the marker is never disclosed in the browser.
            if user.is_main_admin or username_is_main_admin(user.username):
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if user.role != User.Role.ADMIN and not user.is_staff:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not getattr(user, "email_verified", True):
                return Response(
                    {
                        "detail": (
                            "Verify your Kabale email first. Enter the code we sent "
                            "to your inbox, then wait for Main Admin approval."
                        ),
                        "pending_email_verification": True,
                        "email": user.email,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not user.is_approved:
                return Response(
                    {
                        "detail": (
                            "Your email is verified. A Main Admin must still confirm "
                            "you are Kabale University staff before you can sign in."
                        ),
                        "pending_approval": True,
                        "email_verified": True,
                        "email": user.email,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            reg = normalize_registration_number(identifier) or identifier.strip().upper()
            profile = (
                StudentProfile.objects.filter(registration_number__iexact=reg)
                .select_related("user")
                .first()
            )
            if profile is None:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            locked = _reject_if_locked(profile.user, password)
            if locked:
                return locked
            user = _authenticate_user(profile.user, password)
            if user is None:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if user.role != User.Role.STUDENT:
                return Response(
                    {"detail": INVALID_LOGIN_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            # Cache reverse OneToOne so tokens_for_user does not re-query profile.
            user.__dict__["profile"] = profile

        # Tokens only — queue status loads on the dashboard (one less Neon round-trip here).
        data = tokens_for_user(user)
        if hasattr(user, "profile"):
            data["profile_complete"] = user.profile.is_profile_complete
        return Response(data)


class MeView(APIView):
    def get(self, request):
        # Do not mint fresh JWTs on every /auth/me/ — that slows student refresh.
        data = {"user": user_public_payload(request.user)}
        if hasattr(request.user, "profile"):
            entry = get_queue_entry(request.user.profile)
            data["in_queue"] = entry is not None
            data["profile_complete"] = request.user.profile.is_profile_complete
            data["profile"] = profile_payload(request.user.profile, request)
            if entry:
                data["queue"] = QueueEntrySerializer(
                    entry, context={"request": request}
                ).data
        else:
            data["in_queue"] = False
            data["profile_complete"] = True
        return Response(data)


class StudentQueueStatusView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        if not hasattr(request.user, "profile"):
            return Response(
                {"detail": "No student profile."}, status=status.HTTP_404_NOT_FOUND
            )

        profile = request.user.profile
        entry = get_queue_entry(profile)
        outcome = (profile.desk_outcome or "").strip().lower()
        if not entry:
            payload = {
                "in_queue": False,
                "profile_complete": profile.is_profile_complete,
                "profile": profile_payload(profile, request),
            }
            if outcome in ("approved", "rejected"):
                payload["desk_outcome"] = outcome
                payload["desk_finalized"] = True
            return Response(payload)
        ahead = waiting_ahead_count(entry)
        payload = QueueEntrySerializer(entry, context={"request": request}).data
        payload["in_queue"] = True
        payload["profile_complete"] = profile.is_profile_complete
        payload["students_ahead_waiting"] = ahead
        payload["has_batch_number"] = has_batch_queue_number(entry)
        if has_batch_queue_number(entry) or entry.status in (
            QueueEntry.Status.NOTIFIED,
            QueueEntry.Status.CHECKED_IN,
            QueueEntry.Status.SKIPPED,
        ):
            payload["required_documents"] = required_documents_payload()
        day_progress = build_student_day_progress(entry)
        if day_progress:
            payload["day_progress"] = day_progress
        return Response(payload)


class CompleteStudentProfileView(APIView):
    """Fresher completes bio + faculty details before GPS join."""

    permission_classes = [IsStudent]

    def post(self, request):
        if not hasattr(request.user, "profile"):
            return Response(
                {"detail": "No student profile."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = CompleteStudentProfileSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(
            {
                "message": "Profile saved. You can join the queue when you are on campus.",
                "profile_complete": profile.is_profile_complete,
                "profile": profile_payload(profile, request),
                "user": tokens_for_user(request.user)["user"],
            }
        )


class JoinQueueView(APIView):
    """Student joins the priority queue only after profile + on-campus GPS verification."""

    permission_classes = [IsStudent]

    @transaction.atomic
    def post(self, request):
        if not hasattr(request.user, "profile"):
            return Response(
                {"detail": "No student profile."}, status=status.HTTP_404_NOT_FOUND
            )

        profile = request.user.profile
        if not profile.is_profile_complete:
            return Response(
                {
                    "detail": (
                        "Complete your profile (name, contact, faculty, and programme) "
                        "before joining the queue."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if get_queue_entry(profile):
            return Response(
                {"detail": "You are already in the queue."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        outcome = (profile.desk_outcome or "").strip().lower()
        if outcome == "approved":
            return Response(
                {
                    "detail": (
                        "Your documents were already approved at the desk. "
                        "You cannot join the queue again."
                    ),
                    "desk_outcome": "approved",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if outcome == "rejected":
            return Response(
                {
                    "detail": (
                        "Your visit was already completed at the desk and "
                        "documents were not accepted. You cannot join the queue again."
                    ),
                    "desk_outcome": "rejected",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = JoinQueueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile.registered_latitude = serializer.validated_data["latitude"]
        profile.registered_longitude = serializer.validated_data["longitude"]
        profile.joined_queue_at = timezone.now()
        profile.save(
            update_fields=[
                "registered_latitude",
                "registered_longitude",
                "joined_queue_at",
            ]
        )

        # Join only — no batch number yet. Numbers are assigned when supervisor notifies.
        clear_waiting_batch_numbers()
        QueueEntry.ensure_nullable_position()
        try:
            entry = QueueEntry.objects.create(student=profile, position=None)
        except Exception:
            QueueEntry._position_null_ready = False
            QueueEntry.ensure_nullable_position()
            try:
                entry = QueueEntry.objects.create(student=profile, position=None)
            except Exception:
                return Response(
                    {
                        "detail": (
                            "Could not join the queue due to a temporary server issue. "
                            "Please try again in a moment."
                        )
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        if entry.position is not None:
            entry.position = None
            entry.save(update_fields=["position", "updated_at"])

        payload = QueueEntrySerializer(entry, context={"request": request}).data
        payload["in_queue"] = True
        payload["students_ahead_waiting"] = waiting_ahead_count(entry)
        payload["has_batch_number"] = False
        payload["position"] = None
        return Response(
            {
                "message": (
                    "You have joined the KabQue priority queue. "
                    "Your queue number will appear when the supervisor notifies "
                    "your approval batch."
                ),
                "queue": payload,
            },
            status=status.HTTP_201_CREATED,
        )


class StudentRescheduleView(APIView):
    """Student cannot attend: return to waiting queue (no self-chosen date)."""

    permission_classes = [IsStudent]

    @transaction.atomic
    def post(self, request):
        if not hasattr(request.user, "profile"):
            return Response(
                {"detail": "No student profile."}, status=status.HTTP_404_NOT_FOUND
            )
        entry = get_queue_entry(request.user.profile)
        if not entry:
            return Response(
                {"detail": "You are not in the queue."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not can_reschedule_entry(entry):
            return Response(
                {
                    "detail": (
                        "You can only return to waiting after you have been "
                        "scheduled for an approval day."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return_student_to_waiting_queue(entry)
        entry.refresh_from_db()
        payload = QueueEntrySerializer(entry, context={"request": request}).data
        payload["in_queue"] = True
        payload["students_ahead_waiting"] = waiting_ahead_count(entry)
        return Response(
            {
                "message": "Returned to waiting. Wait for the next supervisor schedule.",
                "queue": payload,
            }
        )


class StudentLeaveQueueView(APIView):
    """Remove the student from the queue (cancel assignment / leave for other priorities)."""

    permission_classes = [IsStudent]

    @transaction.atomic
    def post(self, request):
        if not hasattr(request.user, "profile"):
            return Response(
                {"detail": "No student profile."}, status=status.HTTP_404_NOT_FOUND
            )
        entry = get_queue_entry(request.user.profile)
        if not entry:
            return Response(
                {"detail": "You are not in the queue."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if entry.status in (
            QueueEntry.Status.APPROVED,
            QueueEntry.Status.REJECTED,
        ):
            return Response(
                {"detail": "This queue result is already final."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Shrink day's notified total so progress does not treat voluntary exit
        # as a desk finish; then recompact remaining #1…K like approve/reject.
        linked_batch_ids = batch_ids_for_entry(entry.id)
        remove_queue_entry(entry)
        for bid in linked_batch_ids:
            batch = NotificationBatch.objects.filter(pk=bid).first()
            if batch:
                live_n = len(live_batch_entries(bid))
                new_size = max(live_n, max(0, int(batch.batch_size or 0) - 1))
                if new_size != batch.batch_size:
                    batch.batch_size = new_size
                    batch.save(update_fields=["batch_size"])
            recompact_batch_positions(bid)

        profile = request.user.profile
        return Response(
            {
                "message": (
                    "You have left the queue. You can rejoin on campus whenever you are ready."
                ),
                "can_rejoin": True,
                "in_queue": False,
                "profile_complete": profile.is_profile_complete,
                "profile": profile_payload(profile, request),
            }
        )


class AdminDashboardView(APIView):
    permission_classes = [IsQueueAdmin]

    def get(self, request):
        # Read-only: do not clear batch numbers on every poll (keeps refresh fast).
        counts = build_queue_counts()
        campus = CampusSettings.get_solo()
        lite = str(request.query_params.get("lite", "")).lower() in (
            "1",
            "true",
            "yes",
        )
        if lite:
            return Response(
                {
                    "counts": counts,
                    "campus": CampusSettingsSerializer(campus).data,
                }
            )
        # Faculty/programme insight = who is still in the waiting queue only.
        waiting_qs = QueueEntry.objects.filter(status=QueueEntry.Status.WAITING)
        by_faculty = list(
            waiting_qs.values("student__faculty")
            .annotate(count=Count("id"))
            .order_by("-count", "student__faculty")
        )
        by_programme = list(
            waiting_qs.values("student__faculty", "student__programme")
            .annotate(count=Count("id"))
            .order_by("student__faculty", "-count", "student__programme")
        )
        by_faculty = [
            {"faculty": row["student__faculty"] or "", "count": row["count"]}
            for row in by_faculty
        ]
        by_programme = [
            {
                "faculty": row["student__faculty"] or "",
                "programme": row["student__programme"] or "",
                "count": row["count"],
            }
            for row in by_programme
        ]
        return Response(
            {
                "counts": counts,
                "by_faculty": by_faculty,
                "by_programme": by_programme,
                "campus": CampusSettingsSerializer(campus).data,
            }
        )


class AdminQueueListView(APIView):
    """
    Live waiting queue by default.

    Join → appears here (waiting). Notify/schedule → leaves this list
    (they move to the batch / scheduled day). Pass status= to look up others.
    """

    permission_classes = [IsQueueAdmin]

    def get(self, request):
        qs = QueueEntry.objects.select_related("student", "student__user").order_by(
            "created_at", "id"
        )
        status_filter = (request.query_params.get("status") or "").strip().lower()
        if status_filter in ("all", "*"):
            pass
        elif status_filter:
            qs = qs.filter(status=status_filter)
        else:
            # Default: only unscheduled joiners still in the queue
            qs = qs.filter(status=QueueEntry.Status.WAITING)
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(student__registration_number__icontains=search.upper())
        serializer = AdminQueueEntrySerializer(qs[:500], many=True)
        return Response(serializer.data)


class NotifyBatchView(APIView):
    """
    Build the next day batch of size N:
    1) Remaining unapproved students still in batch result tables (carry-overs)
    2) Then waiting students in arrival order

    Assigns fresh queue numbers 1…N including carry-overs, then notifies.
    """

    permission_classes = [IsQueueAdmin]

    def post(self, request):
        serializer = NotifyBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data["batch_size"]
        scheduled_date = serializer.validated_data["scheduled_date"]
        channel = normalize_notify_channel(serializer.validated_data["channel"])
        configured = delivery_configured()

        prepared = []
        shortage = False
        take_leftover = 0
        pool_available = 0
        batch_id = None

        with transaction.atomic():
            leftovers = collect_batch_leftovers()
            waiting_qs = (
                QueueEntry.objects.select_for_update()
                .select_related("student", "student__user")
                .filter(status=QueueEntry.Status.WAITING)
                .order_by("created_at", "id")
            )
            waiting_available = waiting_qs.count()
            leftover_available = len(leftovers)
            pool_available = leftover_available + waiting_available

            if pool_available == 0:
                return Response(
                    {
                        "detail": (
                            "No students to notify. Waiting queue is empty and no "
                            "unapproved students remain in a batch table."
                        ),
                        "requested": requested,
                        "available": 0,
                        "remaining": 0,
                        **configured,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            take_leftover = min(requested, leftover_available)
            take_waiting = min(requested - take_leftover, waiting_available)
            carry_entries = leftovers[:take_leftover]
            waiting_entries = list(waiting_qs[:take_waiting])
            shortage = requested > pool_available

            detach_entries_from_batch_ids = {}
            for entry in carry_entries:
                for bid in batch_ids_for_entry(entry.id):
                    detach_entries_from_batch_ids.setdefault(bid, []).append(entry.id)
            for bid, ids in detach_entries_from_batch_ids.items():
                detach_entries_from_batch(bid, ids)
                recompact_batch_positions(bid)

            clear_waiting_batch_numbers()
            for entry in waiting_entries:
                entry.refresh_from_db(fields=["position", "status", "updated_at"])

            total_plan = take_leftover + take_waiting
            batch = NotificationBatch.objects.create(
                created_by=request.user,
                scheduled_date=scheduled_date,
                batch_size=total_plan,
                channel=channel,
                message_template=(
                    f"Notify {total_plan} (carry {take_leftover} + waiting {take_waiting})"
                ),
            )
            batch_id = batch.id
            batch_number = 0

            def stage(entry):
                nonlocal batch_number
                batch_number += 1
                code, _ = apply_reschedule(
                    entry,
                    scheduled_date,
                    notify=False,
                    channel=channel,
                    position=batch_number,
                )
                ensure_batch_membership(
                    batch,
                    entry,
                    scheduled_date=scheduled_date,
                    code=code,
                    position=batch_number,
                )
                prepared.append(
                    {
                        "entry_id": entry.id,
                        "code": code,
                        "number": batch_number,
                    }
                )

            for locked in carry_entries:
                entry = (
                    QueueEntry.objects.select_for_update()
                    .select_related("student", "student__user")
                    .filter(pk=locked.pk)
                    .first()
                )
                if entry is None or entry.status not in ACTIVE_BATCH_STATUSES:
                    continue
                stage(entry)

            for locked in waiting_entries:
                entry = (
                    QueueEntry.objects.select_for_update()
                    .select_related("student", "student__user")
                    .filter(pk=locked.pk, status=QueueEntry.Status.WAITING)
                    .first()
                )
                if entry is None:
                    continue
                stage(entry)

        if not prepared:
            return Response(
                {
                    "detail": "No students could be notified. Try again.",
                    "requested": requested,
                    "available": pool_available,
                    **configured,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Schedule Brevo / MySMSGate after response — do not block the desk UI.
        queue_prepared_notices(
            batch_id=batch_id,
            prepared_items=prepared,
            scheduled_date=scheduled_date,
            channel=channel,
        )
        batch = NotificationBatch.objects.get(pk=batch_id)
        results = batch_results_from_prepared(prepared)

        remaining = QueueEntry.objects.filter(status=QueueEntry.Status.WAITING).count()
        carried_count = take_leftover
        if shortage:
            message = (
                f"Only {pool_available} student(s) were available "
                f"(batch leftovers + waiting). Assigned queue numbers 1–{len(results)} "
                f"(you requested {requested}). {remaining} still waiting."
            )
        else:
            message = (
                f"Assigned queue numbers 1–{len(results)} for {scheduled_date.isoformat()} "
                f"({carried_count} from prior batch table"
                f"{'' if carried_count == 1 else 's'} + "
                f"{max(0, len(results) - carried_count)} newly waiting). "
                f"{remaining} still waiting."
            )
        message += pending_delivery_note(channel)
        if channel in ("email", "both") and not configured["email_configured"]:
            message += " Email key missing on server."
        if channel in ("sms", "both") and not configured["sms_configured"]:
            message += " SMS key missing on server."

        return Response(
            {
                "batch": NotificationBatchSerializer(batch).data,
                "message": message,
                "requested": requested,
                "available": pool_available,
                "carried_from_batch": carried_count,
                "from_waiting": max(0, len(results) - carried_count),
                "notified_count": len(results),
                "channel": channel,
                "emails_sent": 0,
                "emails_failed": 0,
                "sms_sent": 0,
                "sms_failed": 0,
                "sms_errors": [],
                "delivery_pending": True,
                "email_configured": configured["email_configured"],
                "sms_configured": configured["sms_configured"],
                "shortage": shortage,
                "remaining": remaining,
                "remaining_in_batch": len(results),
                "students": results,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyCodeView(APIView):
    """Confirm fresher identity from notification secret code and check them in."""

    permission_classes = [IsQueueAdmin]

    def post(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["secret_code"].strip().upper()

        entry = (
            QueueEntry.objects.select_related("student", "student__user")
            .filter(secret_code__iexact=code)
            .first()
        )
        if not entry or not entry.secret_code:
            return Response(
                {
                    "detail": "Invalid secret code. No fresher matched in the system.",
                    "valid": False,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if entry.status == QueueEntry.Status.WAITING:
            return Response(
                {
                    "detail": "This code belongs to a fresher who has not been notified yet. Notify them first.",
                    "valid": False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if entry.status in (
            QueueEntry.Status.APPROVED,
            QueueEntry.Status.REJECTED,
        ):
            label = "approved" if entry.status == QueueEntry.Status.APPROVED else "rejected"
            return Response(
                {
                    "detail": (
                        f"This secret code has already been used. "
                        f"The visit was already marked as {label}."
                    ),
                    "valid": False,
                    "entry": AdminQueueEntrySerializer(entry).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        scheduled = entry.scheduled_date
        schedule_is_today = bool(scheduled and scheduled == today)

        # Only the fresher whose approval day is today may be verified — a valid
        # secret code alone is not enough if the code does not read for today.
        if not schedule_is_today:
            when = scheduled.isoformat() if scheduled else "no approval day set"
            return Response(
                {
                    "detail": (
                        "This fresher is not scheduled for today "
                        f"({today.isoformat()}). Their approval day is {when}. "
                        "Only a student scheduled for today can be verified and approved."
                    ),
                    "valid": False,
                    "schedule_is_today": False,
                    "scheduled_date": scheduled.isoformat() if scheduled else None,
                    "today": today.isoformat(),
                    "entry": AdminQueueEntrySerializer(entry).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        newly_checked_in = False
        if entry.status == QueueEntry.Status.NOTIFIED:
            entry.status = QueueEntry.Status.CHECKED_IN
            entry.checked_in_at = timezone.now()
            entry.save(update_fields=["status", "checked_in_at", "updated_at"])
            newly_checked_in = True
        elif entry.status == QueueEntry.Status.SKIPPED:
            # Allow re-check-in after a previous no-show / return visit with same code
            entry.status = QueueEntry.Status.CHECKED_IN
            entry.checked_in_at = timezone.now()
            entry.save(update_fields=["status", "checked_in_at", "updated_at"])
            newly_checked_in = True

        schedule_note = "Confirmed: this fresher is scheduled for today."

        counts = build_queue_counts()

        message = (
            "Identity confirmed and checked in."
            if newly_checked_in
            else "Identity confirmed (already checked in)."
        )

        return Response(
            {
                "valid": True,
                "message": message,
                "newly_checked_in": newly_checked_in,
                "schedule_is_today": schedule_is_today,
                "schedule_note": schedule_note,
                "today": today.isoformat(),
                "entry": AdminQueueEntrySerializer(entry).data,
                "counts": counts,
            }
        )


class CompleteVerificationView(APIView):
    """Approve / reject / return to waiting after identity confirmation."""

    permission_classes = [IsQueueAdmin]

    def post(self, request):
        serializer = CompleteVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entry_id = serializer.validated_data["queue_entry_id"]
        entry = (
            QueueEntry.objects.select_related("student", "student__user")
            .filter(id=entry_id)
            .first()
        )
        if not entry:
            return Response(
                {"detail": "Queue entry not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if entry.status in (
            QueueEntry.Status.APPROVED,
            QueueEntry.Status.REJECTED,
        ):
            return Response(
                {
                    "detail": (
                        "This visit was already completed "
                        f"({entry.status.replace('_', ' ')})."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        decision = serializer.validated_data["decision"]
        if entry.status not in (
            QueueEntry.Status.CHECKED_IN,
            QueueEntry.Status.NOTIFIED,
            QueueEntry.Status.SKIPPED,
        ):
            return Response(
                {
                    "detail": (
                        "Confirm identity with the secret code before "
                        "approving, rejecting, or sending back to the queue."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # A desk outcome (approve/reject) is only allowed for the fresher whose
        # approval day is today — even a valid secret code cannot approve someone
        # scheduled for another day.
        if decision in ("approved", "rejected"):
            today = timezone.localdate()
            scheduled = entry.scheduled_date
            if not scheduled or scheduled != today:
                when = scheduled.isoformat() if scheduled else "no approval day set"
                return Response(
                    {
                        "detail": (
                            f"Cannot mark this fresher as {decision} — they are not "
                            f"scheduled for today ({today.isoformat()}). Their approval "
                            f"day is {when}. Only a student scheduled for today can be "
                            "approved or rejected."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        removed_from_queue = False
        returned_to_waiting = False
        entry_payload = None
        removed_queue_entry_id = entry.id
        linked_batch_ids = batch_ids_for_entry(entry.id)

        # Mutation in its own atomic block. Do not catch-and-return inside the
        # same atomic that ran DDL helpers — that used to poison Postgres and
        # make Approve / Delete / Back to queue look broken.
        try:
            with transaction.atomic():
                if decision in ("approved", "rejected"):
                    CampusSettings.ensure_lifetime_columns()
                    campus = CampusSettings.get_solo()
                    profile = entry.student
                    profile.desk_outcome = decision
                    profile.save(update_fields=["desk_outcome"])
                    if decision == "approved":
                        campus.lifetime_approved = int(campus.lifetime_approved or 0) + 1
                        campus.save(update_fields=["lifetime_approved", "updated_at"])
                    else:
                        campus.lifetime_rejected = int(campus.lifetime_rejected or 0) + 1
                        campus.save(update_fields=["lifetime_rejected", "updated_at"])

                    NotificationLog.ensure_nullable_queue_entry()
                    remove_queue_entry(entry)
                    removed_from_queue = True
                    for bid in linked_batch_ids:
                        recompact_batch_positions(bid)
                else:
                    # back_to_queue — leave batch, wait near the front for next notify
                    return_student_to_waiting_queue(entry)
                    returned_to_waiting = True
                    for bid in linked_batch_ids:
                        recompact_batch_positions(bid)
                    entry.refresh_from_db()
                    entry_payload = AdminQueueEntrySerializer(entry).data
        except Exception:
            return Response(
                {
                    "detail": (
                        "Could not finalize this student right now. "
                        "Please refresh and try again."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        counts = build_queue_counts()
        labels = {
            "approved": (
                "Approved — documents accepted. Student removed from the live "
                "queue and batch table."
            ),
            "rejected": (
                "Deleted from today’s queue and batch table — documents not accepted."
            ),
            "back_to_queue": (
                "Returned to waiting nearer the front of the priority queue "
                "(not the end). Cleared from today’s batch until the next notify."
            ),
        }

        batch_payload = None
        if linked_batch_ids:
            for bid in sorted(linked_batch_ids, reverse=True):
                batch = NotificationBatch.objects.filter(id=bid).first()
                if not batch:
                    continue
                batch_payload = build_live_batch_payload(
                    batch,
                    message=labels.get(decision),
                )
                break

        return Response(
            {
                "message": labels.get(decision, f"Marked as {decision}."),
                "entry": entry_payload,
                "removed_from_queue": removed_from_queue,
                "returned_to_waiting": returned_to_waiting,
                "removed_queue_entry_id": removed_queue_entry_id
                if (removed_from_queue or returned_to_waiting)
                else None,
                "counts": counts,
                "batch": batch_payload,
            }
        )


class AdminRescheduleView(APIView):
    """
    Move one student still awaiting desk approval onto a new day.

    Creates a fresh 1-person batch so they remain visible under
    “Awaiting desk approval” (not an orphan scheduled row).
    """

    permission_classes = [IsQueueAdmin]

    def post(self, request):
        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry_id = serializer.validated_data.get("queue_entry_id")
        if not entry_id:
            return Response(
                {"detail": "queue_entry_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        scheduled_date = serializer.validated_data["scheduled_date"]
        channel = normalize_notify_channel(
            serializer.validated_data.get("channel") or "both"
        )
        entry_pk = None
        code = None
        new_batch_id = None

        with transaction.atomic():
            entry = (
                QueueEntry.objects.select_for_update()
                .select_related("student", "student__user")
                .filter(id=entry_id)
                .first()
            )
            if not entry:
                return Response(
                    {"detail": "Queue entry not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not can_reschedule_entry(entry):
                return Response(
                    {
                        "detail": (
                            "Only students still awaiting desk approval "
                            "(scheduled, not yet approved or deleted) can be rescheduled."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            linked = batch_ids_for_entry(entry.id)
            detach_entry_from_batches(entry)
            for bid in linked:
                recompact_batch_positions(bid)

            new_batch = NotificationBatch.objects.create(
                created_by=request.user,
                scheduled_date=scheduled_date,
                batch_size=1,
                channel=channel,
                message_template=f"Reschedule queue entry {entry.id}",
            )
            new_batch_id = new_batch.id

            code, _ = apply_reschedule(
                entry,
                scheduled_date,
                notify=False,
                channel=channel,
                position=1,
            )
            ensure_batch_membership(
                new_batch,
                entry,
                scheduled_date=scheduled_date,
                code=code,
                position=1,
            )
            entry_pk = entry.id

        entry = (
            QueueEntry.objects.select_related("student", "student__user")
            .filter(pk=entry_pk)
            .first()
        )
        new_batch = NotificationBatch.objects.get(pk=new_batch_id)
        prepared = [
            {
                "entry_id": entry_pk,
                "code": code,
                "number": entry.position or 1,
            }
        ]
        queue_prepared_notices(
            batch_id=new_batch_id,
            prepared_items=prepared,
            scheduled_date=scheduled_date,
            channel=channel,
        )
        results = batch_results_from_prepared(prepared)
        return Response(
            {
                "message": (
                    f"Rescheduled to {scheduled_date.isoformat()}. "
                    "They stay on Awaiting desk approval for the new day."
                    + pending_delivery_note(channel)
                ),
                "secret_code": code,
                "channel": channel,
                "channels": [],
                "delivery_pending": True,
                "entry": AdminQueueEntrySerializer(entry).data,
                "batch": NotificationBatchSerializer(new_batch).data,
                "students": results,
                "remaining_in_batch": len(results),
                "rescheduled": True,
            }
        )


class AdminActiveBatchView(APIView):
    """
    Latest notification batch that still has students awaiting desk completion.
    Approved/rejected students are already gone from this view.
    """

    permission_classes = [IsQueueAdmin]

    def get(self, request):
        # Heal orphans from the old detach-before-delivery bug (once) and
        # re-queue their email/SMS.
        repair = repair_orphaned_batch_entries(created_by=request.user)
        repaired_n = int(repair.get("repaired") or 0)
        repair_batch_id = repair.get("batch_id")

        batch_id = request.query_params.get("batch_id")
        if batch_id:
            batch = NotificationBatch.objects.filter(id=batch_id).first()
            if not batch:
                return Response(
                    {"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND
                )
            payload = build_live_batch_payload(batch)
            if repaired_n and repair_batch_id and str(batch.id) == str(repair_batch_id):
                payload["message"] = (
                    f"Restored {repaired_n} student(s) that had lost batch membership "
                    f"and re-queued their email/SMS. "
                    + (payload.get("message") or "")
                )
                payload["delivery_pending"] = True
                payload["orphans_repaired"] = repaired_n
            return Response(payload)

        # Prefer the newest batch that still has remaining (unapproved) students
        for batch in NotificationBatch.objects.order_by("-created_at", "-id")[:40]:
            if live_batch_entries(batch.id):
                payload = build_live_batch_payload(batch)
                if repaired_n:
                    payload["message"] = (
                        f"Restored {repaired_n} student(s) that had lost batch membership "
                        f"and re-queued their email/SMS. "
                        + (payload.get("message") or "")
                    )
                    payload["delivery_pending"] = True
                    payload["orphans_repaired"] = repaired_n
                return Response(payload)

        return Response(
            {
                "batch": None,
                "students": [],
                "notified_count": 0,
                "remaining_in_batch": 0,
                "message": "No open batch with remaining students.",
            }
        )


class AdminBatchRescheduleView(APIView):
    """
    End-of-day / mid-day move: remaining (not approved) students in the batch
    table are assigned fresh queue numbers 1…N on a new approval day.
    """

    permission_classes = [IsQueueAdmin]

    def post(self, request):
        serializer = BatchRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch_id = serializer.validated_data["batch_id"]
        requested = serializer.validated_data["count"]
        scheduled_date = serializer.validated_data["scheduled_date"]
        channel = normalize_notify_channel(
            serializer.validated_data.get("channel") or "both"
        )
        configured = delivery_configured()

        prepared = []
        shortage = False
        available = 0
        new_batch_id = None

        with transaction.atomic():
            source_batch = NotificationBatch.objects.filter(id=batch_id).first()
            if not source_batch:
                return Response(
                    {"detail": "Batch not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            eligible = [
                e for e in live_batch_entries(batch_id) if can_reschedule_entry(e)
            ]
            available = len(eligible)
            if available == 0:
                return Response(
                    {
                        "detail": (
                            "No students remain in this batch table. "
                            "Approved students already left; notify a new waiting batch if needed."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            to_move = eligible[:requested]
            shortage = requested > available
            move_ids = [e.id for e in to_move]

            # Lock rows so concurrent approve/delete cannot drop mid-move.
            locked_move = list(
                QueueEntry.objects.select_for_update()
                .select_related("student", "student__user")
                .filter(pk__in=move_ids, status__in=ACTIVE_BATCH_STATUSES)
                .order_by("position", "id")
            )
            if not locked_move:
                return Response(
                    {
                        "detail": (
                            "No students remain in this batch table. "
                            "Approved students already left; notify a new waiting batch if needed."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            detach_entries_from_batch(batch_id, [e.id for e in locked_move])
            recompact_batch_positions(batch_id)

            new_batch = NotificationBatch.objects.create(
                created_by=request.user,
                scheduled_date=scheduled_date,
                batch_size=len(locked_move),
                channel=channel,
                message_template=f"Reschedule remaining from batch {batch_id}",
            )
            new_batch_id = new_batch.id

            for index, entry in enumerate(locked_move, start=1):
                code, _ = apply_reschedule(
                    entry,
                    scheduled_date,
                    notify=False,
                    channel=channel,
                    position=index,
                )
                # Membership BEFORE commit — students stay visible even if
                # email/SMS delivery is still in flight or fails.
                ensure_batch_membership(
                    new_batch,
                    entry,
                    scheduled_date=scheduled_date,
                    code=code,
                    position=index,
                )
                prepared.append(
                    {"entry_id": entry.id, "code": code, "number": index}
                )

        new_batch = NotificationBatch.objects.get(pk=new_batch_id)
        queue_prepared_notices(
            batch_id=new_batch_id,
            prepared_items=prepared,
            scheduled_date=scheduled_date,
            channel=channel,
        )
        results = batch_results_from_prepared(prepared)

        message = (
            f"Moved {len(results)} remaining batch student"
            f"{'s' if len(results) != 1 else ''} to {scheduled_date.isoformat()} "
            f"with queue numbers 1–{len(results)}."
        )
        if shortage:
            message += (
                f" Requested {requested}; only {available} were still in the batch "
                f"table (others were already approved)."
            )
        message += pending_delivery_note(channel)

        remaining = QueueEntry.objects.filter(status=QueueEntry.Status.WAITING).count()
        return Response(
            {
                "batch": NotificationBatchSerializer(new_batch).data,
                "source_batch_id": batch_id,
                "message": message,
                "requested": requested,
                "available": available,
                "notified_count": len(results),
                "remaining_in_batch": len(results),
                "channel": channel,
                "emails_sent": 0,
                "emails_failed": 0,
                "sms_sent": 0,
                "sms_failed": 0,
                "sms_errors": [],
                "delivery_pending": True,
                "email_configured": configured["email_configured"],
                "sms_configured": configured["sms_configured"],
                "shortage": shortage,
                "remaining": remaining,
                "students": results,
                "rescheduled": True,
            }
        )


class AdminRemoveFromQueueView(APIView):
    """Manual removal is disabled — students leave after desk approval/rejection."""

    permission_classes = [IsQueueAdmin]

    def post(self, request):
        return Response(
            {
                "detail": (
                    "Invigilators cannot delete students from the queue. "
                    "A student is removed automatically after you approve or reject "
                    "them with their secret code."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )


class CampusSettingsView(APIView):
    permission_classes = [IsQueueAdmin]

    def get(self, request):
        return Response(CampusSettingsSerializer(CampusSettings.get_solo()).data)

    def patch(self, request):
        campus = CampusSettings.get_solo()
        serializer = CampusSettingsSerializer(campus, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


def _main_admin_accounts_qs():
    """All Main Admin accounts (role and/or #@admin@# username marker)."""
    return User.objects.filter(
        Q(role=User.Role.MAIN_ADMIN) | Q(username__contains="#@admin@#")
    ).distinct()


def _user_is_main_admin_account(user) -> bool:
    return bool(
        user
        and (
            getattr(user, "is_main_admin", False)
            or user.role == User.Role.MAIN_ADMIN
            or "#@admin@#" in str(user.username or "")
        )
    )


def _main_admin_student_row(profile):
    try:
        entry = profile.queue_entry
    except QueueEntry.DoesNotExist:
        entry = None
    outcome = (profile.desk_outcome or "").strip().lower()
    if entry is None:
        # Desk finalize beats "not in queue"; voluntary leavers stay not_in_queue.
        verification_status = (
            outcome if outcome in ("approved", "rejected") else "not_in_queue"
        )
        queue_position = None
        scheduled_date = None
        secret_code = ""
    else:
        verification_status = entry.status
        queue_position = entry.position
        scheduled_date = entry.scheduled_date
        secret_code = entry.secret_code or ""
    user = profile.user
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "phone": user.phone or "",
        "full_name": profile.full_name or user.get_full_name() or user.username,
        "role": user.role,
        "is_approved": user.is_approved,
        "is_active": user.is_active,
        "is_locked": not user.is_active,
        "is_main_admin": False,
        "is_self": False,
        "date_joined": user.date_joined,
        "registration_number": profile.registration_number,
        "faculty": profile.faculty or "",
        "programme": profile.programme or "",
        "profile_complete": profile.is_profile_complete,
        "desk_outcome": outcome if outcome in ("approved", "rejected") else "",
        "verification_status": verification_status,
        "queue_position": (
            None
            if verification_status == QueueEntry.Status.WAITING
            else queue_position
        ),
        "scheduled_date": scheduled_date,
        "secret_code": secret_code,
    }


def _main_admin_staff_row(user, *, viewer=None):
    is_main = _user_is_main_admin_account(user)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "phone": user.phone or "",
        "full_name": user.get_full_name() or user.username,
        "role": user.role,
        "is_approved": user.is_approved,
        "email_verified": bool(getattr(user, "email_verified", True)),
        "is_active": user.is_active,
        "is_locked": not user.is_active,
        "is_main_admin": is_main,
        "is_self": bool(viewer is not None and user.pk == viewer.pk),
        "date_joined": user.date_joined,
        "registration_number": "",
        "faculty": "",
        "programme": "",
        "profile_complete": True,
        "verification_status": (
            "approved"
            if user.is_approved
            else (
                "pending"
                if getattr(user, "email_verified", True)
                else "email_unverified"
            )
        ),
        "queue_position": None,
        "scheduled_date": None,
    }


def _main_admin_manageable_target(request, user_id, *, allow_main_admins=True):
    """
    Resolve an account the current Main Admin may lock or delete.
    Never allows modifying yourself. Other Main Admins are allowed (except last one).
    Returns (user, error_response).
    """
    target = User.objects.filter(pk=user_id).first()
    if not target:
        return None, Response(
            {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
        )
    if target.pk == request.user.pk:
        return None, Response(
            {
                "detail": (
                    "You cannot lock or delete your own account here. "
                    "Ask another Main Admin if you need that done."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    target_is_main = _user_is_main_admin_account(target)
    if target_is_main:
        if not allow_main_admins:
            return None, Response(
                {"detail": "Main Admin accounts cannot be changed here."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return target, None

    if target.role not in (User.Role.STUDENT, User.Role.ADMIN):
        return None, Response(
            {"detail": "Only students, supervisors, and Main Admins can be managed."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return target, None


def _guard_last_main_admin(target, *, locking=False):
    """
    Keep at least one Main Admin who can still sign in.
    Returns an error Response, or None if the action is allowed.
    """
    if not _user_is_main_admin_account(target):
        return None

    others = _main_admin_accounts_qs().exclude(pk=target.pk)
    if not others.exists():
        return Response(
            {
                "detail": (
                    "You cannot remove the only Main Admin. "
                    "Register another Main Admin first, then try again."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if locking:
        other_active = others.filter(is_active=True).count()
        if other_active == 0:
            return Response(
                {
                    "detail": (
                        "You cannot lock the last active Main Admin. "
                        "Unlock or create another Main Admin first."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    return None


def _permanently_delete_user(target: User) -> tuple[str, dict]:
    """
    Delete user and related KabQue data (profile, queue row, notification links).

    Returns (message, fresh build_queue_counts()).
    Live desk totals recompute from remaining QueueEntry + StudentProfile.desk_outcome.
    Main Admin accounts: batches they created stay (created_by set null); the user row goes.
    """
    if _user_is_main_admin_account(target):
        role_label = "Main Admin"
    elif target.role == User.Role.STUDENT:
        role_label = "student"
    else:
        role_label = "supervisor"

    label = target.email or target.username
    batch_ids: set[int] = set()
    removed_from_queue = False
    prior_status = ""

    if target.role == User.Role.STUDENT:
        try:
            label = target.profile.registration_number
        except StudentProfile.DoesNotExist:
            pass
    elif _user_is_main_admin_account(target):
        label = target.username or target.email or f"user #{target.pk}"

    try:
        profile = target.profile
    except StudentProfile.DoesNotExist:
        profile = None

    if profile is not None:
        try:
            entry = profile.queue_entry
        except QueueEntry.DoesNotExist:
            entry = None

        if entry is not None:
            prior_status = entry.status or ""
            batch_ids = set(batch_ids_for_entry(entry.id) or [])
            NotificationLog.ensure_nullable_queue_entry()
            NotificationLog.objects.filter(queue_entry_id=entry.id).update(
                queue_entry=None
            )
            entry.delete()
            removed_from_queue = True

        # Safety: no orphan queue rows for this profile
        orphan_ids = list(
            QueueEntry.objects.filter(student_id=profile.pk).values_list("id", flat=True)
        )
        if orphan_ids:
            for oid in orphan_ids:
                batch_ids.update(batch_ids_for_entry(oid) or [])
            NotificationLog.ensure_nullable_queue_entry()
            NotificationLog.objects.filter(queue_entry_id__in=orphan_ids).update(
                queue_entry=None
            )
            QueueEntry.objects.filter(id__in=orphan_ids).delete()
            removed_from_queue = True

        # Keep CampusSettings lifetime tallies aligned with desk_outcome removes
        outcome = (profile.desk_outcome or "").strip()
        if outcome in ("approved", "rejected"):
            CampusSettings.ensure_lifetime_columns()
            campus = CampusSettings.get_solo()
            if outcome == "approved":
                campus.lifetime_approved = max(0, int(campus.lifetime_approved or 0) - 1)
                campus.save(update_fields=["lifetime_approved", "updated_at"])
            else:
                campus.lifetime_rejected = max(0, int(campus.lifetime_rejected or 0) - 1)
                campus.save(update_fields=["lifetime_rejected", "updated_at"])

    # Cascades StudentProfile (and thereby desk_outcome) — Approved count shrinks
    target.delete()

    # Keep remaining batch tables and waiting order consistent.
    # Use savepoints so a compact failure cannot abort the delete transaction.
    for bid in batch_ids:
        try:
            with transaction.atomic():
                recompact_batch_positions(bid)
        except Exception:
            pass
    if removed_from_queue:
        clear_waiting_batch_numbers()
        renumber_queue_positions()

    counts = build_queue_counts()
    status_note = ""
    if prior_status:
        status_note = f" Removed from live queue (was {prior_status})."
    elif removed_from_queue:
        status_note = " Removed from live queue."

    message = (
        f"{'Main Admin' if role_label == 'Main Admin' else role_label.capitalize()} "
        f"{label} permanently deleted.{status_note}"
    )
    return message, counts


class MainAdminOverviewView(APIView):
    """Totals for the Main Admin control page."""

    permission_classes = [IsMainAdmin]

    def get(self, request):
        freshers = StudentProfile.objects.count()
        supervisors = User.objects.filter(role=User.Role.ADMIN).exclude(
            Q(role=User.Role.MAIN_ADMIN) | Q(username__contains="#@admin@#")
        )
        main_admins = _main_admin_accounts_qs()
        pending = supervisors.filter(is_approved=False).count()
        approved_supervisors = supervisors.filter(is_approved=True).count()
        return Response(
            {
                "totals": {
                    "freshers": freshers,
                    "admins": main_admins.count(),
                    "supervisors": supervisors.count(),
                    "supervisors_pending": pending,
                    "supervisors_approved": approved_supervisors,
                }
            }
        )


class MainAdminFreshersView(APIView):
    """All students with profile info and verification / queue status."""

    permission_classes = [IsMainAdmin]

    def get(self, request):
        search = (request.query_params.get("search") or "").strip()
        qs = StudentProfile.objects.select_related("user", "queue_entry").order_by(
            "-registered_at"
        )
        if search:
            qs = qs.filter(
                Q(registration_number__icontains=search)
                | Q(full_name__icontains=search)
                | Q(faculty__icontains=search)
                | Q(programme__icontains=search)
                | Q(user__email__icontains=search)
            )
        rows = [_main_admin_student_row(p) for p in qs]
        return Response({"total": len(rows), "results": rows})


class MainAdminAdminsView(APIView):
    """All Main Admin accounts."""

    permission_classes = [IsMainAdmin]

    def get(self, request):
        qs = _main_admin_accounts_qs().order_by("-date_joined")
        rows = [_main_admin_staff_row(u, viewer=request.user) for u in qs]
        return Response({"total": len(rows), "results": rows})


class MainAdminSupervisorsView(APIView):
    """All supervisor accounts (kab staff) with approval status."""

    permission_classes = [IsMainAdmin]

    def get(self, request):
        status_filter = (request.query_params.get("status") or "").strip().lower()
        qs = (
            User.objects.filter(role=User.Role.ADMIN)
            .exclude(Q(role=User.Role.MAIN_ADMIN) | Q(username__contains="#@admin@#"))
            .order_by("-date_joined")
        )
        if status_filter == "pending":
            qs = qs.filter(is_approved=False)
        elif status_filter == "approved":
            qs = qs.filter(is_approved=True)
        rows = [_main_admin_staff_row(u, viewer=request.user) for u in qs]
        return Response({"total": len(rows), "results": rows})


class MainAdminApproveSupervisorView(APIView):
    """Approve or revoke a supervisor's Kabale staff confirmation."""

    permission_classes = [IsMainAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = ApproveSupervisorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data["user_id"]
        approve = serializer.validated_data["approve"]

        target = User.objects.filter(pk=user_id).first()
        if not target:
            return Response(
                {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if target.is_main_admin or target.role == User.Role.MAIN_ADMIN:
            return Response(
                {"detail": "Cannot change approval for a Main Admin."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if target.role != User.Role.ADMIN:
            return Response(
                {"detail": "Only supervisor accounts can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if approve and not getattr(target, "email_verified", False):
            return Response(
                {
                    "detail": (
                        "This supervisor has not verified their Kabale email yet. "
                        "They must enter the email verification code first."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        target.is_approved = bool(approve)
        target.save(update_fields=["is_approved"])
        return Response(
            {
                "message": (
                    f"Supervisor {target.email} approved."
                    if approve
                    else f"Supervisor {target.email} approval revoked."
                ),
                "user": _main_admin_staff_row(target),
            }
        )


class MainAdminLockUserView(APIView):
    """Lock or unlock a student, supervisor, or other Main Admin (blocks sign-in)."""

    permission_classes = [IsMainAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = MainAdminLockUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target, err = _main_admin_manageable_target(
            request, serializer.validated_data["user_id"]
        )
        if err:
            return err

        lock = bool(serializer.validated_data["lock"])
        if lock:
            last_err = _guard_last_main_admin(target, locking=True)
            if last_err:
                return last_err

        target.is_active = not lock
        target.save(update_fields=["is_active"])
        label = target.email or getattr(
            getattr(target, "profile", None), "registration_number", None
        ) or target.username
        return Response(
            {
                "message": (
                    f"Account locked: {label}. They can no longer sign in."
                    if lock
                    else f"Account unlocked: {label}. They can sign in again."
                ),
                "user": (
                    _main_admin_student_row(target.profile)
                    if target.role == User.Role.STUDENT and hasattr(target, "profile")
                    else _main_admin_staff_row(target, viewer=request.user)
                ),
            }
        )


class MainAdminDeleteUserView(APIView):
    """Permanently delete a student, supervisor, or other Main Admin and related data."""

    permission_classes = [IsMainAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = MainAdminUserIdSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target, err = _main_admin_manageable_target(
            request, serializer.validated_data["user_id"]
        )
        if err:
            return err

        last_err = _guard_last_main_admin(target, locking=False)
        if last_err:
            return last_err

        message, counts = _permanently_delete_user(target)
        return Response(
            {
                "message": message,
                "deleted_user_id": serializer.validated_data["user_id"],
                "counts": counts,
            }
        )
