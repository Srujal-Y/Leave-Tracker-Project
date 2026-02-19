from django.contrib import admin

from .models import (
    Company,
    CostCenter,
    EmployeeRecord,
    IntegrationEvent,
    JobLevel,
    Location,
    ManagerRelationship,
    OrgAccessScope,
    OrganizationDirectory,
    OrganizationFormField,
    OrganizationTenant,
    OrgUnit,
    Position,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "uuid", "name", "slug", "active", "created_at")
    search_fields = ("name", "slug", "uuid")
    list_filter = ("active",)


@admin.register(OrganizationDirectory)
class OrganizationDirectoryAdmin(admin.ModelAdmin):
    list_display = ("id", "uuid", "name", "slug", "active", "company", "created_at")
    search_fields = ("name", "slug", "uuid", "company__name")
    list_filter = ("active",)


@admin.register(OrganizationTenant)
class OrganizationTenantAdmin(admin.ModelAdmin):
    list_display = ("id", "schema_name", "domain", "company", "directory", "active", "created_at")
    search_fields = ("schema_name", "domain", "company__name", "directory__name")
    list_filter = ("active",)


@admin.register(OrgUnit)
class OrgUnitAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "unit_type", "company", "parent", "active")
    search_fields = ("name", "company__name")
    list_filter = ("unit_type", "active", "company")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "city", "country", "timezone", "company", "active")
    search_fields = ("name", "city", "country", "company__name")
    list_filter = ("active", "company")


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "company", "owner", "active")
    search_fields = ("code", "name", "company__name")
    list_filter = ("active", "company")


@admin.register(JobLevel)
class JobLevelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "rank_band", "company", "active")
    search_fields = ("name", "company__name")
    list_filter = ("active", "company")


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "company", "org_unit", "location", "job_level", "headcount", "active")
    search_fields = ("title", "company__name", "org_unit__name")
    list_filter = ("active", "company", "org_unit", "location")


@admin.register(EmployeeRecord)
class EmployeeRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "company", "position", "status", "join_date", "exit_date")
    search_fields = ("user__username", "user__email", "position__title")
    list_filter = ("status", "company")


@admin.register(ManagerRelationship)
class ManagerRelationshipAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "employee", "manager_employee", "effective_from", "effective_to")
    search_fields = ("employee__user__username", "manager_employee__user__username")
    list_filter = ("company",)


@admin.register(OrgAccessScope)
class OrgAccessScopeAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "user", "org_unit", "location", "active")
    search_fields = ("user__username", "user__email")
    list_filter = ("active", "company")


@admin.register(IntegrationEvent)
class IntegrationEventAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "event_type", "created_by", "created_at")
    search_fields = ("event_type", "company__name")
    list_filter = ("company", "event_type")


@admin.register(OrganizationFormField)
class OrganizationFormFieldAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "module", "key", "label", "field_type", "required", "active", "org_unit", "location")
    search_fields = ("key", "label", "company__name")
    list_filter = ("module", "field_type", "required", "active", "company")
