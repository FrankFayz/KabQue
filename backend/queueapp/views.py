from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from django.db import transaction
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
    resolve_student_contacts,
)
from .auth_utils import (
    is_kab_university_email,
    normalize_email,
    username_is_main_admin,
)
from .serializers import (
    AdminQueueEntrySerializer,
    ApproveSupervisorSerializer,
    CampusSettingsSerializer,
    CompleteStudentProfileSerializer,
    CompleteVerificationSerializer,
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
    StudentProfileSerializer,
    StudentRegisterSerializer,
    VerifyCodeSerializer,
)

User = get_user_model()


ACCOUNT_LOCKED_MESSAGE = (
    "This account has been locked by a Main Admin. You cannot sign in."
)


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
    """Approved supervisors only (desk operations)."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_queue_admin
        )


class IsMainAdmin(permissions.BasePermission):
    """System Main Admins (username contains #@admin@#)."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_main_admin
        )


def tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    payload = {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "is_approved": user.is_approved,
            "is_main_admin": user.is_main_admin,
            "is_staff": user.is_staff,
            "is_active": user.is_active,
            "full_name": user.get_full_name() or user.username,
        },
    }
    if hasattr(user, "profile"):
        payload["user"]["profile_complete"] = user.profile.is_profile_complete
        payload["user"]["registration_number"] = user.profile.registration_number
    return payload


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


def recompact_batch_positions(batch_id):
    """Keep contiguous #1…K on remaining (unapproved) students after others leave."""
    QueueEntry.ensure_nullable_position()
    for index, entry in enumerate(live_batch_entries(batch_id), start=1):
        if entry.position != index:
            entry.position = index
            entry.save(update_fields=["position", "updated_at"])


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


