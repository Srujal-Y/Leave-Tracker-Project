from __future__ import annotations

from django.urls import path

from . import views

app_name = "leaves"

urlpatterns = [
    path("apply/", views.apply_leave, name="apply_leave"),
    path("apply/<int:pk>/edit/", views.edit_leave, name="edit_leave"),
    path("apply/<int:pk>/cancel/", views.cancel_leave, name="cancel_leave"),
    path("company/", views.company_board, name="company_board"),
    path("company/export.csv", views.export_csv, name="export_csv"),
    path("calendar/", views.team_calendar, name="team_calendar"),
    path("approvals/", views.approval_queue, name="approval_queue"),
    path("approvals/<int:pk>/", views.review_leave, name="review_leave"),
    path("policies/", views.manage_policies, name="manage_policies"),
    path("policies/types/new/", views.leave_type_create, name="leave_type_create"),
    path("policies/types/<int:pk>/edit/", views.leave_type_edit, name="leave_type_edit"),
    path("policies/reasons/new/", views.reason_preset_create, name="reason_preset_create"),
    path("policies/reasons/<int:pk>/edit/", views.reason_preset_edit, name="reason_preset_edit"),
    path("policies/holidays/new/", views.holiday_create, name="holiday_create"),
    path("policies/holidays/<int:pk>/edit/", views.holiday_edit, name="holiday_edit"),
    path("policies/holidays/<int:pk>/delete/", views.holiday_delete, name="holiday_delete"),
    path("audit-trail/", views.audit_trail, name="audit_trail"),
    path("ical/", views.my_ical, name="my_ical"),
    path("<int:pk>/", views.leave_detail, name="leave_detail"),
]
