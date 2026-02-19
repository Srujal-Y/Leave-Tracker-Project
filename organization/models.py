from __future__ import annotations

from datetime import date
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Company(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class OrganizationDirectory(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True)
    active = models.BooleanField(default=True)
    company = models.OneToOneField(
        Company,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="directory_entry",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class OrganizationTenant(models.Model):
    directory = models.OneToOneField(
        OrganizationDirectory,
        on_delete=models.CASCADE,
        related_name="tenant_config",
    )
    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="tenant_config",
    )
    schema_name = models.SlugField(max_length=80, unique=True)
    domain = models.CharField(max_length=255, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["schema_name"]

    def __str__(self) -> str:
        return f"{self.schema_name} ({self.domain})"

    def clean(self):
        super().clean()
        if self.directory_id and self.company_id and self.directory.company_id and self.directory.company_id != self.company_id:
            raise ValidationError("Tenant company must match directory company when directory is linked.")


class OrgUnit(models.Model):
    class UnitType(models.TextChoices):
        DEPARTMENT = "DEPT", "Department"
        TEAM = "TEAM", "Team"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="org_units")
    name = models.CharField(max_length=140)
    unit_type = models.CharField(max_length=8, choices=UnitType.choices, default=UnitType.TEAM)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    active = models.BooleanField(default=True)
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name", "name"]
        unique_together = [("company", "name", "parent")]
        indexes = [
            models.Index(fields=["company", "unit_type"]),
            models.Index(fields=["company", "active"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self) -> str:
        return f"{self.company.slug}: {self.name}"

    def clean(self):
        super().clean()
        if self.parent_id:
            if self.parent_id == self.id:
                raise ValidationError("OrgUnit cannot be its own parent.")
            if self.parent and self.parent.company_id != self.company_id:
                raise ValidationError("Parent OrgUnit must belong to the same company.")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError("effective_to cannot be earlier than effective_from.")


class Location(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="locations")
    name = models.CharField(max_length=120)
    country = models.CharField(max_length=80, blank=True, default="")
    city = models.CharField(max_length=80, blank=True, default="")
    timezone = models.CharField(max_length=64, default="UTC")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name", "name"]
        unique_together = [("company", "name")]
        indexes = [models.Index(fields=["company", "active"])]

    def __str__(self) -> str:
        return f"{self.company.slug}: {self.name}"


class CostCenter(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="cost_centers")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=140)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_cost_centers",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name", "code"]
        unique_together = [("company", "code")]
        indexes = [models.Index(fields=["company", "active"])]

    def __str__(self) -> str:
        return f"{self.company.slug}: {self.code}"


class JobLevel(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="job_levels")
    name = models.CharField(max_length=80)
    rank_band = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name", "rank_band", "name"]
        unique_together = [("company", "name")]
        indexes = [models.Index(fields=["company", "rank_band"])]

    def __str__(self) -> str:
        return f"{self.company.slug}: {self.name}"


class Position(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="positions")
    title = models.CharField(max_length=160)
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="positions")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="positions")
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT, related_name="positions")
    job_level = models.ForeignKey(JobLevel, on_delete=models.PROTECT, related_name="positions")
    manager_position = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="direct_positions",
    )
    headcount = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name", "title"]
        indexes = [
            models.Index(fields=["company", "org_unit"]),
            models.Index(fields=["company", "location"]),
            models.Index(fields=["company", "manager_position"]),
        ]

    def __str__(self) -> str:
        return f"{self.company.slug}: {self.title}"

    def clean(self):
        super().clean()
        linked = [self.org_unit, self.location, self.cost_center, self.job_level]
        for entity in linked:
            if entity and entity.company_id != self.company_id:
                raise ValidationError("All position references must belong to the same company.")
        if self.manager_position and self.manager_position.company_id != self.company_id:
            raise ValidationError("Manager position must belong to the same company.")


class EmployeeRecord(models.Model):
    class Status(models.TextChoices):
        PENDING_JOIN = "PENDING_JOIN", "Pending Join"
        ACTIVE = "ACTIVE", "Active"
        ON_LEAVE = "ON_LEAVE", "On Leave"
        EXITED = "EXITED", "Exited"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="employees")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee_record",
    )
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="employees")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_JOIN)
    join_date = models.DateField(default=timezone.localdate)
    exit_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name", "position__title", "id"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "position"]),
            models.Index(fields=["join_date"]),
        ]

    def __str__(self) -> str:
        who = self.user.get_full_name() if self.user else f"Employee#{self.pk}"
        return f"{self.company.slug}: {who}"

    def clean(self):
        super().clean()
        if self.position and self.position.company_id != self.company_id:
            raise ValidationError("Position must belong to the same company.")
        if self.user_id and getattr(self.user, "organization_id", None):
            if self.user.organization_id != self.company_id:
                raise ValidationError("User organization must match employee company.")
        if self.exit_date and self.exit_date < self.join_date:
            raise ValidationError("exit_date cannot be earlier than join_date.")

    def save(self, *args, **kwargs):
        if self.user_id and not getattr(self.user, "organization_id", None):
            self.user.organization_id = self.company_id
            self.user.save(update_fields=["organization"])
        super().save(*args, **kwargs)

    @property
    def org_unit(self) -> OrgUnit:
        return self.position.org_unit

    @property
    def location(self) -> Location:
        return self.position.location

    @property
    def cost_center(self) -> CostCenter:
        return self.position.cost_center


