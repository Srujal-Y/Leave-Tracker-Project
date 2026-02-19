from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import AdminAccount, EmployeeProfile, PasswordResetOTP, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "organization",
        "role",
        "manager",
        "admin_scope",
        "portal_access",
    )
    list_filter = ("organization", "role", "portal_access")
    search_fields = ("username", "email", "first_name", "last_name", "organization__name")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Leave Portal",
            {
                "fields": (
                    "organization",
                    "role",
                    "manager",
                    "portal_access",
                )
            },
        ),
    )

    @admin.display(description="Admin Scope")
    def admin_scope(self, obj):
        admin_account = getattr(obj, "admin_account", None)
        if not admin_account:
            return "-"
        if admin_account.level == AdminAccount.Level.PLATFORM:
            return "Platform"
        if admin_account.organization_id:
            return f"Org: {admin_account.organization.name}"
        return "Org"


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number", "current_project", "project_status")
    search_fields = ("user__username", "user__email", "phone_number", "current_project", "project_status")


@admin.register(PasswordResetOTP)
class PasswordResetOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "code", "created_at", "expires_at", "used_at")
    search_fields = ("user__username", "user__email", "organization__name", "code")


@admin.register(AdminAccount)
class AdminAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "organization", "can_manage_users", "can_manage_organizations", "created_at")
    list_filter = ("level", "organization", "can_manage_users", "can_manage_organizations")
    search_fields = ("user__username", "user__email", "organization__name")
