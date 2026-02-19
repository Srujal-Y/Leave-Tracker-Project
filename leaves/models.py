from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class LeaveType(models.Model):
    organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="leave_types",
    )
    name = models.CharField(max_length=80)
    max_days = models.PositiveIntegerField(default=0)
    is_paid = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("organization", "name")]
        indexes = [
            models.Index(fields=["organization", "active"]),
        ]

    def __str__(self) -> str:
        if self.organization_id:
            return f"{self.organization.slug}: {self.name}"
        return self.name


class LeaveReasonPreset(models.Model):
    organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="leave_reason_presets",
    )
    label = models.CharField(max_length=120)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]
        unique_together = [("organization", "label")]
        indexes = [
            models.Index(fields=["organization", "active"]),
        ]

    def __str__(self) -> str:
        if self.organization_id:
            return f"{self.organization.slug}: {self.label}"
        return self.label


class Holiday(models.Model):
    organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="holidays",
    )
    name = models.CharField(max_length=120)
    date = models.DateField()

    class Meta:
        ordering = ["date"]
        unique_together = [("organization", "date")]
        indexes = [
            models.Index(fields=["organization", "date"]),
        ]

    def __str__(self):
        return f"{self.date} - {self.name}"


class LeaveBalance(models.Model):
    organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="leave_balances",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leave_balances")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name="balances")
    year = models.PositiveIntegerField()
    allocated_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    used_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("organization", "user", "leave_type", "year")
        ordering = ["year", "leave_type__name"]
        indexes = [
            models.Index(fields=["organization", "user", "year"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.leave_type} - {self.year}"

    @property
    def remaining_days(self) -> Decimal:
        remaining = self.allocated_days - self.used_days
        return remaining if remaining > 0 else Decimal("0.00")

    def can_consume(self, units: Decimal) -> bool:
        return self.remaining_days >= units

    def consume(self, units: Decimal):
        self.used_days += units
        self.save(update_fields=["used_days", "updated_at"])

    def release(self, units: Decimal):
        self.used_days = self.used_days - units
        if self.used_days < 0:
            self.used_days = Decimal("0.00")
        self.save(update_fields=["used_days", "updated_at"])

    def clean(self):
        super().clean()
        if self.organization_id and getattr(self.user, "organization_id", None):
            if self.user.organization_id != self.organization_id:
                raise ValidationError("User organization does not match leave balance organization.")
        if self.leave_type_id and self.leave_type.organization_id and self.organization_id:
            if self.leave_type.organization_id != self.organization_id:
                raise ValidationError("Leave type organization does not match leave balance organization.")

    def save(self, *args, **kwargs):
        if not self.organization_id and getattr(self.user, "organization_id", None):
            self.organization_id = self.user.organization_id
        if not self.organization_id and self.leave_type_id and self.leave_type.organization_id:
            self.organization_id = self.leave_type.organization_id
        super().save(*args, **kwargs)


class LeaveRequest(models.Model):
    class Portion(models.TextChoices):
        FULL = "FULL", "Full day"
        HALF = "HALF", "Half day"
        QUARTER = "QUARTER", "Quarter day"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    organization = models.ForeignKey(
        "organization.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="leave_requests",
    )
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    leave_label = models.CharField(max_length=120, blank=True, default="")
    reason_preset = models.ForeignKey(LeaveReasonPreset, null=True, blank=True, on_delete=models.SET_NULL)
    reason_text = models.TextField(blank=True, default="")
    start_date = models.DateField()
    end_date = models.DateField()
    portion = models.CharField(max_length=12, choices=Portion.choices, default=Portion.FULL)
    requested_units = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_leave_requests",
    )
    manager_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["employee", "-created_at"]),
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.employee} {self.start_date} to {self.end_date}"

    @property
    def display_reason(self) -> str:
        return self.reason_text or (self.reason_preset.label if self.reason_preset_id else "")

    @property
    def calendar_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @staticmethod
    def _portion_units(portion: str) -> Decimal:
        if portion == LeaveRequest.Portion.HALF:
            return Decimal("0.50")
        if portion == LeaveRequest.Portion.QUARTER:
            return Decimal("0.25")
        return Decimal("1.00")

    @staticmethod
    def business_dates(
        start: date,
        end: date,
        include_holidays: bool = False,
        organization_id: int | None = None,
    ) -> list[date]:
        day_count = (end - start).days + 1
        days: list[date] = []
        holiday_qs = Holiday.objects.filter(date__range=(start, end))
        if organization_id:
            holiday_qs = holiday_qs.filter(organization_id=organization_id)
        holidays = set(holiday_qs.values_list("date", flat=True))
        for i in range(day_count):
            d = start.fromordinal(start.toordinal() + i)
            if d.weekday() >= 5:
                continue
            if not include_holidays and d in holidays:
                continue
            days.append(d)
        return days

    def business_days_count(self, include_holidays: bool = False) -> int:
        return len(
            self.business_dates(
                self.start_date,
                self.end_date,
                include_holidays=include_holidays,
                organization_id=self.organization_id,
            )
        )

    def weekend_or_holiday_count(self) -> int:
        business = self.business_days_count(include_holidays=False)
        return max(self.calendar_days - business, 0)

    def compute_requested_units(self) -> Decimal:
        business_days = self.business_days_count()
        if business_days <= 0:
            return Decimal("0.00")
        portion_units = self._portion_units(self.portion)
        if business_days == 1:
            return portion_units
        return Decimal(business_days - 1) + portion_units

    def units_by_year(self) -> dict[int, Decimal]:
        business_days = self.business_dates(
            self.start_date,
            self.end_date,
            organization_id=self.organization_id,
        )
        if not business_days:
            return {}
        out: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for d in business_days[:-1]:
            out[d.year] += Decimal("1.00")
        out[business_days[-1].year] += self._portion_units(self.portion)
        return dict(out)

    @classmethod
    def overlapping(cls, start: date, end: date, organization_id: int | None = None):
        queryset = cls.objects.filter(Q(start_date__lte=end) & Q(end_date__gte=start))
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        return queryset

    def clean(self):
        super().clean()
        if not isinstance(self.start_date, date) or not isinstance(self.end_date, date):
            return
        if self.end_date < self.start_date:
            raise ValidationError("End date must be on or after start date.")
        if self.business_days_count() <= 0:
            raise ValidationError("Selected range has no working days.")
        if self.organization_id and getattr(self.employee, "organization_id", None):
            if self.employee.organization_id != self.organization_id:
                raise ValidationError("Employee organization does not match leave request organization.")
        if self.leave_type_id and self.leave_type.organization_id and self.organization_id:
            if self.leave_type.organization_id != self.organization_id:
                raise ValidationError("Leave type organization does not match leave request organization.")
        if self.reason_preset_id and self.reason_preset.organization_id and self.organization_id:
            if self.reason_preset.organization_id != self.organization_id:
                raise ValidationError("Reason preset organization does not match leave request organization.")

    def save(self, *args, **kwargs):
        if not self.organization_id and getattr(self.employee, "organization_id", None):
            self.organization_id = self.employee.organization_id
        if not self.organization_id and self.leave_type_id and self.leave_type.organization_id:
            self.organization_id = self.leave_type.organization_id
        if self.requested_units <= 0:
            self.requested_units = self.compute_requested_units()
        if not self.leave_label:
            self.leave_label = self.leave_type.name
        if not self.reason_text and self.reason_preset_id:
            self.reason_text = self.reason_preset.label
        super().save(*args, **kwargs)


