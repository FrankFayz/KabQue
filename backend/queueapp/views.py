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
    normalize_phone,
    send_email_notification,
    send_sms_notification,
)
from .auth_utils import is_kab_university_email, kab_email_error_message, normalize_email
from .serializers import (
    AdminQueueEntrySerializer,
    CampusSettingsSerializer,
    CompleteStudentProfileSerializer,
    CompleteVerificationSerializer,
    JoinQueueSerializer,
    LecturerRegisterSerializer,
    LoginSerializer,
    NotificationBatchSerializer,
    NotifyBatchSerializer,
    QueueEntryIdSerializer,
    QueueEntrySerializer,
    RescheduleSerializer,
    StudentProfileSerializer,
    StudentRegisterSerializer,
    VerifyCodeSerializer,
)

User = get_user_model()


class IsQueueAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_queue_admin
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


def apply_reschedule(entry, scheduled_date, *, notify=True):
    code = entry.assign_secret_code()
    entry.status = QueueEntry.Status.NOTIFIED
    entry.scheduled_date = scheduled_date
    entry.notified_at = timezone.now()
    entry.checked_in_at = None
    entry.verified_at = None
    entry.verification_notes = ""
    entry.save(
        update_fields=[
            "secret_code",
            "status",
            "scheduled_date",
            "notified_at",
            "checked_in_at",
            "verified_at",
            "verification_notes",
            "updated_at",
        ]
    )

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
        email = entry.student.user.email
        phone = entry.student.user.phone
        if email:
            ok, err = send_email_notification(email, subject, body)
            channels.append({"channel": "email", "success": ok, "error": err})
        if phone:
            ok, err = send_sms_notification(phone, sms_body)
            channels.append({"channel": "sms", "success": ok, "error": err})

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
    return counts


def profile_payload(profile, request=None):
    return StudentProfileSerializer(profile, context={"request": request}).data


