from django.urls import path
from . import views

app_name = "leave"

urlpatterns = [
    path("apply/", views.apply_leave, name="apply_leave"),
    path("company/", views.company_leaves, name="company_leaves"),
    path("company/export.csv", views.export_csv, name="export_csv"),
    path("company/calendar/", views.calendar_view, name="calendar_view"),
    path("company/conflicts/", views.team_conflicts, name="team_conflicts"),
    path("company/audit/", views.audit_trail, name="audit_trail"),
    path("company/settings/", views.leave_settings, name="leave_settings"),
    path("ical/my.ics", views.my_ical, name="my_ical"),
    path("company/<int:pk>/", views.leave_detail, name="leave_detail"),
    path("company/<int:pk>/edit/", views.edit_leave, name="edit_leave"),
]
