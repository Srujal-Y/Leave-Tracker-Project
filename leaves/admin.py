from __future__ import annotations

from django.contrib import admin

from .models import Holiday, LeaveAttachment, LeaveBalance, LeaveReasonPreset, LeaveRequest, LeaveType


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "max_days", "is_paid", "active")
    list_filter = ("is_paid", "active")
    search_fields = ("name",)


@admin.register(LeaveReasonPreset)
class LeaveReasonPresetAdmin(admin.ModelAdmin):
    list_display = ("label", "active")
    list_filter = ("active",)
    search_fields = ("label",)


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name")
    search_fields = ("name",)


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ("user", "leave_type", "year", "allocated_days", "used_days", "remaining_days")
    list_filter = ("year", "leave_type")
    search_fields = ("user__username", "user__email", "leave_type__name")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "leave_type",
        "start_date",
        "end_date",
        "portion",
        "requested_units",
        "status",
        "approver",
        "created_at",
    )
    list_filter = ("status", "portion", "leave_type", "start_date")
    search_fields = ("employee__username", "employee__email", "leave_label", "reason_text")


@admin.register(LeaveAttachment)
class LeaveAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "leave_request", "original_name", "size_bytes", "uploaded_by", "uploaded_at")
    search_fields = (
        "leave_request__employee__username",
        "leave_request__employee__email",
        "original_name",
        "file",
    )
    list_filter = ("uploaded_at",)
