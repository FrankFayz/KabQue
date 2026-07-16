from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .auth_utils import (
    email_already_registered,
    is_kab_university_email,
    kab_email_error_message,
    normalize_email,
    parse_main_admin_identifier,
    phone_already_registered,
    username_is_main_admin,
)
from .geo import validate_join_gps
from .models import CampusSettings, NotificationBatch, QueueEntry, StudentProfile
from .phones import validate_east_africa_phone
from .registration import validate_kabale_registration_number

User = get_user_model()


class StudentRegisterSerializer(serializers.Serializer):
    """Fresher account: registration number + password only."""

    registration_number = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_registration_number(self, value):
        try:
            reg = validate_kabale_registration_number(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if username_is_main_admin(reg) or username_is_main_admin(reg.lower()):
            raise serializers.ValidationError("Unable to create account.")
        if StudentProfile.objects.filter(registration_number__iexact=reg).exists():
            raise serializers.ValidationError(
                "This registration number is already registered."
            )
        return reg

    @transaction.atomic
    def create(self, validated_data):
        reg = validated_data["registration_number"]
        username = reg.lower().replace("/", "_")
        if User.objects.filter(username=username).exists():
            raise serializers.ValidationError(
                {"registration_number": "This registration number is already registered."}
            )

        user = User.objects.create_user(
            username=username,
            email="",
            password=validated_data["password"],
            role=User.Role.STUDENT,
            is_approved=True,
            email_verified=True,
        )
        profile = StudentProfile.objects.create(
            user=user,
            registration_number=reg,
            full_name="",
            faculty="",
            programme="",
        )
        return {"user": user, "profile": profile}


class MainAdminRegisterSerializer(serializers.Serializer):
    """Main Admin: must be local@kab.ac.ug#@admin@# (marker after Kabale email)."""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_username(self, value):
        parsed = parse_main_admin_identifier(value)
        if not parsed:
            raise serializers.ValidationError(
                "Main Admin account must be your Kabale email followed by #@admin@# "
                "(example: name@kab.ac.ug#@admin@#)."
            )
        username, contact_email = parsed
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("This Main Admin account is already registered.")
        if email_already_registered(contact_email):
            raise serializers.ValidationError(
                "That Kabale email is already used by another KabQue account."
            )
        return username

    @transaction.atomic
    def create(self, validated_data):
        username = validated_data["username"]
        parsed = parse_main_admin_identifier(username)
        contact_email = parsed[1] if parsed else ""
        user = User.objects.create_user(
            username=username,
            email=contact_email,
            password=validated_data["password"],
            role=User.Role.MAIN_ADMIN,
            is_staff=False,
            is_approved=True,
            email_verified=False,
        )
        return {"user": user}


class LecturerRegisterSerializer(serializers.Serializer):
    """Lecturer / supervisor account: official @kab.ac.ug email + password.

    Account is created inactive for desk access until a Main Admin approves
    that the person is Kabale staff.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value):
        email = normalize_email(value)
        if not is_kab_university_email(email):
            raise serializers.ValidationError(kab_email_error_message())
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "This university email is already registered to another account."
            )
        if User.objects.filter(username__iexact=email).exists():
            raise serializers.ValidationError(
                "This university email is already registered to another account."
            )
        return email

    @transaction.atomic
    def create(self, validated_data):
        email = validated_data["email"]
        full_name = (validated_data.get("full_name") or "").strip()
        parts = full_name.split() if full_name else []
        first = parts[0] if parts else ""
        last = " ".join(parts[1:]) if len(parts) > 1 else ""

        user = User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
            first_name=first,
            last_name=last,
            role=User.Role.ADMIN,
            is_staff=True,
            is_approved=False,
            email_verified=False,
        )
        return {"user": user}

class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(
        help_text="Student registration number, or lecturer @kab.ac.ug email"
    )
    password = serializers.CharField(write_only=True)


class CompleteStudentProfileSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    faculty = serializers.CharField(max_length=150)
    programme = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)

    def validate(self, attrs):
        email = normalize_email(attrs.get("email") or "")
        phone_raw = (attrs.get("phone") or "").strip()

        attrs["full_name"] = (attrs.get("full_name") or "").strip()
        attrs["faculty"] = (attrs.get("faculty") or "").strip()
        attrs["programme"] = (attrs.get("programme") or "").strip()

        errors = {}
        if not attrs["full_name"]:
            errors["full_name"] = "Full name is required."
        if not attrs["faculty"]:
            errors["faculty"] = "Faculty is required."
        if not attrs["programme"]:
            errors["programme"] = "Programme is required."
        if not email:
            errors["email"] = (
                "Email is required for notifications and password resets."
            )
        if not phone_raw:
            errors["phone"] = "Telephone number is required for SMS notifications."

        try:
            phone = validate_east_africa_phone(phone_raw) if phone_raw else ""
        except ValueError as exc:
            errors["phone"] = str(exc)
            phone = ""

        attrs["email"] = email
        attrs["phone"] = phone

        user = self.context["request"].user
        if email and email_already_registered(email, exclude_user_id=user.pk):
            errors["email"] = (
                "This email already belongs to another account. Use a different email."
            )
        if phone and phone_already_registered(phone, exclude_user_id=user.pk):
            errors["phone"] = (
                "This telephone number already belongs to another account. "
                "Use a different number."
            )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        user = self.context["request"].user
        profile = user.profile
        data = self.validated_data

        profile.full_name = data["full_name"]
        profile.faculty = data["faculty"]
        profile.programme = data["programme"]
        profile.save(update_fields=["full_name", "faculty", "programme"])

        user.email = data["email"]
        user.phone = data["phone"]
        parts = data["full_name"].split()
        user.first_name = parts[0]
        user.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        try:
            user.save(update_fields=["email", "phone", "first_name", "last_name"])
        except Exception as exc:
            # DB unique constraints (race-safe) → clear field-level errors
            from django.db import IntegrityError

            if isinstance(exc, IntegrityError):
                msg = str(exc).lower()
                if "email" in msg:
                    raise serializers.ValidationError(
                        {
                            "email": (
                                "This email already belongs to another account. "
                                "Use a different email."
                            )
                        }
                    ) from exc
                if "phone" in msg:
                    raise serializers.ValidationError(
                        {
                            "phone": (
                                "This telephone number already belongs to another account. "
                                "Use a different number."
                            )
                        }
                    ) from exc
            raise

        return profile


class JoinQueueSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    accuracy = serializers.FloatField(required=False, allow_null=True)
    altitude = serializers.FloatField(required=False, allow_null=True)
    altitude_accuracy = serializers.FloatField(required=False, allow_null=True)
    speed = serializers.FloatField(required=False, allow_null=True)
    heading = serializers.FloatField(required=False, allow_null=True)
    captured_at = serializers.FloatField(required=False, allow_null=True)
    sample_count = serializers.IntegerField(required=False, allow_null=True)
    sample_spread_m = serializers.FloatField(required=False, allow_null=True)
    samples = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        max_length=6,
    )

    def validate(self, attrs):
        try:
            distance, _radius, accuracy = validate_join_gps(
                attrs["latitude"],
                attrs["longitude"],
                accuracy=attrs.get("accuracy"),
                samples=attrs.get("samples") or [],
            )
        except ValueError as exc:
            raise serializers.ValidationError({"location": str(exc)}) from exc

        attrs["_distance_meters"] = distance
        attrs["_accuracy_meters"] = accuracy
        return attrs


class StudentProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    profile_complete = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = (
            "registration_number",
            "full_name",
            "faculty",
            "programme",
            "email",
            "phone",
            "registered_at",
            "profile_complete",
            "desk_outcome",
        )

    def get_profile_complete(self, obj):
        return obj.is_profile_complete


class QueueEntrySerializer(serializers.ModelSerializer):
    student = StudentProfileSerializer(read_only=True)
    secret_code = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()

    class Meta:
        model = QueueEntry
        fields = (
            "id",
            "position",
            "status",
            "scheduled_date",
            "notified_at",
            "checked_in_at",
            "verified_at",
            "verification_notes",
            "secret_code",
            "created_at",
            "student",
        )

    def get_position(self, obj):
        # Batch numbers exist only after notify — never for waiting joiners
        if obj.status == QueueEntry.Status.WAITING:
            return None
        return obj.position

    def get_secret_code(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        if request.user.is_queue_admin:
            return obj.secret_code or None
        if (
            hasattr(request.user, "profile")
            and obj.student_id == request.user.profile.id
            and obj.status
            in (
                QueueEntry.Status.NOTIFIED,
                QueueEntry.Status.CHECKED_IN,
                QueueEntry.Status.APPROVED,
                QueueEntry.Status.REJECTED,
            )
        ):
            return obj.secret_code or None
        return None


class AdminQueueEntrySerializer(serializers.ModelSerializer):
    student = StudentProfileSerializer(read_only=True)
    position = serializers.SerializerMethodField()

    class Meta:
        model = QueueEntry
        fields = (
            "id",
            "position",
            "status",
            "scheduled_date",
            "notified_at",
            "checked_in_at",
            "verified_at",
            "verification_notes",
            "secret_code",
            "created_at",
            "student",
        )

    def get_position(self, obj):
        if obj.status == QueueEntry.Status.WAITING:
            return None
        return obj.position


class NotifyBatchSerializer(serializers.Serializer):
    batch_size = serializers.IntegerField(min_value=1, max_value=500)
    scheduled_date = serializers.DateField()
    channel = serializers.ChoiceField(
        choices=["email", "sms", "both"], default="both"
    )


class VerifyCodeSerializer(serializers.Serializer):
    secret_code = serializers.CharField(max_length=16)


class CompleteVerificationSerializer(serializers.Serializer):
    queue_entry_id = serializers.IntegerField()
    decision = serializers.ChoiceField(
        choices=["approved", "rejected", "back_to_queue"]
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class RescheduleSerializer(serializers.Serializer):
    scheduled_date = serializers.DateField()
    queue_entry_id = serializers.IntegerField(required=False)
    channel = serializers.ChoiceField(
        choices=["email", "sms", "both"], default="both", required=False
    )

    def validate_scheduled_date(self, value):
        today = timezone.localdate()
        if value < today:
            raise serializers.ValidationError("Choose today or a future date.")
        return value


class BatchRescheduleSerializer(serializers.Serializer):
    """Reschedule the first N students from a notified batch onto a new day."""

    batch_id = serializers.IntegerField()
    count = serializers.IntegerField(min_value=1, max_value=500)
    scheduled_date = serializers.DateField()
    channel = serializers.ChoiceField(
        choices=["email", "sms", "both"], default="both", required=False
    )

    def validate_scheduled_date(self, value):
        today = timezone.localdate()
        if value < today:
            raise serializers.ValidationError("Choose today or a future date.")
        return value


class QueueEntryIdSerializer(serializers.Serializer):
    queue_entry_id = serializers.IntegerField(required=False)


class CampusSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampusSettings
        fields = (
            "name",
            "latitude",
            "longitude",
            "radius_meters",
            "gps_enforcement",
            "default_daily_batch_size",
            "updated_at",
        )


class NotificationBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationBatch
        fields = (
            "id",
            "scheduled_date",
            "batch_size",
            "channel",
            "created_at",
        )


class MainAdminUserSerializer(serializers.Serializer):
    """Read-only user rows for the Main Admin control page."""

    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    full_name = serializers.CharField()
    role = serializers.CharField()
    is_approved = serializers.BooleanField()
    date_joined = serializers.DateTimeField()
    # Fresher-only fields
    registration_number = serializers.CharField(required=False, allow_blank=True)
    faculty = serializers.CharField(required=False, allow_blank=True)
    programme = serializers.CharField(required=False, allow_blank=True)
    profile_complete = serializers.BooleanField(required=False)
    verification_status = serializers.CharField(required=False, allow_blank=True)
    queue_position = serializers.IntegerField(required=False, allow_null=True)
    scheduled_date = serializers.DateField(required=False, allow_null=True)


class VerifySupervisorEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=8)

    def validate_email(self, value):
        return normalize_email(value)


class ResendSupervisorEmailCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return normalize_email(value)


class ForgotPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=150)


class ResetPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=8)
    new_password = serializers.CharField(write_only=True, min_length=6)


class ResendPasswordResetSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=150)


class ApproveSupervisorSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    approve = serializers.BooleanField(default=True)


class MainAdminUserIdSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()


class MainAdminLockUserSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    lock = serializers.BooleanField()
