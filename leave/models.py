from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum


class LeaveType(models.Model):
    """Company-provided leave types."""

    name = models.CharField(max_length=80, unique=True)
    annual_quota = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class LeaveReasonPreset(models.Model):
    """Optional preset reasons for the dropdown."""

    label = models.CharField(max_length=120, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]

    def __str__(self) -> str:
        return self.label


class Holiday(models.Model):
    title = models.CharField(max_length=140)
    day = models.DateField(unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["day"]

    def __str__(self) -> str:
        return f"{self.day} - {self.title}"


class LeaveRequest(models.Model):
    class Portion(models.TextChoices):
        FULL = "FULL", "Full day(s)"
        HALF = "HALF", "Half day"
        QUARTER = "QUARTER", "Quarter day"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Authentication Waiting"
        AUTHENTICATED = "AUTHENTICATED", "Authenticated"
        CANCELLED = "CANCELLED", "Cancelled"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, null=True, blank=True, on_delete=models.SET_NULL)
    leave_label = models.CharField(max_length=80, blank=True, default="")
    start_date = models.DateField()
    end_date = models.DateField()
    portion = models.CharField(max_length=10, choices=Portion.choices, default=Portion.FULL)
    requested_units = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("1.00"))
    reason_preset = models.ForeignKey(LeaveReasonPreset, null=True, blank=True, on_delete=models.SET_NULL)
    reason_text = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["employee", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee} {self.start_date}→{self.end_date}"

    @property
    def display_reason(self) -> str:
        if self.reason_text:
            return self.reason_text
        if self.reason_preset_id:
            return self.reason_preset.label
        if self.leave_label:
            return self.leave_label
        return ""

    @property
    def duration_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def holiday_days(self) -> int:
        return Holiday.objects.filter(day__gte=self.start_date, day__lte=self.end_date, active=True).count()

    @staticmethod
    def _portion_units(portion: str) -> Decimal:
        if portion == LeaveRequest.Portion.QUARTER:
            return Decimal("0.25")
        if portion == LeaveRequest.Portion.HALF:
            return Decimal("0.50")
        return Decimal("1.00")

    def compute_requested_units(self) -> Decimal:
        days = self.duration_days
        last_day_units = self._portion_units(self.portion)
        if days <= 1:
            return last_day_units
        return Decimal(days - 1) + last_day_units

    @property
    def remaining_balance(self) -> Decimal | None:
        if not self.leave_type_id:
            return None
        used = (
            LeaveRequest.objects.filter(
                employee=self.employee,
                leave_type=self.leave_type,
                status=self.Status.AUTHENTICATED,
                deleted_at__isnull=True,
            )
            .exclude(pk=self.pk)
            .aggregate(s=Sum("requested_units"))
            .get("s")
            or Decimal("0")
        )
        return Decimal(self.leave_type.annual_quota) - used - Decimal(self.requested_units)

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise models.ValidationError("End date must be after start date")

    def save(self, *args, **kwargs):
        if not self.requested_units:
            self.requested_units = self.compute_requested_units()
        if not self.leave_label:
            if self.leave_type_id:
                self.leave_label = self.leave_type.name
            elif self.reason_preset_id:
                self.leave_label = self.reason_preset.label
            else:
                self.leave_label = "Leave"
        if not self.reason_text and self.reason_preset_id:
            self.reason_text = self.reason_preset.label
        super().save(*args, **kwargs)

    @classmethod
    def overlapping(cls, start: date, end: date):
        return cls.objects.filter(Q(start_date__lte=end) & Q(end_date__gte=start), deleted_at__isnull=True)


class LeaveRevision(models.Model):
    leave = models.ForeignKey(LeaveRequest, on_delete=models.CASCADE, related_name="revisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    snapshot_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