class ManagerRelationship(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="manager_relationships")
    employee = models.ForeignKey(EmployeeRecord, on_delete=models.CASCADE, related_name="manager_relationships")
    manager_employee = models.ForeignKey(
        EmployeeRecord,
        on_delete=models.CASCADE,
        related_name="direct_report_relationships",
    )
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="manager_changes",
    )
    note = models.CharField(max_length=220, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-id"]
        indexes = [
            models.Index(fields=["company", "employee", "effective_from"]),
            models.Index(fields=["company", "manager_employee", "effective_from"]),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} -> {self.manager_employee_id} ({self.effective_from})"

    def clean(self):
        super().clean()
        if self.employee_id == self.manager_employee_id:
            raise ValidationError("Employee cannot report to self.")
        if self.employee and self.employee.company_id != self.company_id:
            raise ValidationError("Employee must belong to the same company.")
        if self.manager_employee and self.manager_employee.company_id != self.company_id:
            raise ValidationError("Manager employee must belong to the same company.")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError("effective_to cannot be earlier than effective_from.")

    def is_active_on(self, at_date: date) -> bool:
        if self.effective_from > at_date:
            return False
        if self.effective_to and self.effective_to < at_date:
            return False
        return True

    @classmethod
    def current_for_employee(cls, employee: EmployeeRecord, at_date: date | None = None):
        point = at_date or timezone.localdate()
        return (
            cls.objects.filter(
                company=employee.company,
                employee=employee,
                effective_from__lte=point,
            )
            .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=point))
            .order_by("-effective_from", "-id")
            .first()
        )


class OrgAccessScope(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="access_scopes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="org_access_scopes")
    org_unit = models.ForeignKey(OrgUnit, null=True, blank=True, on_delete=models.CASCADE, related_name="access_scopes")
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.CASCADE, related_name="access_scopes")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["company__name", "user_id"]
        indexes = [
            models.Index(fields=["company", "user", "active"]),
            models.Index(fields=["org_unit", "location"]),
        ]

    def clean(self):
        super().clean()
        if self.org_unit and self.org_unit.company_id != self.company_id:
            raise ValidationError("Org unit must belong to the same company.")
        if self.location and self.location.company_id != self.company_id:
            raise ValidationError("Location must belong to the same company.")


class IntegrationEvent(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="integration_events")
    event_type = models.CharField(max_length=120)
    payload_json = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="integration_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "event_type", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.company.slug}: {self.event_type}"


class OrganizationFormField(models.Model):
    class Module(models.TextChoices):
        TALENT = "TALENT", "Talent Acquisition"
        ONBOARDING = "ONBOARDING", "Onboarding"

    class FieldType(models.TextChoices):
        TEXT = "TEXT", "Text"
        TEXTAREA = "TEXTAREA", "Textarea"
        NUMBER = "NUMBER", "Number"
        DATE = "DATE", "Date"
        EMAIL = "EMAIL", "Email"
        PHONE = "PHONE", "Phone"
        URL = "URL", "URL"
        SELECT = "SELECT", "Select"
        CHECKBOX = "CHECKBOX", "Checkbox"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="form_fields")
    module = models.CharField(max_length=20, choices=Module.choices)
    key = models.SlugField(max_length=80)
    label = models.CharField(max_length=140)
    field_type = models.CharField(max_length=20, choices=FieldType.choices, default=FieldType.TEXT)
    required = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    placeholder = models.CharField(max_length=160, blank=True, default="")
    help_text = models.CharField(max_length=220, blank=True, default="")
    options = models.JSONField(blank=True, default=list)
    org_unit = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="form_fields",
    )
    location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="form_fields",
    )
    sort_order = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["module", "sort_order", "label", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "module", "key", "org_unit", "location"],
                name="uniq_form_field_scope_key",
            )
        ]
        indexes = [
            models.Index(fields=["company", "module", "active"]),
            models.Index(fields=["company", "org_unit", "location"]),
        ]

    def __str__(self) -> str:
        return f"{self.company.slug}:{self.module}:{self.key}"

    def clean(self):
        super().clean()
        if self.org_unit and self.org_unit.company_id != self.company_id:
            raise ValidationError("Org unit must belong to the same company.")
        if self.location and self.location.company_id != self.company_id:
            raise ValidationError("Location must belong to the same company.")