class LeaveAttachment(models.Model):
    organization = models.ForeignKey(
        "organization.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="leave_attachments",
    )
    leave_request = models.ForeignKey(LeaveRequest, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="leave_documents/%Y/%m/%d/")
    original_name = models.CharField(max_length=255, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_leave_attachments",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        name = self.original_name or Path(self.file.name).name
        return f"{name} ({self.leave_request_id})"

    @property
    def size_mb(self) -> Decimal:
        if not self.size_bytes:
            return Decimal("0.00")
        return (Decimal(self.size_bytes) / Decimal(1024 * 1024)).quantize(Decimal("0.01"))

    def clean(self):
        super().clean()
        if self.organization_id and self.leave_request_id and self.leave_request.organization_id:
            if self.organization_id != self.leave_request.organization_id:
                raise ValidationError("Attachment organization does not match leave request organization.")

    def save(self, *args, **kwargs):
        if self.leave_request_id and not self.organization_id:
            self.organization_id = self.leave_request.organization_id
        if self.file:
            if not self.original_name:
                self.original_name = Path(self.file.name).name
            try:
                self.size_bytes = int(self.file.size or 0)
            except Exception:
                pass
        super().save(*args, **kwargs)


class TalentCandidate(models.Model):
    class Stage(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        SCREENING = "SCREENING", "Screening"
        INTERVIEW = "INTERVIEW", "Interview"
        OFFER = "OFFER", "Offer"
        HIRED = "HIRED", "Hired"
        REJECTED = "REJECTED", "Rejected"

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    company = models.ForeignKey(
        "organization.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="talent_candidates",
    )
    org_unit = models.ForeignKey(
        "organization.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="talent_candidates",
    )
    location = models.ForeignKey(
        "organization.Location",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="talent_candidates",
    )
    cost_center = models.ForeignKey(
        "organization.CostCenter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="talent_candidates",
    )
    hiring_manager = models.ForeignKey(
        "organization.EmployeeRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hiring_candidates",
    )
    phone = models.CharField(max_length=30, blank=True, default="")
    role_applied = models.CharField(max_length=120)
    source = models.CharField(max_length=120, blank=True, default="")
    expected_join = models.DateField(null=True, blank=True)
    resume_link = models.URLField(blank=True, default="")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_talent_candidates",
    )
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.APPLIED)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["company", "stage"]),
            models.Index(fields=["org_unit", "location"]),
            models.Index(fields=["stage"]),
            models.Index(fields=["email"]),
            models.Index(fields=["expected_join"]),
            models.Index(fields=["owner", "stage"]),
            models.Index(fields=["-updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.role_applied})"

    def clean(self):
        super().clean()
        if self.company_id and self.org_unit_id and self.org_unit.company_id != self.company_id:
            raise ValidationError("Org unit company does not match candidate company.")
        if self.company_id and self.location_id and self.location.company_id != self.company_id:
            raise ValidationError("Location company does not match candidate company.")
        if self.company_id and self.cost_center_id and self.cost_center.company_id != self.company_id:
            raise ValidationError("Cost center company does not match candidate company.")
        if self.company_id and self.hiring_manager_id and self.hiring_manager.company_id != self.company_id:
            raise ValidationError("Hiring manager company does not match candidate company.")
        if self.company_id and self.owner_id and getattr(self.owner, "organization_id", None):
            if self.owner.organization_id != self.company_id:
                raise ValidationError("Owner organization does not match candidate company.")

    def save(self, *args, **kwargs):
        if not self.company_id and self.owner_id and getattr(self.owner, "organization_id", None):
            self.company_id = self.owner.organization_id
        super().save(*args, **kwargs)


class OnboardingTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        DONE = "DONE", "Done"
        BLOCKED = "BLOCKED", "Blocked"

    class Category(models.TextChoices):
        HR = "HR", "HR"
        IT = "IT", "IT"
        FACILITIES = "FACILITIES", "Facilities"
        GENERAL = "GENERAL", "General"

    company = models.ForeignKey(
        "organization.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="onboarding_tasks",
    )

    candidate = models.ForeignKey(
        TalentCandidate,
        on_delete=models.CASCADE,
        related_name="onboarding_tasks",
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_onboarding_tasks",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_date", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["candidate", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.candidate.full_name}: {self.title}"

    def clean(self):
        super().clean()
        if self.candidate_id and self.company_id and self.candidate.company_id and self.company_id != self.candidate.company_id:
            raise ValidationError("Onboarding task company does not match candidate company.")
        if self.company_id and self.owner_id and getattr(self.owner, "organization_id", None):
            if self.owner.organization_id != self.company_id:
                raise ValidationError("Owner organization does not match onboarding task company.")

    def save(self, *args, **kwargs):
        if not self.company_id and self.candidate_id and self.candidate.company_id:
            self.company_id = self.candidate.company_id
        super().save(*args, **kwargs)


class TalentCandidateCustomFieldValue(models.Model):
    candidate = models.ForeignKey(
        TalentCandidate,
        on_delete=models.CASCADE,
        related_name="custom_fields",
    )
    field = models.ForeignKey(
        "organization.OrganizationFormField",
        on_delete=models.CASCADE,
        related_name="candidate_values",
    )
    value_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["field__sort_order", "id"]
        unique_together = [("candidate", "field")]
        indexes = [
            models.Index(fields=["candidate", "field"]),
            models.Index(fields=["field"]),
        ]

    def __str__(self) -> str:
        return f"{self.candidate_id}:{self.field.key}"

    def clean(self):
        super().clean()
        if self.field.module != "TALENT":
            raise ValidationError("Selected field is not configured for Talent module.")
        if self.candidate.company_id and self.field.company_id != self.candidate.company_id:
            raise ValidationError("Form field company does not match candidate company.")


class OnboardingTaskCustomFieldValue(models.Model):
    task = models.ForeignKey(
        OnboardingTask,
        on_delete=models.CASCADE,
        related_name="custom_fields",
    )
    field = models.ForeignKey(
        "organization.OrganizationFormField",
        on_delete=models.CASCADE,
        related_name="onboarding_values",
    )
    value_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["field__sort_order", "id"]
        unique_together = [("task", "field")]
        indexes = [
            models.Index(fields=["task", "field"]),
            models.Index(fields=["field"]),
        ]

    def __str__(self) -> str:
        return f"{self.task_id}:{self.field.key}"

    def clean(self):
        super().clean()
        if self.field.module != "ONBOARDING":
            raise ValidationError("Selected field is not configured for Onboarding module.")
        if self.task.company_id and self.field.company_id != self.task.company_id:
            raise ValidationError("Form field company does not match onboarding task company.")
