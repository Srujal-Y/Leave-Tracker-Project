from django.contrib import admin
from .models import Holiday, LeaveReasonPreset, LeaveRequest, LeaveRevision, LeaveType


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "annual_quota", "active")
    list_editable = ("annual_quota", "active")
    search_fields = ("name",)


@admin.register(LeaveReasonPreset)
class LeaveReasonPresetAdmin(admin.ModelAdmin):
    list_display = ("label", "active")
    list_editable = ("active",)
    search_fields = ("label",)


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("day", "title", "active")
    list_editable = ("title", "active")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "leave_type",
        "leave_label",
        "start_date",
        "end_date",
        "portion",
        "requested_units",
        "status",
        "created_at",
    )
    list_filter = ("portion", "status", "leave_type", "start_date", "end_date")
    search_fields = (
        "employee__username",
        "employee__email",
        "leave_label",
        "reason_text",
        "leave_type__name",
        "reason_preset__label",
    )


@admin.register(LeaveRevision)
class LeaveRevisionAdmin(admin.ModelAdmin):
    list_display = ("leave", "actor", "created_at")
    readonly_fields = ("snapshot_json",)
