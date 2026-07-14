from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("student/queue/", views.StudentQueueStatusView.as_view(), name="student_queue"),
    path(
        "student/profile/",
        views.CompleteStudentProfileView.as_view(),
        name="student_profile",
    ),
    path("student/join-queue/", views.JoinQueueView.as_view(), name="join_queue"),
    path(
        "student/reschedule/",
        views.StudentRescheduleView.as_view(),
        name="student_reschedule",
    ),
    path(
        "student/leave-queue/",
        views.StudentLeaveQueueView.as_view(),
        name="student_leave_queue",
    ),
    path("admin/dashboard/", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    path("admin/queue/", views.AdminQueueListView.as_view(), name="admin_queue"),
    path("admin/notify/", views.NotifyBatchView.as_view(), name="admin_notify"),
    path("admin/verify-code/", views.VerifyCodeView.as_view(), name="admin_verify"),
    path(
        "admin/complete-verification/",
        views.CompleteVerificationView.as_view(),
        name="admin_complete",
    ),
    path(
        "admin/reschedule/",
        views.AdminRescheduleView.as_view(),
        name="admin_reschedule",
    ),
    path(
        "admin/remove-from-queue/",
        views.AdminRemoveFromQueueView.as_view(),
        name="admin_remove_from_queue",
    ),
    path("admin/campus/", views.CampusSettingsView.as_view(), name="admin_campus"),
    path(
        "main-admin/overview/",
        views.MainAdminOverviewView.as_view(),
        name="main_admin_overview",
    ),
    path(
        "main-admin/freshers/",
        views.MainAdminFreshersView.as_view(),
        name="main_admin_freshers",
    ),
    path(
        "main-admin/admins/",
        views.MainAdminAdminsView.as_view(),
        name="main_admin_admins",
    ),
    path(
        "main-admin/supervisors/",
        views.MainAdminSupervisorsView.as_view(),
        name="main_admin_supervisors",
    ),
    path(
        "main-admin/approve-supervisor/",
        views.MainAdminApproveSupervisorView.as_view(),
        name="main_admin_approve_supervisor",
    ),
]