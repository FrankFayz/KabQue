from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    CampusSettings,
    NotificationBatch,
    NotificationLog,
    QueueEntry,
    StudentProfile,
    User,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "phone", "role", "is_staff")
    list_filter = ("role", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("KabQue", {"fields": ("role", "phone")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("KabQue", {"fields": ("role", "phone", "email")}),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = (
        "registration_number",
        "full_name",
        "faculty",
        "programme",
        "registered_at",
    )
    list_filter = ("faculty", "programme")
    search_fields = ("registration_number", "full_name", "faculty", "programme")


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display = (
        "position",
        "student",
        "status",
        "scheduled_date",
        "secret_code",
        "created_at",
    )
    list_filter = ("status", "scheduled_date")
    search_fields = ("student__registration_number", "secret_code", "student__full_name")


@admin.register(NotificationBatch)
class NotificationBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "scheduled_date", "batch_size", "channel", "created_at")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("channel", "destination", "success", "sent_at", "batch")
    list_filter = ("channel", "success")


@admin.register(CampusSettings)
class CampusSettingsAdmin(admin.ModelAdmin):
    list_display = ("name", "latitude", "longitude", "radius_meters", "gps_enforcement")
