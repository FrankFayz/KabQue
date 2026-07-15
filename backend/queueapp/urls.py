from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path(
        "auth/verify-supervisor-email/",
        views.VerifySupervisorEmailView.as_view(),
        name="verify_supervisor_email",
    ),
    path(
        "auth/resend-supervisor-code/",
        views.ResendSupervisorEmailCodeView.as_view(),
        name="resend_supervisor_code",
    ),
    path(
        "auth/forgot-password/",
        views.ForgotPasswordView.as_view(),
        name="forgot_password",
    ),
    path(
        "auth/reset-password/",
        views.ResetPasswordView.as_view(),
        name="reset_password",
    ),
    path(
        "auth/resend-reset-code/",
        views.ResendPasswordResetView.as_view(),
        name="resend_reset_code",
    ),
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
        "admin/batch-reschedule/",
        views.AdminBatchRescheduleView.as_view(),
        name="admin_batch_reschedule",
    ),
    path(
        "admin/batch/active/",
        views.AdminActiveBatchView.as_view(),
        name="admin_batch_active",
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
    path(
        "main-admin/lock-user/",
        views.MainAdminLockUserView.as_view(),
        name="main_admin_lock_user",
    ),
    path(
        "main-admin/delete-user/",
        views.MainAdminDeleteUserView.as_view(),
        name="main_admin_delete_user",
    ),
]
