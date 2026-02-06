from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


class LeaveType(models.Model):
    """Company-provided leave types (optional)."""

    name = models.CharField(max_length=80, unique=True)
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


class LeaveRequest(models.Model):
    class Portion(models.TextChoices):
        FULL = "FULL", "Full day(s)"
        HALF = "HALF", "Half day"
        QUARTER = "QUARTER", "Quarter day"

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Optional type dropdown
    leave_type = models.ForeignKey(LeaveType, null=True, blank=True, on_delete=models.SET_NULL)

    # User-visible label (free text; can mirror type/reason)
    leave_label = models.CharField(max_length=80, blank=True, default="")

    start_date = models.DateField()
    end_date = models.DateField()

    # Boolean-like choice, but stored as a single value
    portion = models.CharField(max_length=10, choices=Portion.choices, default=Portion.FULL)

    # Units requested; unlimited by design (company policy can later add validation).
    # We keep two decimal places so quarter day = 0.25.
    requested_units = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("1.00"))

    # Reason can be selected from dropdown or typed.
    reason_preset = models.ForeignKey(LeaveReasonPreset, null=True, blank=True, on_delete=models.SET_NULL)
    reason_text = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["employee", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee} {self.start_date}→{self.end_date}"

    @property
    def display_reason(self) -> str:
        """Single string shown on the public board."""
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

    @staticmethod
    def _portion_units(portion: str) -> Decimal:
        if portion == LeaveRequest.Portion.QUARTER:
            return Decimal("0.25")
        if portion == LeaveRequest.Portion.HALF:
            return Decimal("0.50")
        return Decimal("1.00")

    def compute_requested_units(self) -> Decimal:
        """Compute requested_units from date range + portion.

        For multi-day ranges, the portion applies to the last day:
        e.g. 3 days with HALF => 2.5
        """
        days = self.duration_days
        last_day_units = self._portion_units(self.portion)
        if days <= 1:
            return last_day_units
        return Decimal(days - 1) + last_day_units

    def clean(self):
        super().clean()
        if self.end_date < self.start_date:
            raise models.ValidationError("End date must be after start date")

    def save(self, *args, **kwargs):
        # Always keep requested_units coherent unless caller explicitly set it.
        if not self.requested_units:
            self.requested_units = self.compute_requested_units()
        # If label empty, provide a sensible default.
        if not self.leave_label:
            if self.leave_type_id:
                self.leave_label = self.leave_type.name
            elif self.reason_preset_id:
                self.leave_label = self.reason_preset.label
            else:
                self.leave_label = "Leave"
        # If reason_text empty and preset selected, copy preset into text.
        if not self.reason_text and self.reason_preset_id:
            self.reason_text = self.reason_preset.label
        super().save(*args, **kwargs)

    @classmethod
    def overlapping(cls, start: date, end: date):
        return cls.objects.filter(Q(start_date__lte=end) & Q(end_date__gte=start))
