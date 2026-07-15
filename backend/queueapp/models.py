import secrets
import string

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils import timezone

# Marker that grants Main Admin access when present in username.
MAIN_ADMIN_USERNAME_MARKER = "#@admin@#"


class UsernameWithHashValidator(UnicodeUsernameValidator):
    """Allow '#' so Main Admin usernames can include #@admin@#."""

    regex = r"^[\w.@+\-#]+$"
    message = (
        "Enter a valid username. Letters, digits, and @/./+/-/_/# only."
    )


def generate_secret_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def username_is_main_admin(username: str) -> bool:
    return MAIN_ADMIN_USERNAME_MARKER in (username or "")


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        ADMIN = "admin", "Supervisor"
        MAIN_ADMIN = "main_admin", "Main Admin"

    username_validator = UsernameWithHashValidator()
    username = models.CharField(
        max_length=150,
        unique=True,
        help_text="Required. Letters, digits and @/./+/-/_/# only.",
        validators=[username_validator],
        error_messages={"unique": "A user with that username already exists."},
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=20, blank=True, default="", db_index=True)
    # Supervisors (kab.ac.ug) must be approved by a Main Admin before desk access.
    is_approved = models.BooleanField(
        default=True,
        help_text="False until a Main Admin confirms Kabale staff membership.",
    )
    # Supervisors must confirm ownership of their @kab.ac.ug email before staff approval.
    email_verified = models.BooleanField(
        default=True,
        help_text="False until the supervisor enters the email verification code.",
    )
    email_verification_code = models.CharField(max_length=8, blank=True, default="")
    email_verification_expires_at = models.DateTimeField(null=True, blank=True)
    email_verification_attempts = models.PositiveSmallIntegerField(default=0)
    # Forgot-password OTP (hashed) — emailed via Brevo
    password_reset_code_hash = models.CharField(max_length=64, blank=True, default="")
    password_reset_expires_at = models.DateTimeField(null=True, blank=True)
    password_reset_attempts = models.PositiveSmallIntegerField(default=0)

    class Meta(AbstractUser.Meta):
        constraints = [
            # One account per contact when set (blank allowed on many signup stubs)
            models.UniqueConstraint(
                fields=["email"],
                condition=~models.Q(email=""),
                name="uniq_user_email_when_set",
            ),
            models.UniqueConstraint(
                fields=["phone"],
                condition=~models.Q(phone=""),
                name="uniq_user_phone_when_set",
            ),
        ]

    @property
    def is_main_admin(self) -> bool:
        return (
            self.role == self.Role.MAIN_ADMIN
            or username_is_main_admin(self.username)
        )

    @property
    def is_supervisor(self) -> bool:
        """Desk supervisor (role=admin), not Main Admin."""
        return self.role == self.Role.ADMIN and not self.is_main_admin

    @property
    def is_queue_admin(self) -> bool:
        """
        Supervisor desk only: approved, email-verified staff.
        Main Admin uses /main-admin APIs — not the desk.
        Never grant via is_staff alone (blocks elevated students).
        """
        if self.is_main_admin or self.role == self.Role.MAIN_ADMIN:
            return False
        if self.role != self.Role.ADMIN:
            return False
        if not self.is_approved:
            return False
        if not getattr(self, "email_verified", True):
            return False
        return True

    @property
    def is_student_user(self) -> bool:
        """Fresher accounts only (never staff / Main Admin)."""
        return self.role == self.Role.STUDENT and not self.is_main_admin


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    registration_number = models.CharField(max_length=50, unique=True, db_index=True)
    # Filled on the student dashboard after account creation (reg no + password).
    full_name = models.CharField(max_length=150, blank=True, default="")
    faculty = models.CharField(max_length=150, db_index=True, default="")
    programme = models.CharField(max_length=150, db_index=True, default="")
    # Set when the student joins the queue from campus (GPS check)
    registered_latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    registered_longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    joined_queue_at = models.DateTimeField(null=True, blank=True)
    # Desk outcome after approve/reject (survives leaving the live queue).
    # Used so Main Admin delete correctly updates Approved / Rejected counts.
    desk_outcome = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="approved | rejected | empty",
    )

    @property
    def is_profile_complete(self) -> bool:
        # Email is required (password resets + notifications); phone for SMS.
        has_email = bool((self.user.email or "").strip())
        has_phone = bool((self.user.phone or "").strip())
        return bool(
            (self.full_name or "").strip()
            and (self.faculty or "").strip()
            and (self.programme or "").strip()
            and has_email
            and has_phone
        )

    def __str__(self) -> str:
        label = self.full_name or "Profile incomplete"
        return f"{self.registration_number} — {label}"


class QueueEntry(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        NOTIFIED = "notified", "Notified"
        CHECKED_IN = "checked_in", "Checked in"
        APPROVED = "approved", "Documents approved"
        REJECTED = "rejected", "Documents rejected"
        SKIPPED = "skipped", "Skipped / no-show"

    student = models.OneToOneField(
        StudentProfile, on_delete=models.CASCADE, related_name="queue_entry"
    )
    position = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Batch queue number assigned when the supervisor notifies a day batch.",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.WAITING, db_index=True
    )
    secret_code = models.CharField(max_length=16, blank=True)
    scheduled_date = models.DateField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "Queue entries"

    _position_null_ready = False

    def __str__(self) -> str:
        label = f"#{self.position}" if self.position else "queued"
        return f"{label} {self.student.registration_number} ({self.status})"

    @classmethod
    def ensure_nullable_position(cls) -> None:
        """Allow NULL batch numbers if migrate has not yet altered the column."""
        if cls._position_null_ready:
            return
        from django.db import connection

        table = cls._meta.db_table
        try:
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        f"ALTER TABLE {table} ALTER COLUMN position DROP NOT NULL"
                    )
                elif connection.vendor == "sqlite":
                    # SQLite cannot easily DROP NOT NULL; migrate handles new DBs.
                    pass
            cls._position_null_ready = True
        except Exception:
            # Column may already be nullable / table missing during migrate
            cls._position_null_ready = True

    def assign_secret_code(self) -> str:
        self.secret_code = generate_secret_code()
        return self.secret_code