class RegisterView(APIView):
    """
    One signup form. Backend decides the role:
    - registration number → fresher (student dashboard)
    - email ending @kab.ac.ug → lecturer / supervisor (admin dashboard)
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        identifier = (
            request.data.get("identifier")
            or request.data.get("registration_number")
            or request.data.get("email")
            or ""
        )
        identifier = str(identifier).strip()
        password = request.data.get("password")
        account_type = (request.data.get("account_type") or "").strip().lower()

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
            data = tokens_for_user(result["user"])
            data["message"] = "Welcome to KabQue."
            return Response(data, status=status.HTTP_201_CREATED)

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
    - registration number → fresher
    - @kab.ac.ug email → lecturer / supervisor
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"].strip()
        password = serializer.validated_data["password"]
        user = None

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

            user = authenticate(username=user_obj.username, password=password)
            if user is None:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not user.is_queue_admin:
                return Response(
                    {"detail": "Invalid credentials."},
                    status=status.HTTP_401_UNAUTHORIZED,
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
        payload["has_batch_number"] = entry.position is not None
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

        payload = QueueEntrySerializer(entry, context={"request": request}).data
        payload["in_queue"] = True
        payload["students_ahead_waiting"] = waiting_ahead_count(entry)
        payload["has_batch_number"] = False
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
    """Fresher picks a new approval day when they cannot attend the assigned one."""

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
                {"detail": "No assigned day to reschedule."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code, channels = apply_reschedule(
            entry, serializer.validated_data["scheduled_date"], notify=True
        )
        entry.refresh_from_db()
        payload = QueueEntrySerializer(entry, context={"request": request}).data
        payload["in_queue"] = True
        return Response(
            {
                "message": f"Rescheduled to {serializer.validated_data['scheduled_date']}.",
                "secret_code": code,
                "channels": channels,
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
    Notify the next waiting students in arrival order (first come, first served).
    Assigns batch queue numbers 1…N for the size the supervisor requests.
    """

    permission_classes = [IsQueueAdmin]

    @transaction.atomic
    def post(self, request):
        serializer = NotifyBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data["batch_size"]
        scheduled_date = serializer.validated_data["scheduled_date"]
        channel = serializer.validated_data["channel"]

        waiting_qs = (
            QueueEntry.objects.select_for_update()
            .select_related("student", "student__user")
            .filter(status=QueueEntry.Status.WAITING)
            .order_by("created_at", "id")
        )
        available = waiting_qs.count()
        if available == 0:
            return Response(
                {
                    "detail": "No students remaining in the waiting queue.",
                    "requested": requested,
                    "available": 0,
                    "remaining": 0,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        take = min(requested, available)
        entries = list(waiting_qs[:take])
        shortage = requested > available

        batch = NotificationBatch.objects.create(
            created_by=request.user,
            scheduled_date=scheduled_date,
            batch_size=len(entries),
            channel=channel,
        )

        results = []
        email_ok = 0
        email_fail = 0
        sms_ok = 0
        sms_fail = 0
        sms_errors = []
        now = timezone.now()
        for batch_number, entry in enumerate(entries, start=1):
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
            subject = f"KabQue: Document approval on {scheduled_date.isoformat()}"

            channels_tried = []
            if channel in ("email", "both"):
                ok, err = send_email_notification(
                    entry.student.user.email, subject, body
                )
                if ok:
                    email_ok += 1
                else:
                    email_fail += 1
                NotificationLog.objects.create(
                    batch=batch,
                    queue_entry=entry,
                    channel="email",
                    destination=entry.student.user.email or "",
                    body=body,
                    success=ok,
                    error_message=err,
                )
                channels_tried.append({"channel": "email", "success": ok, "error": err})

            if channel in ("sms", "both"):
                phone = normalize_phone(entry.student.user.phone)
                ok, err = send_sms_notification(phone, sms_body)
                if ok:
                    sms_ok += 1
                else:
                    sms_fail += 1
                    if err and err not in sms_errors:
                        sms_errors.append(err)
                NotificationLog.objects.create(
                    batch=batch,
                    queue_entry=entry,
                    channel="sms",
                    destination=phone or entry.student.user.phone or "",
                    body=sms_body,
                    success=ok,
                    error_message=err,
                )
                channels_tried.append({"channel": "sms", "success": ok, "error": err})

            results.append(
                {
                    "position": batch_number,
                    "registration_number": entry.student.registration_number,
                    "full_name": entry.student.full_name,
                    "email": entry.student.user.email or "",
                    "phone": normalize_phone(entry.student.user.phone)
                    or entry.student.user.phone
                    or "",
                    "secret_code": code,
                    "scheduled_date": scheduled_date.isoformat(),
                    "channels": channels_tried,
                }
            )

        remaining = QueueEntry.objects.filter(status=QueueEntry.Status.WAITING).count()
        if shortage:
            message = (
                f"Only {available} student(s) were waiting. "
                f"Assigned queue numbers 1–{len(results)} and notified them "
                f"(you requested {requested}). {remaining} still waiting."
            )
        else:
            message = (
                f"Assigned queue numbers 1–{len(results)} to the next "
                f"{len(results)} student(s) in arrival order and notified them. "
                f"{remaining} remaining to notify."
            )
        if channel in ("email", "both"):
            message += f" Emails sent: {email_ok}."
            if email_fail:
                message += f" Email failures: {email_fail}."
        if channel in ("sms", "both"):
            message += f" SMS sent: {sms_ok}."
            if sms_fail:
                hint = sms_errors[0] if sms_errors else (
                    "Check student phone (+country code) and that the MySMSGate "
                    "Android app is online with the same account as MYSMSGATE_API_KEY on Render."
                )
                message += f" SMS failures: {sms_fail}. Reason: {hint}"

        return Response(
            {
                "batch": NotificationBatchSerializer(batch).data,
                "message": message,
                "requested": requested,
                "available": available,
                "notified_count": len(results),
                "emails_sent": email_ok,
                "emails_failed": email_fail,
                "sms_sent": sms_ok,
                "sms_failed": sms_fail,
                "sms_errors": sms_errors,
                "sms_configured": bool(
                    (getattr(settings, "MYSMSGATE_API_KEY", "") or "").strip()
                ),
                "shortage": shortage,
                "remaining": remaining,
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

        try:
            if decision in ("approved", "rejected"):
                # Record desk outcome, then leave the live queue.
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
            "approved": "Approved — documents accepted. Student removed from the live queue.",
            "rejected": "Rejected — documents not accepted. Student removed from the live queue.",
            "skipped": "Marked as no-show. Student stays in the queue for a return visit.",
        }
        return Response(
            {
                "message": labels.get(decision, f"Marked as {decision}."),
                "entry": entry_payload,
                "removed_from_queue": removed_from_queue,
                "counts": counts,
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
