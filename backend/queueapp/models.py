import secrets
import string

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def generate_secret_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=20, blank=True)

    @property
    def is_queue_admin(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_staff


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

    @property
    def is_profile_complete(self) -> bool:
        has_contact = bool((self.user.email or "").strip() or (self.user.phone or "").strip())
        return bool(
            (self.full_name or "").strip()
            and (self.faculty or "").strip()
            and (self.programme or "").strip()
            and has_contact
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
    position = models.PositiveIntegerField(db_index=True)
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
        ordering = ["position"]
        verbose_name_plural = "Queue entries"

    def __str__(self) -> str:
        return f"#{self.position} {self.student.registration_number} ({self.status})"

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
        QueueEntry, on_delete=models.CASCADE, related_name="notifications"
    )
    channel = models.CharField(max_length=20)
    destination = models.CharField(max_length=255)
    body = models.TextField()
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.channel} → {self.destination}"


class CampusSettings(models.Model):
    """Singleton-style campus geofence configuration."""

    name = models.CharField(max_length=100, default="Kabale University Kikungiri")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, default=-1.272215)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, default=29.988321)
    radius_meters = models.PositiveIntegerField(default=800)
    gps_enforcement = models.BooleanField(default=True)
    default_daily_batch_size = models.PositiveIntegerField(default=50)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Campus settings"

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_solo(cls) -> "CampusSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
