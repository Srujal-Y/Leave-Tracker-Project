from django.contrib import admin
from .models import LeaveRequest, LeaveType, LeaveReasonPreset


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_editable = ("active",)
    search_fields = ("name",)


@admin.register(LeaveReasonPreset)
class LeaveReasonPresetAdmin(admin.ModelAdmin):
    list_display = ("label", "active")
    list_editable = ("active",)
    search_fields = ("label",)

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
        "created_at",
    )
    list_filter = ("portion", "leave_type", "start_date", "end_date")
    search_fields = (
        "employee__username",
        "employee__email",
        "leave_label",
        "reason_text",
        "leave_type__name",
        "reason_preset__label",
    )