def return_student_to_waiting_queue(entry):
    """
    Student cannot attend their assigned day: clear the assignment and place them
    at the back of the waiting queue. They do not choose a new date — they wait
    until a supervisor notifies the next batch.
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
    # Re-join by current time so they wait behind current waiters (fair FCFS)
    entry.created_at = timezone.now()
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
        body = build_approval_message(
            full_name=entry.student.full_name,
            registration_number=entry.student.registration_number,
            scheduled_date=scheduled_date,
            secret_code=code,
            position=entry.position,
        )
        sms_body = build_approval_sms(
            full_name=entry.student.full_name,
            registration_number=entry.student.registration_number,
            scheduled_date=scheduled_date,
            secret_code=code,
            position=entry.position,
        )
        subject = f"KabQue: Rescheduled approval on {scheduled_date.isoformat()}"
        # Same profile email/phone the fresher saved after signup
        channels = deliver_student_notification(
            user=entry.student.user,
            channel=channel,
            subject=subject,
            email_body=body,
            sms_body=sms_body,
        )

    return code, channels


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
    """Live queue statuses plus lifetime approved/rejected desk totals."""
    CampusSettings.ensure_lifetime_columns()
    counts = QueueEntry.objects.aggregate(
        total=Count("id"),
        waiting=Count("id", filter=Q(status=QueueEntry.Status.WAITING)),
        notified=Count("id", filter=Q(status=QueueEntry.Status.NOTIFIED)),
        checked_in=Count("id", filter=Q(status=QueueEntry.Status.CHECKED_IN)),
        approved_live=Count("id", filter=Q(status=QueueEntry.Status.APPROVED)),
        rejected_live=Count("id", filter=Q(status=QueueEntry.Status.REJECTED)),
        skipped=Count("id", filter=Q(status=QueueEntry.Status.SKIPPED)),
    )
    approved_live = counts.pop("approved_live") or 0
    rejected_live = counts.pop("rejected_live") or 0
    try:
        campus = CampusSettings.get_solo()
        lifetime_approved = int(getattr(campus, "lifetime_approved", 0) or 0)
        lifetime_rejected = int(getattr(campus, "lifetime_rejected", 0) or 0)
    except Exception:
        lifetime_approved = 0
        lifetime_rejected = 0
    counts["approved"] = lifetime_approved + approved_live
    counts["rejected"] = lifetime_rejected + rejected_live
    counts["remaining"] = counts["waiting"] or 0
    # Unapproved students still sitting in batch result tables (carry into next notify)
    leftover_n = len(collect_batch_leftovers())
    counts["batch_leftovers"] = leftover_n
    counts["notify_pool"] = (counts["waiting"] or 0) + leftover_n
    return counts


def profile_payload(profile, request=None):
    return StudentProfileSerializer(profile, context={"request": request}).data


class RegisterView(APIView):
    """
    One signup form. Backend decides the role:
    - username containing #@admin@# → Main Admin (system control)
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

        # Main Admin: username must include the marker string
        if username_is_main_admin(identifier) or account_type == "main_admin":
            serializer = MainAdminRegisterSerializer(
                data={"username": identifier, "password": password}
            )
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            data = tokens_for_user(result["user"])
            data["message"] = "Main Admin account created."
            return Response(data, status=status.HTTP_201_CREATED)

        # Prefer explicit type when provided; otherwise detect from identifier
        if not account_type:
            account_type = "lecturer" if "@" in identifier else "student"

        if account_type in ("lecturer", "supervisor", "admin"):
            payload = {
                "email": identifier or request.data.get("email"),
                "password": password,
                "full_name": request.data.get("full_name", ""),
            }
            serializer = LecturerRegisterSerializer(data=payload)
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            # Do NOT issue tokens — supervisor cannot enter the system until approved
            return Response(
                {
                    "pending_approval": True,
                    "message": (
                        "Account created. A Main Admin must confirm you are "
                        "Kabale University staff before you can sign in."
                    ),
                    "user": {
                        "id": result["user"].id,
                        "email": result["user"].email,
                        "role": result["user"].role,
                        "is_approved": False,
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


class LoginView(APIView):
    """
    One sign-in form. Backend decides access:
    - username with #@admin@# → Main Admin
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

        # Main Admin username path (may or may not contain @ from the marker)
        if username_is_main_admin(identifier):
            user_obj = User.objects.filter(username__iexact=identifier).first()
            if user_obj is None:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            locked = _reject_if_locked(user_obj, password)
            if locked:
                return locked
            user = authenticate(username=user_obj.username, password=password)
            if user is None or not user.is_main_admin:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            data = tokens_for_user(user)
            return Response(data)

        if "@" in identifier:
            email = normalize_email(identifier)
            # Only official Kabale staff emails may sign in via email
            if not is_kab_university_email(email):
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            user_obj = User.objects.filter(email__iexact=email).first()
            if user_obj is None:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            locked = _reject_if_locked(user_obj, password)
            if locked:
                return locked
            user = authenticate(username=user_obj.username, password=password)
            if user is None:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if user.is_main_admin:
                data = tokens_for_user(user)
                return Response(data)
            if user.role != User.Role.ADMIN and not user.is_staff:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not user.is_approved:
                return Response(
                    {
                        "detail": (
                            "Your supervisor account is awaiting Main Admin approval. "
                            "You cannot access KabQue until you are confirmed as Kabale staff."
                        ),
                        "pending_approval": True,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            profile = (
                StudentProfile.objects.filter(registration_number__iexact=identifier)
                .select_related("user")
                .first()
            )
            if profile is None:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            locked = _reject_if_locked(profile.user, password)
            if locked:
                return locked
            user = authenticate(username=profile.user.username, password=password)
            if user is None:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if user.role != User.Role.STUDENT:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        data = tokens_for_user(user)
        if hasattr(user, "profile"):
            entry = get_queue_entry(user.profile)
            data["in_queue"] = entry is not None
            data["profile_complete"] = user.profile.is_profile_complete
            if entry:
                data["queue"] = QueueEntrySerializer(
                    entry, context={"request": request}
                ).data
        return Response(data)


class MeView(APIView):
    def get(self, request):
        data = tokens_for_user(request.user)
        del data["refresh"]
        del data["access"]
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
    def get(self, request):
        if not hasattr(request.user, "profile"):
            return Response(
                {"detail": "No student profile."}, status=status.HTTP_404_NOT_FOUND
            )
        if request.user.role != User.Role.STUDENT:
            return Response(
                {"detail": "Student access only."}, status=status.HTTP_403_FORBIDDEN
            )

        clear_waiting_batch_numbers()
        profile = request.user.profile
        entry = get_queue_entry(profile)
        if not entry:
            return Response(
                {
                    "in_queue": False,
                    "profile_complete": profile.is_profile_complete,
                    "profile": profile_payload(profile, request),
                }
            )
        ahead = waiting_ahead_count(entry)
        payload = QueueEntrySerializer(entry, context={"request": request}).data
        payload["in_queue"] = True
        payload["profile_complete"] = profile.is_profile_complete
        payload["students_ahead_waiting"] = ahead
        payload["has_batch_number"] = has_batch_queue_number(entry)
        return Response(payload)


class CompleteStudentProfileView(APIView):
    """Fresher completes bio + faculty details before GPS join."""

    def post(self, request):
        if not hasattr(request.user, "profile") or request.user.role != User.Role.STUDENT:
            return Response(
                {"detail": "Student access only."}, status=status.HTTP_403_FORBIDDEN
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

    @transaction.atomic
    def post(self, request):
        if not hasattr(request.user, "profile"):
            return Response(
                {"detail": "No student profile."}, status=status.HTTP_404_NOT_FOUND
            )
        if request.user.role != User.Role.STUDENT:
            return Response(
                {"detail": "Student access only."}, status=status.HTTP_403_FORBIDDEN
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

    @transaction.atomic
    def post(self, request):
        if not hasattr(request.user, "profile") or request.user.role != User.Role.STUDENT:
            return Response(
                {"detail": "Student access only."}, status=status.HTTP_403_FORBIDDEN
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
                "message": (
                    "You have been returned to the waiting queue. "
                    "You cannot choose a priority date — please wait until "
                    "the supervisor notifies the next approval schedule."
                ),
                "queue": payload,
            }
        )


class StudentLeaveQueueView(APIView):
    """Remove the student from the queue (cancel assignment / leave for other priorities)."""

    @transaction.atomic
    def post(self, request):
        if not hasattr(request.user, "profile") or request.user.role != User.Role.STUDENT:
            return Response(
                {"detail": "Student access only."}, status=status.HTTP_403_FORBIDDEN
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

        remove_queue_entry(entry)
        profile = request.user.profile
        return Response(
            {
                "message": "You have left the queue.",
                "in_queue": False,
                "profile_complete": profile.is_profile_complete,
                "profile": profile_payload(profile, request),
            }
        )


class AdminDashboardView(APIView):
    permission_classes = [IsQueueAdmin]

    def get(self, request):
        clear_waiting_batch_numbers()
        counts = build_queue_counts()
        by_faculty = list(
            QueueEntry.objects.values("student__faculty")
            .annotate(count=Count("id"))
            .order_by("-count", "student__faculty")
        )
        by_programme = list(
            QueueEntry.objects.values("student__faculty", "student__programme")
            .annotate(count=Count("id"))
            .order_by("student__faculty", "-count", "student__programme")
        )
        # Only students currently in the queue (join adds, leave / approve removes).
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
        campus = CampusSettings.get_solo()
        return Response(
            {
                "counts": counts,
                "by_faculty": by_faculty,
                "by_programme": by_programme,
                "campus": CampusSettingsSerializer(campus).data,
            }
        )


class AdminQueueListView(APIView):
    permission_classes = [IsQueueAdmin]

    def get(self, request):
        clear_waiting_batch_numbers()
        qs = (
            QueueEntry.objects.select_related("student", "student__user")
            .all()
            .order_by("created_at", "id")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        search = (request.query_params.get("search") or "").strip()
        if search:
            # Registration number is the system primary student key — search only on that.
            qs = qs.filter(
                student__registration_number__icontains=search.upper()
            )
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

    @transaction.atomic
    def post(self, request):
        serializer = NotifyBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data["batch_size"]
        scheduled_date = serializer.validated_data["scheduled_date"]
        channel = serializer.validated_data["channel"]

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
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        take_leftover = min(requested, leftover_available)
        take_waiting = min(requested - take_leftover, waiting_available)
        carry_entries = leftovers[:take_leftover]
        waiting_entries = list(waiting_qs[:take_waiting])
        shortage = requested > pool_available

        # Leftovers leave their old day tables; waiting rows clear stale numbers
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

        results = []
        email_ok = email_fail = sms_ok = sms_fail = 0
        sms_errors = []
        now = timezone.now()
        batch_number = 0

        def append_delivery(entry, code, channels_tried, number):
            nonlocal email_ok, email_fail, sms_ok, sms_fail
            body = build_approval_message(
                full_name=entry.student.full_name,
                registration_number=entry.student.registration_number,
                scheduled_date=scheduled_date,
                secret_code=code,
                position=number,
            )
            sms_body = build_approval_sms(
                full_name=entry.student.full_name,
                registration_number=entry.student.registration_number,
                scheduled_date=scheduled_date,
                secret_code=code,
                position=number,
            )
            for attempt in channels_tried:
                if attempt["channel"] == "email":
                    if attempt["success"]:
                        email_ok += 1
                    else:
                        email_fail += 1
                elif attempt["channel"] == "sms":
                    if attempt["success"]:
                        sms_ok += 1
                    else:
                        sms_fail += 1
                        err = attempt.get("error") or ""
                        if err and err not in sms_errors:
                            sms_errors.append(err)
                NotificationLog.objects.create(
                    batch=batch,
                    queue_entry=entry,
                    channel=attempt["channel"],
                    destination=attempt.get("destination") or "",
                    body=body if attempt["channel"] == "email" else sms_body,
                    success=attempt["success"],
                    error_message=attempt.get("error") or "",
                )
            results.append(serialize_batch_student(entry, channels=channels_tried))

        # 1) Carry remaining unapproved from prior batch tables — get numbers first
        for locked in carry_entries:
            entry = (
                QueueEntry.objects.select_for_update()
                .select_related("student", "student__user")
                .filter(pk=locked.pk)
                .first()
            )
            if entry is None or entry.status not in ACTIVE_BATCH_STATUSES:
                continue
            batch_number += 1
            code, channels_tried = apply_reschedule(
                entry,
                scheduled_date,
                notify=True,
                channel=channel,
                position=batch_number,
            )
            entry.refresh_from_db()
            append_delivery(entry, code, channels_tried, batch_number)

        # 2) Fill remaining seats from waiting (arrival order)
        for locked in waiting_entries:
            entry = (
                QueueEntry.objects.select_for_update()
                .select_related("student", "student__user")
                .filter(pk=locked.pk, status=QueueEntry.Status.WAITING)
                .first()
            )
            if entry is None:
                continue

            batch_number += 1
            code = entry.assign_secret_code()
            entry.status = QueueEntry.Status.NOTIFIED
            entry.scheduled_date = scheduled_date
            entry.notified_at = now
            entry.position = batch_number
            entry.save(
                update_fields=[
                    "secret_code",
                    "status",
                    "scheduled_date",
                    "notified_at",
                    "position",
                    "updated_at",
                ]
            )
            subject = f"KabQue: Document approval on {scheduled_date.isoformat()}"
            body = build_approval_message(
                full_name=entry.student.full_name,
                registration_number=entry.student.registration_number,
                scheduled_date=scheduled_date,
                secret_code=code,
                position=batch_number,
            )
            sms_body = build_approval_sms(
                full_name=entry.student.full_name,
                registration_number=entry.student.registration_number,
                scheduled_date=scheduled_date,
                secret_code=code,
                position=batch_number,
            )
            channels_tried = deliver_student_notification(
                user=entry.student.user,
                channel=channel,
                subject=subject,
                email_body=body,
                sms_body=sms_body,
            )
            append_delivery(entry, code, channels_tried, batch_number)

        if not results:
            return Response(
                {
                    "detail": "No students could be notified. Try again.",
                    "requested": requested,
                    "available": pool_available,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        if channel in ("email", "both"):
            message += f" Emails: {email_ok}."
            if email_fail:
                message += f" Email failed: {email_fail}."
        if channel in ("sms", "both"):
            message += f" SMS: {sms_ok}."
            if sms_fail:
                message += f" SMS failed: {sms_fail}."

        return Response(
            {
                "batch": NotificationBatchSerializer(batch).data,
                "message": message,
                "requested": requested,
                "available": pool_available,
                "carried_from_batch": carried_count,
                "from_waiting": max(0, len(results) - carried_count),
                "notified_count": len(results),
                "emails_sent": email_ok,
                "emails_failed": email_fail,
                "sms_sent": sms_ok,
                "sms_failed": sms_fail,
                "sms_errors": sms_errors[:3],
                "sms_configured": bool(
                    (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
                ),
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

        today = timezone.localdate()
        scheduled = entry.scheduled_date
        schedule_is_today = bool(scheduled and scheduled == today)
        if not scheduled:
            schedule_note = "No approval day is assigned on this record."
        elif schedule_is_today:
            schedule_note = "Confirmed: this fresher is scheduled for today."
        else:
            schedule_note = (
                f"Scheduled day is {scheduled.isoformat()}, not today ({today.isoformat()})."
            )

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
    """Approve / reject / mark no-show after identity confirmation."""

    permission_classes = [IsQueueAdmin]

    @transaction.atomic
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
                {"detail": f"Already finalized as {entry.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        decision = serializer.validated_data["decision"]
        if (
            decision in ("approved", "rejected")
            and entry.status
            not in (
                QueueEntry.Status.CHECKED_IN,
                QueueEntry.Status.NOTIFIED,
            )
        ):
            return Response(
                {
                    "detail": "Confirm identity with the secret code before approving or rejecting."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = serializer.validated_data.get("notes", "")
        removed_from_queue = False
        entry_payload = None
        removed_queue_entry_id = entry.id
        linked_batch_ids = batch_ids_for_entry(entry.id)

        try:
            if decision in ("approved", "rejected"):
                # Record desk outcome, then leave the live queue + batch result table.
                CampusSettings.ensure_lifetime_columns()
                campus = CampusSettings.get_solo()
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
                entry.status = decision
                entry.verified_at = timezone.now()
                entry.verification_notes = notes
                entry.save(
                    update_fields=[
                        "status",
                        "verified_at",
                        "verification_notes",
                        "updated_at",
                    ]
                )
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
            "approved": "Approved — documents accepted. Student removed from the live queue and batch table.",
            "rejected": "Rejected — documents not accepted. Student removed from the live queue and batch table.",
            "skipped": "Marked as no-show. Student stays in the batch for end-of-day reschedule.",
        }

        active_batch = None
        batch_payload = None
        if linked_batch_ids:
            # Prefer the most recent linked batch that still has remaining students
            for bid in sorted(linked_batch_ids, reverse=True):
                batch = NotificationBatch.objects.filter(id=bid).first()
                if not batch:
                    continue
                live = live_batch_entries(bid)
                if decision in ("approved", "rejected") or live:
                    active_batch = batch
                    batch_payload = build_live_batch_payload(batch)
                    break
            if active_batch is None and linked_batch_ids:
                batch = NotificationBatch.objects.filter(id=linked_batch_ids[-1]).first()
                if batch:
                    active_batch = batch
                    batch_payload = build_live_batch_payload(batch)

        return Response(
            {
                "message": labels.get(decision, f"Marked as {decision}."),
                "entry": entry_payload,
                "removed_from_queue": removed_from_queue,
                "removed_queue_entry_id": removed_queue_entry_id
                if removed_from_queue
                else None,
                "counts": counts,
                "batch": batch_payload,
            }
        )


class AdminRescheduleView(APIView):
    permission_classes = [IsQueueAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry_id = serializer.validated_data.get("queue_entry_id")
        if not entry_id:
            return Response(
                {"detail": "queue_entry_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entry = (
            QueueEntry.objects.select_related("student", "student__user")
            .filter(id=entry_id)
            .first()
        )
        if not entry:
            return Response(
                {"detail": "Queue entry not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if not can_reschedule_entry(entry):
            return Response(
                {"detail": "This entry cannot be rescheduled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Leave the day's leftover batch table — they're moved to a new schedule
        linked = batch_ids_for_entry(entry.id)
        detach_entry_from_batches(entry)
        for bid in linked:
            recompact_batch_positions(bid)

        code, channels = apply_reschedule(
            entry, serializer.validated_data["scheduled_date"], notify=True
        )
        entry.refresh_from_db()
        return Response(
            {
                "message": f"Rescheduled to {serializer.validated_data['scheduled_date']}.",
                "secret_code": code,
                "channels": channels,
                "entry": AdminQueueEntrySerializer(entry).data,
            }
        )


class AdminActiveBatchView(APIView):
    """
    Latest notification batch that still has students awaiting desk completion.
    Approved/rejected students are already gone from this view.
    """

    permission_classes = [IsQueueAdmin]

    def get(self, request):
        batch_id = request.query_params.get("batch_id")
        if batch_id:
            batch = NotificationBatch.objects.filter(id=batch_id).first()
            if not batch:
                return Response(
                    {"detail": "Batch not found."}, status=status.HTTP_404_NOT_FOUND
                )
            return Response(build_live_batch_payload(batch))

        # Prefer the newest batch that still has remaining (unapproved) students
        for batch in NotificationBatch.objects.order_by("-created_at", "-id")[:40]:
            if live_batch_entries(batch.id):
                return Response(build_live_batch_payload(batch))

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

    @transaction.atomic
    def post(self, request):
        serializer = BatchRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch_id = serializer.validated_data["batch_id"]
        requested = serializer.validated_data["count"]
        scheduled_date = serializer.validated_data["scheduled_date"]
        channel = serializer.validated_data.get("channel") or "both"

        source_batch = NotificationBatch.objects.filter(id=batch_id).first()
        if not source_batch:
            return Response(
                {"detail": "Batch not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Only students still in the batch table (not approved / rejected)
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

        # They leave the old day's batch table, then get numbers on the new day
        detach_entries_from_batch(batch_id, move_ids)

        new_batch = NotificationBatch.objects.create(
            created_by=request.user,
            scheduled_date=scheduled_date,
            batch_size=len(to_move),
            channel=channel,
            message_template=f"Reschedule remaining from batch {batch_id}",
        )

        results = []
        email_ok = email_fail = sms_ok = sms_fail = 0
        sms_errors = []

        for index, entry in enumerate(to_move, start=1):
            code, channels_tried = apply_reschedule(
                entry,
                scheduled_date,
                notify=True,
                channel=channel,
                position=index,
            )
            entry.refresh_from_db()

            body = build_approval_message(
                full_name=entry.student.full_name,
                registration_number=entry.student.registration_number,
                scheduled_date=scheduled_date,
                secret_code=code,
                position=index,
            )
            sms_body = build_approval_sms(
                full_name=entry.student.full_name,
                registration_number=entry.student.registration_number,
                scheduled_date=scheduled_date,
                secret_code=code,
                position=index,
            )

            for attempt in channels_tried:
                if attempt["channel"] == "email":
                    if attempt["success"]:
                        email_ok += 1
                    else:
                        email_fail += 1
                elif attempt["channel"] == "sms":
                    if attempt["success"]:
                        sms_ok += 1
                    else:
                        sms_fail += 1
                        err = attempt.get("error") or ""
                        if err and err not in sms_errors:
                            sms_errors.append(err)

                NotificationLog.objects.create(
                    batch=new_batch,
                    queue_entry=entry,
                    channel=attempt["channel"],
                    destination=attempt.get("destination") or "",
                    body=body if attempt["channel"] == "email" else sms_body,
                    success=attempt["success"],
                    error_message=attempt.get("error") or "",
                )

            results.append(serialize_batch_student(entry, channels=channels_tried))

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
        if channel in ("email", "both"):
            message += f" Emails: {email_ok}."
            if email_fail:
                message += f" Email failed: {email_fail}."
        if channel in ("sms", "both"):
            message += f" SMS: {sms_ok}."
            if sms_fail:
                message += f" SMS failed: {sms_fail}."

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
                "emails_sent": email_ok,
                "emails_failed": email_fail,
                "sms_sent": sms_ok,
                "sms_failed": sms_fail,
                "sms_errors": sms_errors[:3],
                "sms_configured": bool(
                    (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
                ),
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


def _main_admin_student_row(profile):
    try:
        entry = profile.queue_entry
    except QueueEntry.DoesNotExist:
        entry = None
    if entry is None:
        verification_status = "not_in_queue"
        queue_position = None
        scheduled_date = None
    else:
        verification_status = entry.status
        queue_position = entry.position
        scheduled_date = entry.scheduled_date
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
        "date_joined": user.date_joined,
        "registration_number": profile.registration_number,
        "faculty": profile.faculty or "",
        "programme": profile.programme or "",
        "profile_complete": profile.is_profile_complete,
        "verification_status": verification_status,
        "queue_position": (
            None
            if verification_status == QueueEntry.Status.WAITING
            else queue_position
        ),
        "scheduled_date": scheduled_date,
    }


def _main_admin_staff_row(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "phone": user.phone or "",
        "full_name": user.get_full_name() or user.username,
        "role": user.role,
        "is_approved": user.is_approved,
        "is_active": user.is_active,
        "is_locked": not user.is_active,
        "date_joined": user.date_joined,
        "registration_number": "",
        "faculty": "",
        "programme": "",
        "profile_complete": True,
        "verification_status": "approved" if user.is_approved else "pending",
        "queue_position": None,
        "scheduled_date": None,
    }


def _main_admin_manageable_target(request, user_id):
    """
    Resolve a student or supervisor the current Main Admin may manage.
    Returns (user, error_response).
    """
    target = User.objects.filter(pk=user_id).first()
    if not target:
        return None, Response(
            {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
        )
    if target.pk == request.user.pk:
        return None, Response(
            {"detail": "You cannot modify your own account here."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if target.is_main_admin or target.role == User.Role.MAIN_ADMIN:
        return None, Response(
            {"detail": "Main Admin accounts cannot be locked or deleted here."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if target.role not in (User.Role.STUDENT, User.Role.ADMIN):
        return None, Response(
            {"detail": "Only students and supervisors can be managed."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return target, None


def _permanently_delete_user(target: User) -> str:
    """Delete user and related KabQue data (profile, queue, logs)."""
    role_label = "student" if target.role == User.Role.STUDENT else "supervisor"
    label = target.email or target.username
    if target.role == User.Role.STUDENT:
        try:
            label = target.profile.registration_number
        except StudentProfile.DoesNotExist:
            pass

    if hasattr(target, "profile"):
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
                NotificationLog.ensure_nullable_queue_entry()
                NotificationLog.objects.filter(queue_entry_id=entry.id).update(
                    queue_entry=None
                )
                entry.delete()

    # Cascades StudentProfile; NotificationBatch.created_by is SET_NULL
    target.delete()
    return f"{role_label.capitalize()} {label} permanently deleted."


class MainAdminOverviewView(APIView):
    """Totals for the Main Admin control page."""

    permission_classes = [IsMainAdmin]

    def get(self, request):
        freshers = StudentProfile.objects.count()
        supervisors = User.objects.filter(role=User.Role.ADMIN).exclude(
            role=User.Role.MAIN_ADMIN
        )
        # Role.ADMIN users only; also catch marker usernames for main admins
        main_admins = User.objects.filter(
            Q(role=User.Role.MAIN_ADMIN) | Q(username__contains="#@admin@#")
        ).distinct()
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
        qs = (
            User.objects.filter(
                Q(role=User.Role.MAIN_ADMIN) | Q(username__contains="#@admin@#")
            )
            .distinct()
            .order_by("-date_joined")
        )
        rows = [_main_admin_staff_row(u) for u in qs]
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
        rows = [_main_admin_staff_row(u) for u in qs]
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
    """Lock or unlock a student / supervisor account (blocks sign-in when locked)."""

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
                    else _main_admin_staff_row(target)
                ),
            }
        )


class MainAdminDeleteUserView(APIView):
    """Permanently delete a student or supervisor and related KabQue data."""

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

        message = _permanently_delete_user(target)
        return Response({"message": message, "deleted_user_id": serializer.validated_data["user_id"]})
