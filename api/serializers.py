from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers

from auditlog.models import AuditEvent
from leaves.models import (
    Holiday,
    LeaveAttachment,
    LeaveReasonPreset,
    LeaveRequest,
    LeaveType,
    OnboardingTaskCustomFieldValue,
    OnboardingTask,
    TalentCandidateCustomFieldValue,
    TalentCandidate,
)
from organization.models import (
    Company,
    CostCenter,
    EmployeeRecord,
    JobLevel,
    Location,
    ManagerRelationship,
    OrganizationDirectory,
    OrgUnit,
    OrganizationTenant,
    OrganizationFormField,
    Position,
)
from users.models import AdminAccount

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    manager_email = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    current_project = serializers.SerializerMethodField()
    project_status = serializers.SerializerMethodField()
    initiatives_to_take = serializers.SerializerMethodField()
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    created_in_organization_name = serializers.CharField(source="created_in_organization.name", read_only=True)
    is_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "organization",
            "organization_slug",
            "created_by",
            "created_by_name",
            "created_in_organization",
            "created_in_organization_name",
            "is_admin",
            "portal_access",
            "manager_email",
            "photo_url",
            "phone_number",
            "current_project",
            "project_status",
            "initiatives_to_take",
        ]

    def get_full_name(self, obj) -> str:
        return obj.get_full_name() or obj.username

    def get_manager_email(self, obj) -> str:
        return obj.manager.email if obj.manager and obj.manager.email else ""

    def get_created_by_name(self, obj) -> str:
        if not getattr(obj, "created_by", None):
            return ""
        return obj.created_by.get_full_name() or obj.created_by.username

    def _profile(self, obj):
        return getattr(obj, "profile", None)

    def get_photo_url(self, obj) -> str:
        profile = self._profile(obj)
        request = self.context.get("request")
        if profile and profile.photo:
            if request:
                return request.build_absolute_uri(profile.photo.url)
            return profile.photo.url
        return ""

    def get_phone_number(self, obj) -> str:
        profile = self._profile(obj)
        return profile.phone_number if profile else ""

    def get_current_project(self, obj) -> str:
        profile = self._profile(obj)
        return profile.current_project if profile else ""

    def get_project_status(self, obj) -> str:
        profile = self._profile(obj)
        return profile.project_status if profile else ""

    def get_initiatives_to_take(self, obj) -> str:
        profile = self._profile(obj)
        return profile.initiatives_to_take if profile else ""

    def get_is_admin(self, obj) -> bool:
        try:
            obj.admin_account
            return True
        except AdminAccount.DoesNotExist:
            return False


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "organization", "name", "max_days", "is_paid", "active"]


class LeaveAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = LeaveAttachment
        fields = ["id", "original_name", "size_bytes", "size_mb", "file_url", "uploaded_at"]

    def get_file_url(self, obj) -> str:
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url


class LeaveRequestSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    employee_name = serializers.SerializerMethodField()
    attachments = LeaveAttachmentSerializer(many=True, read_only=True)
    display_reason = serializers.CharField(read_only=True)
    portion_label = serializers.CharField(source="get_portion_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "organization",
            "employee",
            "employee_name",
            "leave_type",
            "leave_type_name",
            "leave_label",
            "reason_text",
            "display_reason",
            "start_date",
            "end_date",
            "portion",
            "portion_label",
            "requested_units",
            "status",
            "status_label",
            "manager_note",
            "created_at",
            "updated_at",
            "approved_at",
            "rejected_at",
            "cancelled_at",
            "attachments",
        ]

    def get_employee_name(self, obj) -> str:
        return obj.employee.get_full_name() or obj.employee.username


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "organization", "date", "name"]


class LeaveReasonPresetSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveReasonPreset
        fields = ["id", "organization", "label", "active"]


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "uuid", "name", "slug", "active"]


class AdminAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminAccount
        fields = ["id", "user", "organization", "level", "can_manage_users", "can_manage_organizations"]


class OrganizationDirectorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationDirectory
        fields = ["id", "uuid", "name", "slug", "active", "company"]


class OrganizationTenantSerializer(serializers.ModelSerializer):
    directory_name = serializers.CharField(source="directory.name", read_only=True)

    class Meta:
        model = OrganizationTenant
        fields = ["id", "directory", "directory_name", "company", "schema_name", "domain", "active"]


class OrgUnitSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)

    class Meta:
        model = OrgUnit
        fields = [
            "id",
            "company",
            "name",
            "unit_type",
            "parent",
            "parent_name",
            "active",
            "effective_from",
            "effective_to",
        ]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "company", "name", "country", "city", "timezone", "active"]


class CostCenterSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = CostCenter
        fields = ["id", "company", "code", "name", "owner", "owner_name", "active"]

    def get_owner_name(self, obj) -> str:
        if not obj.owner:
            return ""
        return obj.owner.get_full_name() or obj.owner.username


class JobLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobLevel
        fields = ["id", "company", "name", "rank_band", "active"]


class PositionSerializer(serializers.ModelSerializer):
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    cost_center_code = serializers.CharField(source="cost_center.code", read_only=True)
    job_level_name = serializers.CharField(source="job_level.name", read_only=True)
    manager_position_title = serializers.CharField(source="manager_position.title", read_only=True)

    class Meta:
        model = Position
        fields = [
            "id",
            "company",
            "title",
            "org_unit",
            "org_unit_name",
            "location",
            "location_name",
            "cost_center",
            "cost_center_code",
            "job_level",
            "job_level_name",
            "manager_position",
            "manager_position_title",
            "headcount",
            "active",
        ]


class EmployeeRecordSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    position_title = serializers.CharField(source="position.title", read_only=True)
    org_unit_id = serializers.IntegerField(source="position.org_unit_id", read_only=True)
    org_unit_name = serializers.CharField(source="position.org_unit.name", read_only=True)
    location_id = serializers.IntegerField(source="position.location_id", read_only=True)
    location_name = serializers.CharField(source="position.location.name", read_only=True)
    current_manager_employee_id = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeRecord
        fields = [
            "id",
            "company",
            "user",
            "user_name",
            "user_email",
            "position",
            "position_title",
            "org_unit_id",
            "org_unit_name",
            "location_id",
            "location_name",
            "status",
            "join_date",
            "exit_date",
            "current_manager_employee_id",
        ]

    def get_user_name(self, obj) -> str:
        if not obj.user:
            return ""
        return obj.user.get_full_name() or obj.user.username

    def get_user_email(self, obj) -> str:
        return obj.user.email if obj.user else ""

    def get_current_manager_employee_id(self, obj) -> int | None:
        rel = ManagerRelationship.current_for_employee(obj)
        return rel.manager_employee_id if rel else None


class OrganizationFormFieldSerializer(serializers.ModelSerializer):
    module_label = serializers.CharField(source="get_module_display", read_only=True)
    field_type_label = serializers.CharField(source="get_field_type_display", read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = OrganizationFormField
        fields = [
            "id",
            "company",
            "module",
            "module_label",
            "key",
            "label",
            "field_type",
            "field_type_label",
            "required",
            "active",
            "placeholder",
            "help_text",
            "options",
            "org_unit",
            "org_unit_name",
            "location",
            "location_name",
            "sort_order",
            "created_at",
            "updated_at",
        ]


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = ["id", "actor_name", "action", "entity_type", "entity_id", "meta_json", "created_at"]

    def get_actor_name(self, obj) -> str:
        if not obj.actor:
            return "System"
        return obj.actor.get_full_name() or obj.actor.username


class TalentCandidateSerializer(serializers.ModelSerializer):
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    task_count = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    company_slug = serializers.CharField(source="company.slug", read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    cost_center_code = serializers.CharField(source="cost_center.code", read_only=True)
    hiring_manager_name = serializers.SerializerMethodField()
    custom_fields = serializers.SerializerMethodField()

    class Meta:
        model = TalentCandidate
        fields = [
            "id",
            "full_name",
            "email",
            "company",
            "company_slug",
            "org_unit",
            "org_unit_name",
            "location",
            "location_name",
            "cost_center",
            "cost_center_code",
            "hiring_manager",
            "hiring_manager_name",
            "phone",
            "role_applied",
            "source",
            "expected_join",
            "resume_link",
            "owner",
            "owner_name",
            "stage",
            "stage_label",
            "notes",
            "task_count",
            "custom_fields",
            "created_at",
            "updated_at",
        ]

    def get_task_count(self, obj) -> int:
        return obj.onboarding_tasks.count()

    def get_owner_name(self, obj) -> str:
        if not obj.owner:
            return ""
        return obj.owner.get_full_name() or obj.owner.username

    def get_hiring_manager_name(self, obj) -> str:
        if not obj.hiring_manager or not obj.hiring_manager.user:
            return ""
        return obj.hiring_manager.user.get_full_name() or obj.hiring_manager.user.username

    def get_custom_fields(self, obj) -> list[dict]:
        values = (
            obj.custom_fields.select_related("field").all()
            if hasattr(obj, "custom_fields")
            else TalentCandidateCustomFieldValue.objects.select_related("field").filter(candidate=obj)
        )
        return [
            {
                "field_id": value.field_id,
                "key": value.field.key,
                "label": value.field.label,
                "field_type": value.field.field_type,
                "value": value.value_text,
            }
            for value in values
        ]


class OnboardingTaskSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    candidate_name = serializers.CharField(source="candidate.full_name", read_only=True)
    owner_name = serializers.SerializerMethodField()
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    company_slug = serializers.CharField(source="company.slug", read_only=True)
    custom_fields = serializers.SerializerMethodField()

    class Meta:
        model = OnboardingTask
        fields = [
            "id",
            "company",
            "company_slug",
            "candidate",
            "candidate_name",
            "title",
            "description",
            "due_date",
            "owner",
            "owner_name",
            "status",
            "status_label",
            "category",
            "category_label",
            "custom_fields",
            "created_at",
            "updated_at",
        ]

    def get_owner_name(self, obj) -> str:
        if not obj.owner:
            return ""
        return obj.owner.get_full_name() or obj.owner.username

    def get_custom_fields(self, obj) -> list[dict]:
        values = (
            obj.custom_fields.select_related("field").all()
            if hasattr(obj, "custom_fields")
            else OnboardingTaskCustomFieldValue.objects.select_related("field").filter(task=obj)
        )
        return [
            {
                "field_id": value.field_id,
                "key": value.field.key,
                "label": value.field.label,
                "field_type": value.field.field_type,
                "value": value.value_text,
            }
            for value in values
        ]


class DashboardSummarySerializer(serializers.Serializer):
    current_year = serializers.IntegerField()
    total_leaves = serializers.DecimalField(max_digits=8, decimal_places=2)
    leaves_taken = serializers.DecimalField(max_digits=8, decimal_places=2)
    remaining_balance = serializers.DecimalField(max_digits=8, decimal_places=2)
    recent_requests = LeaveRequestSerializer(many=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for key in ("total_leaves", "leaves_taken", "remaining_balance"):
            value = data.get(key)
            if isinstance(value, Decimal):
                data[key] = f"{value:.2f}"
        return data
