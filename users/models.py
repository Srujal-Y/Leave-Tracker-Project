from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        MANAGER = "MANAGER", "Manager"
        HR = "HR", "HR"

    class PortalAccess(models.TextChoices):
        MAIN = "MAIN", "Main Leave Tracker"
        ORGANIZATION = "ORGANIZATION", "Organization Server"
        BOTH = "BOTH", "Both Trackers"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.EMPLOYEE)
    organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_members",
        limit_choices_to={"role": Role.MANAGER},
    )
    created_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_users",
        help_text="User who created this account.",
    )
    created_in_organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="org_server_created_users",
        help_text="Organization context used when this user was created.",
    )
    portal_access = models.CharField(
        max_length=16,
        choices=PortalAccess.choices,
        default=PortalAccess.BOTH,
        help_text="Controls whether user can login to Main tracker, Organization server, or both.",
    )

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        if self.manager_id and self.manager and self.organization_id and self.manager.organization_id != self.organization_id:
            self.manager = None
        super().save(*args, **kwargs)


class AdminAccount(models.Model):
    class Level(models.TextChoices):
        PLATFORM = "PLATFORM", "Platform Admin"
        ORGANIZATION = "ORGANIZATION", "Organization Admin"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="admin_account")
    organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="admin_accounts",
    )
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.ORGANIZATION)
    can_manage_users = models.BooleanField(default=True)
    can_manage_organizations = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        scope = self.organization.slug if self.organization_id else "global"
        return f"{self.user.username} ({self.level}:{scope})"

    def clean(self):
        super().clean()
        if self.level == self.Level.PLATFORM:
            self.organization = None
        if self.level == self.Level.ORGANIZATION and not self.organization_id:
            raise ValidationError("Organization admin must be linked to an organization.")


class EmployeeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    photo = models.FileField(upload_to="employee_photos/", blank=True, null=True)
    phone_number = models.CharField(max_length=30, blank=True, default="")
    current_project = models.CharField(max_length=200, blank=True, default="")
    project_status = models.CharField(max_length=200, blank=True, default="")
    initiatives_to_take = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"Profile({self.user.username})"


class PasswordResetOTP(models.Model):
    organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="password_otps",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_otps")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def expiry_timestamp(cls):
        return timezone.now() + timedelta(minutes=10)

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])

    def save(self, *args, **kwargs):
        if not self.organization_id and self.user_id and getattr(self.user, "organization_id", None):
            self.organization_id = self.user.organization_id
        super().save(*args, **kwargs)
