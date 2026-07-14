from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .auth_utils import is_kab_university_email, kab_email_error_message, normalize_email
from .geo import is_on_campus
from .models import CampusSettings, NotificationBatch, QueueEntry, StudentProfile
from .phones import validate_east_africa_phone

User = get_user_model()


class StudentRegisterSerializer(serializers.Serializer):
    """Fresher account: registration number + password only."""

    registration_number = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_registration_number(self, value):
        reg = value.strip().upper()
        if not reg:
            raise serializers.ValidationError("Registration number is required.")
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
        )
        profile = StudentProfile.objects.create(
            user=user,
            registration_number=reg,
            full_name="",
            faculty="",
            programme="",
        )
        return {"user": user, "profile": profile}


class LecturerRegisterSerializer(serializers.Serializer):
    """Lecturer / supervisor account: official @kab.ac.ug email + password."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value):
        email = normalize_email(value)
        if not is_kab_university_email(email):
            raise serializers.ValidationError(kab_email_error_message())
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("This university email is already registered.")
        if User.objects.filter(username__iexact=email).exists():
            raise serializers.ValidationError("This university email is already registered.")
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
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate(self, attrs):
        email = normalize_email(attrs.get("email") or "")
        phone_raw = (attrs.get("phone") or "").strip()
        if not email and not phone_raw:
            raise serializers.ValidationError(
                "Provide at least an email or a telephone number for notifications."
            )

        try:
            phone = validate_east_africa_phone(phone_raw)
        except ValueError as exc:
            raise serializers.ValidationError({"phone": str(exc)}) from exc

        attrs["full_name"] = attrs["full_name"].strip()
        attrs["faculty"] = attrs["faculty"].strip()
        attrs["programme"] = attrs["programme"].strip()
        attrs["email"] = email
        attrs["phone"] = phone

        if not attrs["full_name"]:
            raise serializers.ValidationError({"full_name": "Full name is required."})
        if not attrs["faculty"]:
            raise serializers.ValidationError({"faculty": "Faculty is required."})
        if not attrs["programme"]:
            raise serializers.ValidationError({"programme": "Programme is required."})

        user = self.context["request"].user
        if email:
            taken = User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists()
            if taken:
                raise serializers.ValidationError({"email": "Email already in use."})
            # Students may use any email for notifications; lecturers alone require @kab.ac.ug
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
        user.save(update_fields=["email", "phone", "first_name", "last_name"])

        return profile


class JoinQueueSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()

    def validate(self, attrs):
        allowed, distance, radius = is_on_campus(attrs["latitude"], attrs["longitude"])
        if not allowed:
            raise serializers.ValidationError(
                {
                    "location": (
                        "You must be inside Uganda to join the KabQue test queue. "
                        "Turn on GPS and try again. "
                        f"(You are about {int(distance)}m outside the allowed area; "
                        f"allowed radius: {int(radius)}m.)"
                    )
                }
            )
        attrs["_distance_meters"] = distance
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
        )

    def get_profile_complete(self, obj):
        return obj.is_profile_complete


class QueueEntrySerializer(serializers.ModelSerializer):
    student = StudentProfileSerializer(read_only=True)
    secret_code = serializers.SerializerMethodField()

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
    decision = serializers.ChoiceField(choices=["approved", "rejected", "skipped"])
    notes = serializers.CharField(required=False, allow_blank=True)


class RescheduleSerializer(serializers.Serializer):
    scheduled_date = serializers.DateField()
    queue_entry_id = serializers.IntegerField(required=False)

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