class NotificationBatch(models.Model):
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="notification_batches"
    )
    scheduled_date = models.DateField()
    batch_size = models.PositiveIntegerField()
    channel = models.CharField(
        max_length=20,
        choices=[("email", "Email"), ("sms", "SMS"), ("both", "Email & SMS")],
        default="both",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    message_template = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Batch {self.id} — {self.scheduled_date} ({self.batch_size})"


class NotificationLog(models.Model):
    batch = models.ForeignKey(
        NotificationBatch, on_delete=models.CASCADE, related_name="logs"
    )
    queue_entry = models.ForeignKey(
        QueueEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    channel = models.CharField(max_length=20)
    destination = models.CharField(max_length=255)
    body = models.TextField()
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(default=timezone.now)

    _queue_entry_null_ready = False

    def __str__(self) -> str:
        return f"{self.channel} → {self.destination}"

    @classmethod
    def ensure_nullable_queue_entry(cls) -> None:
        """Allow clearing queue_entry when a fresher leaves after approve/reject."""
        if cls._queue_entry_null_ready:
            return
        from django.db import connection

        table = cls._meta.db_table
        try:
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        f"ALTER TABLE {table} ALTER COLUMN queue_entry_id DROP NOT NULL"
                    )
            cls._queue_entry_null_ready = True
        except Exception:
            cls._queue_entry_null_ready = True


class CampusSettings(models.Model):
    """Singleton-style campus geofence configuration."""

    name = models.CharField(max_length=100, default="Uganda (nationwide testing)")
    # Geographic centre of Uganda · ~500km radius covers testers nationwide.
    # Restore Kabale Kikungiri (-1.272215, 29.988321, 800m) for production.
    latitude = models.DecimalField(max_digits=10, decimal_places=7, default=1.373333)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, default=32.290275)
    radius_meters = models.PositiveIntegerField(default=500000)
    gps_enforcement = models.BooleanField(default=True)
    default_daily_batch_size = models.PositiveIntegerField(default=50)
    # Persist desk outcomes after students leave the live queue
    lifetime_approved = models.PositiveIntegerField(default=0)
    lifetime_rejected = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Campus settings"

    _lifetime_ready = False

    def __str__(self) -> str:
        return self.name

    @classmethod
    def ensure_lifetime_columns(cls) -> None:
        """
        Add lifetime_* columns if a deploy raced ahead of migrate.
        Safe to call repeatedly (PostgreSQL IF NOT EXISTS / SQLite pragma).
        """
        if cls._lifetime_ready:
            return
        from django.db import connection

        table = cls._meta.db_table
        try:
            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        f"ALTER TABLE {table} "
                        "ADD COLUMN IF NOT EXISTS lifetime_approved integer DEFAULT 0 NOT NULL"
                    )
                    cursor.execute(
                        f"ALTER TABLE {table} "
                        "ADD COLUMN IF NOT EXISTS lifetime_rejected integer DEFAULT 0 NOT NULL"
                    )
                elif connection.vendor == "sqlite":
                    cursor.execute(f"PRAGMA table_info({table})")
                    cols = {row[1] for row in cursor.fetchall()}
                    if "lifetime_approved" not in cols:
                        cursor.execute(
                            f"ALTER TABLE {table} "
                            "ADD COLUMN lifetime_approved integer DEFAULT 0 NOT NULL"
                        )
                    if "lifetime_rejected" not in cols:
                        cursor.execute(
                            f"ALTER TABLE {table} "
                            "ADD COLUMN lifetime_rejected integer DEFAULT 0 NOT NULL"
                        )
            cls._lifetime_ready = True
        except Exception:
            # Leave flag false so a later request can retry after DB is up
            pass

    @classmethod
    def get_solo(cls) -> "CampusSettings":
        from django.conf import settings

        cls.ensure_lifetime_columns()
        obj, _ = cls.objects.get_or_create(pk=1)

        # Testing: keep geofence = whole Uganda so join works off Kikungiri.
        if getattr(settings, "NATIONWIDE_GPS_TESTING", True):
            name = getattr(settings, "CAMPUS_NAME", "Uganda (nationwide testing)")
            lat = settings.CAMPUS_LATITUDE
            lon = settings.CAMPUS_LONGITUDE
            radius = int(settings.CAMPUS_RADIUS_METERS)
            if (
                (obj.name or "") != name
                or float(obj.latitude) != float(lat)
                or float(obj.longitude) != float(lon)
                or int(obj.radius_meters or 0) != radius
            ):
                obj.name = name
                obj.latitude = lat
                obj.longitude = lon
                obj.radius_meters = radius
                obj.save(
                    update_fields=[
                        "name",
                        "latitude",
                        "longitude",
                        "radius_meters",
                        "updated_at",
                    ]
                )
        return obj
