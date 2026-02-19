from __future__ import annotations

import csv
import json
from io import StringIO
from calendar import monthcalendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from secrets import randbelow
from uuid import UUID

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import get_connection
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils.text import slugify
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from auditlog.models import AuditEvent
from leaves.forms import HolidayForm, LeaveReasonPresetForm, LeaveRequestForm, LeaveTypeForm
from leaves.models import (
    Holiday,
    LeaveAttachment,
    LeaveBalance,
    LeaveReasonPreset,
    LeaveRequest,
    LeaveType,
    OnboardingTaskCustomFieldValue,
    OnboardingTask,
    TalentCandidateCustomFieldValue,
    TalentCandidate,
)
from leaves.views import _audit, _notify_leave_submission, _team_conflicts, _validate_balance
from organization.context import (
    get_or_create_default_company,
    infer_company_ids_for_user,
    resolve_company_context,
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
from organization.services import (
    build_reporting_tree,
    change_manager,
    emit_integration_event,
    get_current_manager,
    get_direct_reports,
    get_employee_for_user,
    get_indirect_reports,
    has_hr_scope_access,
    resolve_company,
)
from users.models import AdminAccount, PasswordResetOTP
from users.models import User as UserModel
from users.permissions import can_manage_organizations, is_admin as user_is_admin

from .permissions import IsAdminOnly, IsAdminOrHR
from .serializers import (
    AuditEventSerializer,
    AdminAccountSerializer,
    DashboardSummarySerializer,
    CompanySerializer,
    CostCenterSerializer,
    EmployeeRecordSerializer,
    HolidaySerializer,
    JobLevelSerializer,
    LeaveReasonPresetSerializer,
    LeaveRequestSerializer,
    LeaveTypeSerializer,
    LocationSerializer,
    OnboardingTaskSerializer,
    OrganizationDirectorySerializer,
    OrganizationFormFieldSerializer,
    OrganizationTenantSerializer,
    OrgUnitSerializer,
    PositionSerializer,
    TalentCandidateSerializer,
    UserSerializer,
)

User = get_user_model()


def _form_error_payload(form) -> dict:
    payload: dict[str, list[str]] = {}
    for key, errors in form.errors.items():
        payload[key] = [str(error) for error in errors]
    return payload


def _to_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_admin_or_hr(user) -> bool:
    hr_value = "HR"
    role_enum = getattr(user.__class__, "Role", None)
    if role_enum is not None and hasattr(role_enum, "HR"):
        hr_value = role_enum.HR
    return bool(user_is_admin(user) or getattr(user, "role", "") == hr_value)


def _is_admin(user) -> bool:
    return bool(user_is_admin(user))


def _is_platform_admin(user) -> bool:
    try:
        admin_account = user.admin_account
    except AdminAccount.DoesNotExist:
        return False
    return admin_account.level == AdminAccount.Level.PLATFORM


def _organization_admin_company_id(user) -> int | None:
    try:
        admin_account = user.admin_account
    except AdminAccount.DoesNotExist:
        return None
    if admin_account.level != AdminAccount.Level.ORGANIZATION:
        return None
    return admin_account.organization_id


def _scoped_admin_target_user(request, pk: int):
    if _is_platform_admin(request.user):
        return User.objects.filter(pk=pk).first()

    org_admin_company_id = _organization_admin_company_id(request.user)
    if org_admin_company_id:
        return User.objects.filter(pk=pk, organization_id=org_admin_company_id).first()

    company = _company_from_request(request)
    return User.objects.filter(pk=pk, organization=company).first()


def _is_manager(user) -> bool:
    manager_value = "MANAGER"
    role_enum = getattr(user.__class__, "Role", None)
    if role_enum is not None and hasattr(role_enum, "MANAGER"):
        manager_value = role_enum.MANAGER
    return getattr(user, "role", "") == manager_value


def _get_default_company() -> Company:
    return get_or_create_default_company()


def _is_org_context_exempt_path(path: str) -> bool:
    exact_paths = set(getattr(settings, "ORG_CONTEXT_EXEMPT_PATHS", []))
    if path in exact_paths:
        return True
    prefixes = tuple(getattr(settings, "ORG_CONTEXT_EXEMPT_PATH_PREFIXES", []))
    return any(path.startswith(prefix) for prefix in prefixes)


def _company_from_request(request) -> Company:
    company = getattr(request, "organization_context", None)
    if company:
        return company
    path = getattr(request, "path", "") or ""
    require_explicit = bool(getattr(settings, "REQUIRE_EXPLICIT_ORG_CONTEXT", False))
    if _is_org_context_exempt_path(path):
        require_explicit = False
    company = resolve_company_context(
        request,
        request.user,
        allow_request_data=True,
        require_explicit=require_explicit,
        bind_user_organization=True,
    )
    request.organization_context = company
    request.organization_context_id = company.id
    request.organization_context_slug = company.slug
    return company


def _form_field_scope_rank(field: OrganizationFormField, org_unit_id: int | None, location_id: int | None) -> int:
    rank = 0
    if field.org_unit_id:
        if not org_unit_id or field.org_unit_id != org_unit_id:
            return -1
        rank += 2
    if field.location_id:
        if not location_id or field.location_id != location_id:
            return -1
        rank += 1
    return rank


def _scoped_form_fields(
    *,
    company: Company,
    module: str,
    org_unit_id: int | None = None,
    location_id: int | None = None,
    active_only: bool = True,
) -> list[OrganizationFormField]:
    queryset = OrganizationFormField.objects.filter(company=company, module=module)
    if active_only:
        queryset = queryset.filter(active=True)

    if org_unit_id:
        queryset = queryset.filter(Q(org_unit_id=org_unit_id) | Q(org_unit__isnull=True))
    else:
        queryset = queryset.filter(org_unit__isnull=True)

    if location_id:
        queryset = queryset.filter(Q(location_id=location_id) | Q(location__isnull=True))
    else:
        queryset = queryset.filter(location__isnull=True)

    selected: dict[str, tuple[int, OrganizationFormField]] = {}
    for field in queryset.order_by("sort_order", "id"):
        rank = _form_field_scope_rank(field, org_unit_id, location_id)
        if rank < 0:
            continue
        existing = selected.get(field.key)
        if not existing or rank > existing[0]:
            selected[field.key] = (rank, field)

    return sorted(
        [item[1] for item in selected.values()],
        key=lambda field: (field.sort_order, field.label.lower(), field.id),
    )


def _normalize_custom_fields_payload(raw_payload) -> list[dict]:
    payload = raw_payload
    if payload is None:
        return []
    if isinstance(payload, str):
        if not payload.strip():
            return []
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []

    if isinstance(payload, dict):
        normalized = []
        for key, value in payload.items():
            item = {"value": value}
            key_str = str(key)
            if key_str.isdigit():
                item["field_id"] = int(key_str)
            else:
                item["key"] = key_str
            normalized.append(item)
        return normalized

    if isinstance(payload, list):
        normalized = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "field_id": row.get("field_id"),
                    "key": row.get("key"),
                    "value": row.get("value"),
                }
            )
        return normalized

    return []


def _coerce_custom_value(raw_value) -> str:
    if isinstance(raw_value, bool):
        return "true" if raw_value else "false"
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def _normalize_field_options(raw_options) -> list[str]:
    if raw_options is None:
        return []
    if isinstance(raw_options, list):
        return [str(item).strip() for item in raw_options if str(item).strip()]
    if isinstance(raw_options, str):
        value = raw_options.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _upsert_talent_custom_values(candidate: TalentCandidate, raw_payload, replace: bool = False):
    if not candidate.company_id:
        return
    scoped_fields = _scoped_form_fields(
        company=candidate.company,
        module=OrganizationFormField.Module.TALENT,
        org_unit_id=candidate.org_unit_id,
        location_id=candidate.location_id,
    )
    by_id = {field.id: field for field in scoped_fields}
    by_key = {field.key: field for field in scoped_fields}
    items = _normalize_custom_fields_payload(raw_payload)
    submitted_field_ids: set[int] = set()

    for item in items:
        field = None
        field_id = item.get("field_id")
        if str(field_id).isdigit():
            field = by_id.get(int(field_id))
        if not field:
            key = str(item.get("key") or "").strip()
            field = by_key.get(key)
        if not field:
            continue
        value_text = _coerce_custom_value(item.get("value"))
        if field.required and not value_text:
            raise ValidationError(f"{field.label} is required.")
        TalentCandidateCustomFieldValue.objects.update_or_create(
            candidate=candidate,
            field=field,
            defaults={"value_text": value_text},
        )
        submitted_field_ids.add(field.id)

    if replace:
        scoped_ids = [field.id for field in scoped_fields]
        delete_qs = TalentCandidateCustomFieldValue.objects.filter(candidate=candidate, field_id__in=scoped_ids)
        if submitted_field_ids:
            delete_qs = delete_qs.exclude(field_id__in=submitted_field_ids)
        delete_qs.delete()

        for field in scoped_fields:
            if not field.required:
                continue
            existing_value = TalentCandidateCustomFieldValue.objects.filter(candidate=candidate, field=field).first()
            if not existing_value or not existing_value.value_text.strip():
                raise ValidationError(f"{field.label} is required.")


def _upsert_onboarding_custom_values(task: OnboardingTask, raw_payload, replace: bool = False):
    company = task.company or (task.candidate.company if task.candidate_id else None)
    if not company:
        return
    scoped_fields = _scoped_form_fields(
        company=company,
        module=OrganizationFormField.Module.ONBOARDING,
        org_unit_id=task.candidate.org_unit_id if task.candidate_id else None,
        location_id=task.candidate.location_id if task.candidate_id else None,
    )
    by_id = {field.id: field for field in scoped_fields}
    by_key = {field.key: field for field in scoped_fields}
    items = _normalize_custom_fields_payload(raw_payload)
    submitted_field_ids: set[int] = set()

    for item in items:
        field = None
        field_id = item.get("field_id")
        if str(field_id).isdigit():
            field = by_id.get(int(field_id))
        if not field:
            key = str(item.get("key") or "").strip()
            field = by_key.get(key)
        if not field:
            continue
        value_text = _coerce_custom_value(item.get("value"))
        if field.required and not value_text:
            raise ValidationError(f"{field.label} is required.")
        OnboardingTaskCustomFieldValue.objects.update_or_create(
            task=task,
            field=field,
            defaults={"value_text": value_text},
        )
        submitted_field_ids.add(field.id)

    if replace:
        scoped_ids = [field.id for field in scoped_fields]
        delete_qs = OnboardingTaskCustomFieldValue.objects.filter(task=task, field_id__in=scoped_ids)
        if submitted_field_ids:
            delete_qs = delete_qs.exclude(field_id__in=submitted_field_ids)
        delete_qs.delete()

        for field in scoped_fields:
            if not field.required:
                continue
            existing_value = OnboardingTaskCustomFieldValue.objects.filter(task=task, field=field).first()
            if not existing_value or not existing_value.value_text.strip():
                raise ValidationError(f"{field.label} is required.")


def _is_manager_of(request_user, target_user, company: Company) -> bool:
    manager_employee = get_employee_for_user(request_user, company)
    target_employee = get_employee_for_user(target_user, company)
    if manager_employee and target_employee:
        target_manager = get_current_manager(target_employee)
        if target_manager and target_manager.id == manager_employee.id:
            return True
        all_reports = {e.id for e in get_indirect_reports(manager_employee)}
        if target_employee.id in all_reports:
            return True
    return bool(getattr(target_user, "manager_id", None) == request_user.id)


def _parse_iso_date(raw_value: str | None, fallback: date | None = None) -> date | None:
    value = (raw_value or "").strip()
    if not value:
        return fallback
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_location_from_payload(company: Company, raw_location_id, raw_location_name) -> Location | None:
    location_name = str(raw_location_name or "").strip()
    location_id = str(raw_location_id or "").strip()

    if location_id and location_id.lower() not in {"none", "null"}:
        if not location_id.isdigit():
            raise ValidationError("Invalid location value.")
        location = Location.objects.filter(company=company, id=int(location_id)).first()
        if not location:
            raise ValidationError("Invalid location for selected company.")
        return location

    if not location_name:
        return None

    location = (
        Location.objects.filter(company=company, name__iexact=location_name)
        .order_by("id")
        .first()
    )
    if location:
        return location

    created = Location.objects.create(
        company=company,
        name=location_name,
        country="",
        city="",
        timezone="UTC",
        active=True,
    )
    emit_integration_event(
        "location.updated",
        company=company,
        payload={"location_id": created.id, "action": "created"},
        actor=None,
    )
    return created


def _audit_event(actor, action: str, entity_type: str, entity_id: str, meta: dict | None = None):
    AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta_json=json.dumps(meta or {}, default=str),
    )


def _require_org_write_access(request, company: Company, org_unit_id: int | None = None, location_id: int | None = None):
    if _is_admin(request.user):
        return None
    if not _is_admin_or_hr(request.user):
        return Response({"detail": "Only admin/HR can modify organization data."}, status=status.HTTP_403_FORBIDDEN)
    if has_hr_scope_access(request.user, company, org_unit_id=org_unit_id, location_id=location_id):
        return None
    return Response({"detail": "You do not have HR scope access for this org/location."}, status=status.HTTP_403_FORBIDDEN)


def _hr_scoped_employee_queryset(request, company: Company):
    queryset = EmployeeRecord.objects.filter(company=company).select_related(
        "user",
        "position__org_unit",
        "position__location",
        "position__cost_center",
        "position__job_level",
    )
    if _is_admin(request.user):
        return queryset
    if _is_admin_or_hr(request.user):
        allowed_ids: list[int] = []
        for record in queryset:
            if has_hr_scope_access(
                request.user,
                company,
                org_unit_id=record.position.org_unit_id,
                location_id=record.position.location_id,
            ):
                allowed_ids.append(record.id)
        return queryset.filter(id__in=allowed_ids) if allowed_ids else queryset.none()
    manager_employee = get_employee_for_user(request.user, company)
    if not manager_employee:
        own_record = get_employee_for_user(request.user, company)
        return queryset.filter(id=own_record.id) if own_record else queryset.none()
    report_ids = [employee.id for employee in get_indirect_reports(manager_employee)]
    report_ids.append(manager_employee.id)
    return queryset.filter(id__in=report_ids)


def _candidate_default_onboarding_payload(candidate: TalentCandidate) -> list[dict]:
    due_anchor = candidate.expected_join or timezone.localdate()
    return [
        {
            "title": "Collect HR Documents",
            "description": "Collect and verify employee onboarding documents.",
            "category": OnboardingTask.Category.HR,
            "due_date": due_anchor,
            "owner": candidate.owner,
        },
        {
            "title": "Set Up IT Access",
            "description": "Provision email, SSO, and required software access.",
            "category": OnboardingTask.Category.IT,
            "due_date": due_anchor,
            "owner": candidate.hiring_manager.user if candidate.hiring_manager and candidate.hiring_manager.user_id else None,
        },
        {
            "title": "Facilities Readiness",
            "description": "Prepare workspace, access badge, and day-one logistics.",
            "category": OnboardingTask.Category.FACILITIES,
            "due_date": due_anchor,
            "owner": None,
        },
    ]


def _provision_employee_and_onboarding(candidate: TalentCandidate, actor):
    if candidate.stage != TalentCandidate.Stage.HIRED:
        return None
    if not candidate.company_id or not candidate.org_unit_id or not candidate.location_id or not candidate.cost_center_id:
        return None

    job_level = JobLevel.objects.filter(company_id=candidate.company_id, active=True).order_by("rank_band", "id").first()
    if not job_level:
        job_level = JobLevel.objects.create(company_id=candidate.company_id, name="L1", rank_band=1, active=True)

    position, _ = Position.objects.get_or_create(
        company_id=candidate.company_id,
        title=candidate.role_applied,
        org_unit_id=candidate.org_unit_id,
        location_id=candidate.location_id,
        cost_center_id=candidate.cost_center_id,
        job_level=job_level,
        defaults={"headcount": 1, "active": True},
    )

    user = User.objects.filter(email__iexact=candidate.email).first()
    employee_record = None
    if user:
        if not user.organization_id:
            user.organization_id = candidate.company_id
            user.save(update_fields=["organization"])
        employee_record, created = EmployeeRecord.objects.get_or_create(
            company_id=candidate.company_id,
            user=user,
            defaults={
                "position": position,
                "status": EmployeeRecord.Status.PENDING_JOIN,
                "join_date": candidate.expected_join or timezone.localdate(),
            },
        )
        if not created and employee_record.position_id != position.id:
            previous_position_id = employee_record.position_id
            employee_record.position = position
            employee_record.save(update_fields=["position", "updated_at"])
            emit_integration_event(
                "employee.position.changed",
                company=candidate.company,
                payload={
                    "employee_id": employee_record.id,
                    "old_position_id": previous_position_id,
                    "new_position_id": position.id,
                },
                actor=actor,
            )
            _audit_event(
                actor,
                "EMPLOYEE_POSITION_CHANGED",
                "EmployeeRecord",
                str(employee_record.id),
                {"old_position_id": previous_position_id, "new_position_id": position.id},
            )

        if candidate.hiring_manager_id:
            current = ManagerRelationship.current_for_employee(employee_record)
            if not current or current.manager_employee_id != candidate.hiring_manager_id:
                change_manager(
                    company=candidate.company,
                    employee=employee_record,
                    manager_employee=candidate.hiring_manager,
                    effective_from=candidate.expected_join or timezone.localdate(),
                    actor=actor,
                    note="Auto-assigned from Talent Candidate hiring manager",
                )

    existing_titles = set(
        OnboardingTask.objects.filter(candidate=candidate).values_list("title", flat=True)
    )
    for task_payload in _candidate_default_onboarding_payload(candidate):
        if task_payload["title"] in existing_titles:
            continue
        OnboardingTask.objects.create(
            company=candidate.company,
            candidate=candidate,
            title=task_payload["title"],
            description=task_payload["description"],
            due_date=task_payload["due_date"],
            status=OnboardingTask.Status.PENDING,
            category=task_payload["category"],
            owner=task_payload["owner"],
        )
    return employee_record


def _filtered_leave_queryset(request):
    queryset = LeaveRequest.objects.select_related("employee", "leave_type").prefetch_related("attachments")
    company = _company_from_request(request)
    queryset = queryset.filter(organization=company)

    search = (request.GET.get("q") or "").strip()
    employee_id = (request.GET.get("employee") or "").strip()
    leave_type_id = (request.GET.get("leave_type") or "").strip()
    month_value = (request.GET.get("month") or "").strip()
    portion_filter = (request.GET.get("portion") or "").strip().upper()
    status_filter = (request.GET.get("status") or "").strip().upper()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    if not _is_admin_or_hr(request.user):
        scope = Q(employee=request.user)
        if _is_manager(request.user):
            manager_employee = get_employee_for_user(request.user, company)
            if manager_employee:
                report_user_ids = [emp.user_id for emp in get_indirect_reports(manager_employee) if emp.user_id]
                if report_user_ids:
                    scope |= Q(employee_id__in=report_user_ids)
            fallback_report_ids = list(User.objects.filter(manager=request.user).values_list("id", flat=True))
            if fallback_report_ids:
                scope |= Q(employee_id__in=fallback_report_ids)
        queryset = queryset.filter(scope)
    else:
        if not _is_admin(request.user):
            scoped_user_ids = []
            records = (
                EmployeeRecord.objects.filter(company=company)
                .select_related("position__org_unit", "position__location")
                .only("user_id", "position__org_unit_id", "position__location_id")
            )
            for rec in records:
                if rec.user_id and has_hr_scope_access(
                    request.user,
                    company,
                    org_unit_id=rec.position.org_unit_id,
                    location_id=rec.position.location_id,
                ):
                    scoped_user_ids.append(rec.user_id)
            if scoped_user_ids:
                queryset = queryset.filter(employee_id__in=scoped_user_ids)
            else:
                queryset = queryset.none()
        if employee_id.isdigit():
            queryset = queryset.filter(employee_id=int(employee_id))
    if employee_id.isdigit() and not _is_admin_or_hr(request.user):
        queryset = queryset.filter(employee_id=int(employee_id))

    queryset = queryset.filter(is_deleted=False)

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__username__icontains=search)
            | Q(employee__email__icontains=search)
            | Q(reason_text__icontains=search)
            | Q(leave_label__icontains=search)
        )
    if leave_type_id.isdigit():
        queryset = queryset.filter(leave_type_id=int(leave_type_id))
    if portion_filter in {LeaveRequest.Portion.FULL, LeaveRequest.Portion.HALF, LeaveRequest.Portion.QUARTER}:
        queryset = queryset.filter(portion=portion_filter)
    if status_filter in {
        LeaveRequest.Status.PENDING,
        LeaveRequest.Status.APPROVED,
        LeaveRequest.Status.REJECTED,
        LeaveRequest.Status.CANCELLED,
    }:
        queryset = queryset.filter(status=status_filter)
    if month_value:
        try:
            month_start = datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
            queryset = queryset.filter(start_date__lte=month_end, end_date__gte=month_start)
        except ValueError:
            pass
    if date_from:
        queryset = queryset.filter(end_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(start_date__lte=date_to)
    return queryset.order_by("-created_at")


def _parse_ics_holidays(raw_text: str) -> list[tuple[date, str]]:
    # Support simple RFC5545 parsing for all-day or datetime DTSTART fields.
    lines: list[str] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip("\r\n")
        if not line:
            continue
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line.strip()
        else:
            lines.append(line.strip())

    events: list[tuple[date, str]] = []
    in_event = False
    summary = ""
    dtstart = ""

    def flush_event():
        nonlocal summary, dtstart
        if not dtstart:
            summary = ""
            return
        value = dtstart
        if ":" in value:
            value = value.split(":", 1)[1].strip()
        if "T" in value:
            value = value.split("T", 1)[0]
        try:
            parsed = datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            summary = ""
            dtstart = ""
            return
        label = summary or "Public Holiday"
        events.append((parsed, label[:120]))
        summary = ""
        dtstart = ""

    for line in lines:
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            in_event = True
            summary = ""
            dtstart = ""
            continue
        if upper == "END:VEVENT":
            if in_event:
                flush_event()
            in_event = False
            continue
        if not in_event:
            continue
        if upper.startswith("SUMMARY"):
            summary = line.split(":", 1)[1].strip() if ":" in line else ""
        elif upper.startswith("DTSTART"):
            dtstart = line

    return events


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username_or_email = (request.data.get("username") or request.data.get("email") or "").strip()
        password = request.data.get("password") or ""
        if not username_or_email or not password:
            return Response({"detail": "Username/email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        lookup_user = User.objects.filter(email__iexact=username_or_email).first()
        if not lookup_user:
            lookup_user = User.objects.filter(username__iexact=username_or_email).first()
        auth_username = lookup_user.username if lookup_user else username_or_email
        user = authenticate(request, username=auth_username, password=password)

        if not user:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        if not _is_admin(user):
            allowed_for_main = {
                UserModel.PortalAccess.MAIN,
                UserModel.PortalAccess.BOTH,
            }
            if getattr(user, "portal_access", UserModel.PortalAccess.BOTH) not in allowed_for_main:
                return Response(
                    {"detail": "This account is not allowed to access the Main Leave Tracker."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        if not _is_admin(user) and not getattr(user, "organization_id", None):
            company = resolve_company(user) or _get_default_company()
            user.organization = company
            user.save(update_fields=["organization"])

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user, context={"request": request}).data,
            }
        )


class MeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)


class PasswordResetRequestAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first() or User.objects.filter(username__iexact=email).first()
        if not user:
            return Response({"detail": "No account found with this email."}, status=status.HTTP_400_BAD_REQUEST)

        recent = (
            PasswordResetOTP.objects.filter(user=user, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if recent and recent.expires_at > timezone.now() and (timezone.now() - recent.created_at) < timedelta(minutes=1):
            otp = recent
        else:
            otp = PasswordResetOTP.objects.create(
                organization=user.organization,
                user=user,
                code=f"{randbelow(1_000_000):06d}",
                expires_at=PasswordResetOTP.expiry_timestamp(),
            )

        reset_link = request.build_absolute_uri(f"/password-reset/verify/{otp.token}/")
        try:
            connection = get_connection(timeout=getattr(settings, "EMAIL_TIMEOUT", 20))
            sent_count = send_mail(
                "Leave Tracker OTP Password Reset",
                f"OTP: {otp.code}\nExpires in 10 minutes.\nReset link: {reset_link}",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
                connection=connection,
            )
        except Exception:
            return Response(
                {
                    "detail": "OTP email request timed out or failed. Check SMTP host/port/credentials.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if sent_count < 1:
            return Response(
                {"detail": "OTP email could not be sent. Check SMTP config."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        payload = {
            "message": "OTP sent to your email.",
            "token": str(otp.token),
        }
        if settings.DEBUG and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
            payload["debug_otp"] = otp.code
            payload["warning"] = "Console email backend enabled. OTP is printed in terminal."
        return Response(payload)


class PasswordResetVerifyAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, token):
        try:
            token_value = UUID(str(token))
        except ValueError:
            return Response({"detail": "Invalid reset token."}, status=status.HTTP_400_BAD_REQUEST)

        otp = PasswordResetOTP.objects.filter(token=token_value).first()
        if not otp:
            return Response({"detail": "Reset token not found."}, status=status.HTTP_404_NOT_FOUND)
        if otp.used_at:
            return Response({"detail": "OTP already used. Request a new one."}, status=status.HTTP_400_BAD_REQUEST)
        if otp.is_expired():
            return Response({"detail": "OTP expired. Request a new one."}, status=status.HTTP_400_BAD_REQUEST)

        code = (request.data.get("code") or "").strip()
        new_password = request.data.get("new_password") or ""
        confirm_password = request.data.get("confirm_password") or ""

        if len(code) != 6 or not code.isdigit():
            return Response({"detail": "Enter a valid 6-digit OTP."}, status=status.HTTP_400_BAD_REQUEST)
        if code != otp.code:
            return Response({"detail": "Incorrect OTP."}, status=status.HTTP_400_BAD_REQUEST)
        if not new_password:
            return Response({"detail": "New password is required."}, status=status.HTTP_400_BAD_REQUEST)
        if new_password != confirm_password:
            return Response({"detail": "Passwords do not match."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user=otp.user)
        except ValidationError as validation_error:
            message = " ".join(validation_error.messages)
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        user = otp.user
        user.set_password(new_password)
        user.save(update_fields=["password"])
        otp.mark_used()
        return Response({"message": "Password updated. Please login."})


class DashboardSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        current_year = timezone.localdate().year
        totals = LeaveBalance.objects.filter(
            user=request.user,
            organization=company,
            year=current_year,
        ).aggregate(
            total=Sum("allocated_days"),
            used=Sum("used_days"),
        )
        total_leaves = totals["total"] or Decimal("0.00")
        leaves_taken = totals["used"] or Decimal("0.00")
        remaining_balance = total_leaves - leaves_taken
        if remaining_balance < 0:
            remaining_balance = Decimal("0.00")

        recent_requests = (
            LeaveRequest.objects.filter(employee=request.user, organization=company, is_deleted=False)
            .select_related("leave_type", "employee")
            .prefetch_related("attachments")
            .order_by("-created_at")[:5]
        )
        payload = {
            "current_year": current_year,
            "total_leaves": total_leaves,
            "leaves_taken": leaves_taken,
            "remaining_balance": remaining_balance,
            "recent_requests": recent_requests,
        }
        serializer = DashboardSummarySerializer(payload, context={"request": request})
        return Response(serializer.data)


class LeaveTypeListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = LeaveType.objects.filter(organization=company, active=True).order_by("name")
        return Response(LeaveTypeSerializer(queryset, many=True).data)

    def post(self, request):
        if not _is_admin_or_hr(request.user):
            return Response({"detail": "Only admin/HR can create leave types."}, status=status.HTTP_403_FORBIDDEN)
        company = _company_from_request(request)
        form = LeaveTypeForm(request.data, company=company)
        if not form.is_valid():
            return Response({"errors": _form_error_payload(form)}, status=status.HTTP_400_BAD_REQUEST)
        leave_type = form.save()
        return Response(LeaveTypeSerializer(leave_type).data, status=status.HTTP_201_CREATED)


class LeaveTypeDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def patch(self, request, pk: int):
        company = _company_from_request(request)
        leave_type = LeaveType.objects.filter(pk=pk, organization=company).first()
        if not leave_type:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        form = LeaveTypeForm(request.data, instance=leave_type, company=company)
        if not form.is_valid():
            return Response({"errors": _form_error_payload(form)}, status=status.HTTP_400_BAD_REQUEST)
        leave_type = form.save()
        return Response(LeaveTypeSerializer(leave_type).data)


class LeaveReasonPresetListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = LeaveReasonPreset.objects.filter(organization=company, active=True).order_by("label")
        return Response(LeaveReasonPresetSerializer(queryset, many=True).data)

    def post(self, request):
        if not _is_admin_or_hr(request.user):
            return Response({"detail": "Only admin/HR can create reason presets."}, status=status.HTTP_403_FORBIDDEN)
        company = _company_from_request(request)
        form = LeaveReasonPresetForm(request.data, company=company)
        if not form.is_valid():
            return Response({"errors": _form_error_payload(form)}, status=status.HTTP_400_BAD_REQUEST)
        preset = form.save()
        return Response(LeaveReasonPresetSerializer(preset).data, status=status.HTTP_201_CREATED)


class LeaveReasonPresetDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def patch(self, request, pk: int):
        company = _company_from_request(request)
        preset = LeaveReasonPreset.objects.filter(pk=pk, organization=company).first()
        if not preset:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        form = LeaveReasonPresetForm(request.data, instance=preset, company=company)
        if not form.is_valid():
            return Response({"errors": _form_error_payload(form)}, status=status.HTTP_400_BAD_REQUEST)
        preset = form.save()
        return Response(LeaveReasonPresetSerializer(preset).data)


class LeaveRequestListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        queryset = _filtered_leave_queryset(request)

        paginator = PageNumberPagination()
        paginator.page_size = 12
        page = paginator.paginate_queryset(queryset, request)
        serializer = LeaveRequestSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        company = _company_from_request(request)
        form = LeaveRequestForm(request.data, request.FILES, user=request.user, company=company)
        if not form.is_valid():
            return Response({"errors": _form_error_payload(form)}, status=status.HTTP_400_BAD_REQUEST)

        recent_cutoff = timezone.now() - timedelta(minutes=1)
        if LeaveRequest.objects.filter(
            employee=request.user,
            organization=company,
            created_at__gte=recent_cutoff,
        ).count() >= settings.LEAVE_RATE_LIMIT_PER_MINUTE:
            return Response(
                {"detail": "Rate limit exceeded. Please wait a minute before creating another request."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        leave_request: LeaveRequest = form.save(commit=False)
        leave_request.organization = company
        leave_request.employee = request.user
        leave_request.status = LeaveRequest.Status.PENDING
        leave_request.requested_units = leave_request.compute_requested_units()

        balance_errors = _validate_balance(leave_request)
        if balance_errors:
            return Response({"errors": {"non_field_errors": balance_errors}}, status=status.HTTP_400_BAD_REQUEST)

        leave_request.save()
        for document in form.cleaned_data.get("documents", []):
            LeaveAttachment.objects.create(
                leave_request=leave_request,
                file=document,
                uploaded_by=request.user,
            )

        _audit(request.user, "LEAVE_CREATED_API", leave_request)
        _notify_leave_submission(leave_request)
        conflicts = [d.isoformat() for d in _team_conflicts(leave_request)]

        serializer = LeaveRequestSerializer(leave_request, context={"request": request})
        return Response(
            {
                "message": "Leave request submitted and marked as Pending approval.",
                "team_conflict_dates": conflicts,
                "leave_request": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class LeaveRequestDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, request, pk: int) -> LeaveRequest | None:
        company = _company_from_request(request)
        queryset = LeaveRequest.objects.select_related("employee", "leave_type", "approver").prefetch_related("attachments")
        obj = queryset.filter(pk=pk, organization=company, is_deleted=False).first()
        if not obj:
            return None
        if _is_admin_or_hr(request.user) or obj.employee_id == request.user.id:
            return obj
        return None

    def get(self, request, pk: int):
        leave_request = self.get_object(request, pk)
        if not leave_request:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = LeaveRequestSerializer(leave_request, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, pk: int):
        leave_request = self.get_object(request, pk)
        if not leave_request:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if leave_request.status != LeaveRequest.Status.PENDING:
            return Response({"detail": "Only pending requests can be edited."}, status=status.HTTP_400_BAD_REQUEST)
        if not (_is_admin_or_hr(request.user) or leave_request.employee_id == request.user.id):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()
        default_values = {
            "leave_type": str(leave_request.leave_type_id),
            "leave_label": leave_request.leave_label,
            "start_date": leave_request.start_date.isoformat(),
            "end_date": leave_request.end_date.isoformat(),
            "portion": leave_request.portion,
            "reason_preset": str(leave_request.reason_preset_id) if leave_request.reason_preset_id else "",
            "reason_text": leave_request.reason_text,
        }
        for key, default_value in default_values.items():
            if key not in data:
                data[key] = default_value

        form = LeaveRequestForm(
            data,
            request.FILES,
            instance=leave_request,
            user=leave_request.employee,
            company=leave_request.organization,
        )
        if not form.is_valid():
            return Response({"errors": _form_error_payload(form)}, status=status.HTTP_400_BAD_REQUEST)

        updated_request: LeaveRequest = form.save(commit=False)
        updated_request.organization = leave_request.organization
        updated_request.status = LeaveRequest.Status.PENDING
        updated_request.requested_units = updated_request.compute_requested_units()

        balance_errors = _validate_balance(updated_request)
        if balance_errors:
            return Response({"errors": {"non_field_errors": balance_errors}}, status=status.HTTP_400_BAD_REQUEST)

        updated_request.save()
        for document in form.cleaned_data.get("documents", []):
            LeaveAttachment.objects.create(
                leave_request=updated_request,
                file=document,
                uploaded_by=request.user,
            )
        _audit(request.user, "LEAVE_EDITED_API", updated_request)
        serializer = LeaveRequestSerializer(updated_request, context={"request": request})
        return Response(serializer.data)

    def delete(self, request, pk: int):
        leave_request = self.get_object(request, pk)
        if not leave_request:
            return Response(status=status.HTTP_204_NO_CONTENT)
        if not (_is_admin_or_hr(request.user) or leave_request.employee_id == request.user.id):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if leave_request.status == LeaveRequest.Status.APPROVED:
            return Response(
                {"detail": "Approved leave cannot be cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if leave_request.status != LeaveRequest.Status.PENDING:
            return Response(
                {"detail": "Only pending leave requests can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        leave_request.status = LeaveRequest.Status.CANCELLED
        leave_request.cancelled_at = timezone.now()
        leave_request.save(update_fields=["status", "cancelled_at", "updated_at"])
        _audit(request.user, "LEAVE_CANCELLED_API", leave_request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LeaveReviewAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk: int):
        company = _company_from_request(request)
        leave_request = LeaveRequest.objects.filter(pk=pk, organization=company, is_deleted=False).first()
        if not leave_request:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not (_is_admin_or_hr(request.user) or _is_manager_of(request.user, leave_request.employee, company)):
            return Response({"detail": "You are not allowed to review this leave request."}, status=status.HTTP_403_FORBIDDEN)

        action = (request.data.get("action") or "").strip().lower()
        note = (request.data.get("manager_note") or "").strip()
        if action not in {"approve", "reject"}:
            return Response({"detail": "Action must be approve or reject."}, status=status.HTTP_400_BAD_REQUEST)

        leave_request.manager_note = note
        leave_request.approver = request.user

        if action == "approve":
            leave_request.status = LeaveRequest.Status.APPROVED
            leave_request.approved_at = timezone.now()
            leave_request.rejected_at = None
        else:
            leave_request.status = LeaveRequest.Status.REJECTED
            leave_request.rejected_at = timezone.now()
            leave_request.approved_at = None

        leave_request.save()
        _audit(request.user, f"LEAVE_{action.upper()}D_API", leave_request)
        serializer = LeaveRequestSerializer(leave_request, context={"request": request})
        return Response(serializer.data)


class HolidayListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = Holiday.objects.filter(organization=company).order_by("date")
        return Response(HolidaySerializer(queryset, many=True).data)

    def post(self, request):
        if not IsAdminOnly().has_permission(request, self):
            return Response({"detail": "Only admin users can add holidays."}, status=status.HTTP_403_FORBIDDEN)
        company = _company_from_request(request)
        form = HolidayForm(request.data, company=company)
        if not form.is_valid():
            return Response({"errors": _form_error_payload(form)}, status=status.HTTP_400_BAD_REQUEST)
        holiday = form.save()
        return Response(HolidaySerializer(holiday).data, status=status.HTTP_201_CREATED)


class HolidayDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]

    def patch(self, request, pk: int):
        company = _company_from_request(request)
        holiday = Holiday.objects.filter(pk=pk, organization=company).first()
        if not holiday:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        form = HolidayForm(request.data, instance=holiday, company=company)
        if not form.is_valid():
            return Response({"errors": _form_error_payload(form)}, status=status.HTTP_400_BAD_REQUEST)
        holiday = form.save()
        return Response(HolidaySerializer(holiday).data)

    def delete(self, request, pk: int):
        company = _company_from_request(request)
        holiday = Holiday.objects.filter(pk=pk, organization=company).first()
        if not holiday:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        holiday.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HolidayImportICSAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        company = _company_from_request(request)
        uploaded = request.FILES.get("file")
        inline_text = request.data.get("ics_text") or ""

        if uploaded:
            try:
                raw_text = uploaded.read().decode("utf-8")
            except UnicodeDecodeError:
                raw_text = uploaded.read().decode("latin-1", errors="ignore")
        else:
            raw_text = str(inline_text)

        if not raw_text.strip():
            return Response({"detail": "Upload a valid .ics file."}, status=status.HTTP_400_BAD_REQUEST)

        parsed = _parse_ics_holidays(raw_text)
        if not parsed:
            return Response(
                {"detail": "No calendar events were found in the uploaded file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = 0
        updated = 0
        unchanged = 0
        for holiday_date, holiday_name in parsed:
            existing = Holiday.objects.filter(organization=company, date=holiday_date).first()
            if not existing:
                Holiday.objects.create(organization=company, date=holiday_date, name=holiday_name)
                created += 1
                continue
            if existing.name != holiday_name:
                existing.name = holiday_name
                existing.save(update_fields=["name"])
                updated += 1
            else:
                unchanged += 1

        return Response(
            {
                "message": "ICS holidays imported successfully.",
                "processed": len(parsed),
                "created": created,
                "updated": updated,
                "unchanged": unchanged,
            }
        )


class OrganizationContextAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        selected_company = _company_from_request(request)
        resolved_schema = (
            getattr(request, "organization_context_schema", "")
            or (request.headers.get("X-DTS-SCHEMA", "") or "").strip().lower()
            or (selected_company.slug if selected_company else "")
        )
        explicit_company = None
        explicit_error = None
        try:
            explicit_company = resolve_company_context(
                request,
                request.user,
                allow_request_data=False,
                require_explicit=True,
                bind_user_organization=False,
            )
        except Exception as exc:  # pragma: no cover - debug endpoint safety
            explicit_error = str(getattr(exc, "detail", exc))

        return Response(
            {
                "strict_mode_enabled": bool(getattr(settings, "REQUIRE_EXPLICIT_ORG_CONTEXT", False)),
                "postgres_schema_tenancy_enabled": bool(
                    getattr(settings, "ENABLE_POSTGRES_SCHEMA_TENANCY", False)
                ),
                "selected_company": CompanySerializer(selected_company).data if selected_company else None,
                "request_headers": {
                    "x_company_id": request.headers.get("X-Company-Id", ""),
                    "x_dts_schema": request.headers.get("X-DTS-SCHEMA", ""),
                },
                "resolved_schema": resolved_schema,
                "schema_switched": bool(getattr(request, "organization_context_schema_switched", False)),
                "explicit_context_valid": explicit_company is not None,
                "explicit_context_error": explicit_error,
                "explicit_company_id": explicit_company.id if explicit_company else None,
                "accessible_company_ids": infer_company_ids_for_user(request.user),
            }
        )


class CompanyDirectoryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = Company.objects.filter(active=True).order_by("name")
        if not _is_admin(request.user):
            if getattr(request.user, "organization_id", None):
                queryset = queryset.filter(id=request.user.organization_id)
            else:
                company_ids = list(
                    EmployeeRecord.objects.filter(user=request.user).values_list("company_id", flat=True)
                )
                queryset = queryset.filter(id__in=company_ids) if company_ids else queryset.none()

        selected = _company_from_request(request)
        return Response(
            {
                "selected_company_id": selected.id if selected else None,
                "results": CompanySerializer(queryset, many=True).data,
            }
        )

    def post(self, request):
        if not can_manage_organizations(request.user):
            return Response({"detail": "Only platform admin can add organizations."}, status=status.HTTP_403_FORBIDDEN)

        name = (request.data.get("name") or "").strip()
        requested_slug = slugify((request.data.get("slug") or "").strip().lower())
        schema_name = (request.data.get("schema_name") or "").strip().lower()
        domain = (request.data.get("domain") or "").strip().lower()

        if not name:
            return Response({"detail": "name is required."}, status=status.HTTP_400_BAD_REQUEST)
        base_slug = requested_slug or slugify(name) or "organization"
        slug = base_slug
        existing_same_name = Company.objects.filter(name__iexact=name).first()
        if not existing_same_name:
            suffix = 2
            while Company.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{suffix}"
                suffix += 1

        if not schema_name:
            schema_name = slug
        if not schema_name:
            return Response({"detail": "schema_name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not domain:
            domain = f"{schema_name}.leave.local"

        with transaction.atomic():
            company = existing_same_name
            if not company:
                company, _ = Company.objects.get_or_create(
                    slug=slug,
                    defaults={"name": name, "active": True},
                )
            if company.name != name:
                company.name = name
                company.save(update_fields=["name"])
            if not company.active:
                company.active = True
                company.save(update_fields=["active"])

            directory, _ = OrganizationDirectory.objects.get_or_create(
                slug=company.slug,
                defaults={
                    "name": name,
                    "active": True,
                    "company": company,
                },
            )
            updates = []
            if directory.name != name:
                directory.name = name
                updates.append("name")
            if directory.company_id != company.id:
                directory.company = company
                updates.append("company")
            if not directory.active:
                directory.active = True
                updates.append("active")
            if updates:
                directory.save(update_fields=updates)

            tenant, created = OrganizationTenant.objects.get_or_create(
                company=company,
                defaults={
                    "directory": directory,
                    "schema_name": schema_name,
                    "domain": domain,
                    "active": True,
                },
            )
            if not created:
                tenant_updates = []
                if tenant.directory_id != directory.id:
                    tenant.directory = directory
                    tenant_updates.append("directory")
                if tenant.schema_name != schema_name:
                    tenant.schema_name = schema_name
                    tenant_updates.append("schema_name")
                if tenant.domain != domain:
                    tenant.domain = domain
                    tenant_updates.append("domain")
                if not tenant.active:
                    tenant.active = True
                    tenant_updates.append("active")
                if tenant_updates:
                    tenant.save(update_fields=tenant_updates)

        return Response(
            {
                "company": CompanySerializer(company).data,
                "directory": OrganizationDirectorySerializer(directory).data,
                "tenant": OrganizationTenantSerializer(tenant).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        if not can_manage_organizations(request.user):
            return Response({"detail": "Only platform admin can update organizations."}, status=status.HTTP_403_FORBIDDEN)

        raw_id = str(request.data.get("id") or "").strip()
        if not raw_id.isdigit():
            return Response({"detail": "id is required."}, status=status.HTTP_400_BAD_REQUEST)

        company = Company.objects.filter(pk=int(raw_id)).first()
        if not company:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        updates: list[str] = []
        if "name" in request.data:
            new_name = str(request.data.get("name") or "").strip()
            if not new_name:
                return Response({"detail": "name cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
            company.name = new_name
            updates.append("name")

        if "active" in request.data:
            company.active = _to_bool(request.data.get("active"), default=company.active)
            updates.append("active")

        if updates:
            company.save(update_fields=updates)

            if "name" in request.data:
                OrganizationDirectory.objects.filter(company=company).update(name=company.name)
            if "active" in request.data:
                OrganizationDirectory.objects.filter(company=company).update(active=company.active)
                OrganizationTenant.objects.filter(company=company).update(active=company.active)

        return Response({"company": CompanySerializer(company).data})


class OrganizationTenantListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]

    def get(self, request):
        queryset = OrganizationTenant.objects.select_related("company", "directory").order_by("schema_name")
        return Response(OrganizationTenantSerializer(queryset, many=True).data)


class OrganizationFormFieldListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        module = (request.GET.get("module") or "").strip().upper()
        org_unit_id = request.GET.get("org_unit")
        location_id = request.GET.get("location")
        include_inactive = _to_bool(request.GET.get("include_inactive"), False)
        scoped = _to_bool(request.GET.get("scoped"), True)

        if module and module not in OrganizationFormField.Module.values:
            return Response({"detail": "Invalid module value."}, status=status.HTTP_400_BAD_REQUEST)

        org_unit = int(org_unit_id) if str(org_unit_id).isdigit() else None
        location = int(location_id) if str(location_id).isdigit() else None

        if module and scoped:
            fields = _scoped_form_fields(
                company=company,
                module=module,
                org_unit_id=org_unit,
                location_id=location,
                active_only=not include_inactive,
            )
            return Response(OrganizationFormFieldSerializer(fields, many=True).data)

        queryset = OrganizationFormField.objects.filter(company=company)
        if module:
            queryset = queryset.filter(module=module)
        if not include_inactive:
            queryset = queryset.filter(active=True)
        if org_unit:
            queryset = queryset.filter(Q(org_unit_id=org_unit) | Q(org_unit__isnull=True))
        if location:
            queryset = queryset.filter(Q(location_id=location) | Q(location__isnull=True))
        queryset = queryset.select_related("org_unit", "location").order_by("module", "sort_order", "id")
        return Response(OrganizationFormFieldSerializer(queryset, many=True).data)

    def post(self, request):
        company = _company_from_request(request)
        module = (request.data.get("module") or "").strip().upper()
        if module not in OrganizationFormField.Module.values:
            return Response({"detail": "module must be TALENT or ONBOARDING."}, status=status.HTTP_400_BAD_REQUEST)

        org_unit_id = int(request.data.get("org_unit")) if str(request.data.get("org_unit")).isdigit() else None
        location_id = int(request.data.get("location")) if str(request.data.get("location")).isdigit() else None
        denied = _require_org_write_access(request, company, org_unit_id=org_unit_id, location_id=location_id)
        if denied:
            return denied

        payload = request.data.copy()
        payload["company"] = company.id
        payload["module"] = module
        payload["options"] = _normalize_field_options(request.data.get("options"))

        serializer = OrganizationFormFieldSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        form_field = serializer.save()
        _audit_event(
            request.user,
            "ORG_FORM_FIELD_CREATED",
            "OrganizationFormField",
            str(form_field.id),
            {"module": form_field.module, "key": form_field.key},
        )
        return Response(OrganizationFormFieldSerializer(form_field).data, status=status.HTTP_201_CREATED)


class OrganizationFormFieldDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request, pk: int) -> OrganizationFormField | None:
        company = _company_from_request(request)
        return OrganizationFormField.objects.filter(company=company, id=pk).first()

    def patch(self, request, pk: int):
        form_field = self.get_object(request, pk)
        if not form_field:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        org_unit_id = (
            int(request.data.get("org_unit"))
            if str(request.data.get("org_unit")).isdigit()
            else form_field.org_unit_id
        )
        location_id = (
            int(request.data.get("location"))
            if str(request.data.get("location")).isdigit()
            else form_field.location_id
        )
        denied = _require_org_write_access(request, form_field.company, org_unit_id=org_unit_id, location_id=location_id)
        if denied:
            return denied

        payload = request.data.copy()
        payload["company"] = form_field.company_id
        if "options" in payload:
            payload["options"] = _normalize_field_options(payload.get("options"))
        serializer = OrganizationFormFieldSerializer(form_field, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        form_field = serializer.save()
        _audit_event(
            request.user,
            "ORG_FORM_FIELD_UPDATED",
            "OrganizationFormField",
            str(form_field.id),
            {"module": form_field.module, "key": form_field.key},
        )
        return Response(OrganizationFormFieldSerializer(form_field).data)

    def delete(self, request, pk: int):
        form_field = self.get_object(request, pk)
        if not form_field:
            return Response(status=status.HTTP_204_NO_CONTENT)
        denied = _require_org_write_access(
            request,
            form_field.company,
            org_unit_id=form_field.org_unit_id,
            location_id=form_field.location_id,
        )
        if denied:
            return denied
        form_field.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrgUnitDirectoryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = OrgUnit.objects.filter(company=company).select_related("parent")
        query = (request.GET.get("q") or "").strip()
        parent = (request.GET.get("parent") or "").strip()
        unit_type = (request.GET.get("type") or "").strip().upper()
        active = (request.GET.get("active") or "").strip().lower()

        if query:
            queryset = queryset.filter(name__icontains=query)
        if parent.isdigit():
            queryset = queryset.filter(parent_id=int(parent))
        if unit_type in {OrgUnit.UnitType.DEPARTMENT, OrgUnit.UnitType.TEAM}:
            queryset = queryset.filter(unit_type=unit_type)
        if active in {"true", "false"}:
            queryset = queryset.filter(active=(active == "true"))
        return Response(OrgUnitSerializer(queryset.order_by("name"), many=True).data)

    def post(self, request):
        company = _company_from_request(request)
        denied = _require_org_write_access(request, company)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = OrgUnitSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        unit = serializer.save()
        emit_integration_event(
            "org.unit.updated",
            company=company,
            payload={"org_unit_id": unit.id, "action": "created"},
            actor=request.user,
        )
        _audit_event(request.user, "ORG_UNIT_CREATED", "OrgUnit", str(unit.id), {"name": unit.name})
        return Response(OrgUnitSerializer(unit).data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        company = _company_from_request(request)
        unit_id = request.data.get("id") or request.query_params.get("id")
        if not str(unit_id).isdigit():
            return Response({"detail": "id is required for patch."}, status=status.HTTP_400_BAD_REQUEST)
        unit = OrgUnit.objects.filter(company=company, id=int(unit_id)).first()
        if not unit:
            return Response({"detail": "Org unit not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = _require_org_write_access(request, company, org_unit_id=unit.id)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = OrgUnitSerializer(unit, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        unit = serializer.save()
        emit_integration_event(
            "org.unit.updated",
            company=company,
            payload={"org_unit_id": unit.id, "action": "updated"},
            actor=request.user,
        )
        _audit_event(request.user, "ORG_UNIT_UPDATED", "OrgUnit", str(unit.id), {"name": unit.name})
        return Response(OrgUnitSerializer(unit).data)


class LocationDirectoryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = Location.objects.filter(company=company)
        query = (request.GET.get("q") or "").strip()
        active = (request.GET.get("active") or "").strip().lower()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(country__icontains=query) | Q(city__icontains=query))
        if active in {"true", "false"}:
            queryset = queryset.filter(active=(active == "true"))
        return Response(LocationSerializer(queryset.order_by("name"), many=True).data)

    def post(self, request):
        company = _company_from_request(request)
        denied = _require_org_write_access(request, company)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = LocationSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        location = serializer.save()
        emit_integration_event(
            "location.updated",
            company=company,
            payload={"location_id": location.id, "action": "created"},
            actor=request.user,
        )
        _audit_event(request.user, "LOCATION_CREATED", "Location", str(location.id), {"name": location.name})
        return Response(LocationSerializer(location).data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        company = _company_from_request(request)
        location_id = request.data.get("id") or request.query_params.get("id")
        if not str(location_id).isdigit():
            return Response({"detail": "id is required for patch."}, status=status.HTTP_400_BAD_REQUEST)
        location = Location.objects.filter(company=company, id=int(location_id)).first()
        if not location:
            return Response({"detail": "Location not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = _require_org_write_access(request, company, location_id=location.id)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = LocationSerializer(location, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        location = serializer.save()
        emit_integration_event(
            "location.updated",
            company=company,
            payload={"location_id": location.id, "action": "updated"},
            actor=request.user,
        )
        _audit_event(request.user, "LOCATION_UPDATED", "Location", str(location.id), {"name": location.name})
        return Response(LocationSerializer(location).data)


class CostCenterDirectoryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = CostCenter.objects.filter(company=company).select_related("owner")
        query = (request.GET.get("q") or "").strip()
        if query:
            queryset = queryset.filter(Q(code__icontains=query) | Q(name__icontains=query))
        return Response(CostCenterSerializer(queryset.order_by("code"), many=True).data)

    def post(self, request):
        company = _company_from_request(request)
        denied = _require_org_write_access(request, company)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = CostCenterSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        center = serializer.save()
        _audit_event(request.user, "COST_CENTER_CREATED", "CostCenter", str(center.id), {"code": center.code})
        return Response(CostCenterSerializer(center).data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        company = _company_from_request(request)
        center_id = request.data.get("id") or request.query_params.get("id")
        if not str(center_id).isdigit():
            return Response({"detail": "id is required for patch."}, status=status.HTTP_400_BAD_REQUEST)
        center = CostCenter.objects.filter(company=company, id=int(center_id)).first()
        if not center:
            return Response({"detail": "Cost center not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = _require_org_write_access(request, company)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = CostCenterSerializer(center, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        center = serializer.save()
        _audit_event(request.user, "COST_CENTER_UPDATED", "CostCenter", str(center.id), {"code": center.code})
        return Response(CostCenterSerializer(center).data)


class JobLevelDirectoryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = JobLevel.objects.filter(company=company)
        query = (request.GET.get("q") or "").strip()
        if query:
            queryset = queryset.filter(name__icontains=query)
        return Response(JobLevelSerializer(queryset.order_by("rank_band", "name"), many=True).data)

    def post(self, request):
        company = _company_from_request(request)
        denied = _require_org_write_access(request, company)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = JobLevelSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        level = serializer.save()
        _audit_event(request.user, "JOB_LEVEL_CREATED", "JobLevel", str(level.id), {"name": level.name})
        return Response(JobLevelSerializer(level).data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        company = _company_from_request(request)
        level_id = request.data.get("id") or request.query_params.get("id")
        if not str(level_id).isdigit():
            return Response({"detail": "id is required for patch."}, status=status.HTTP_400_BAD_REQUEST)
        level = JobLevel.objects.filter(company=company, id=int(level_id)).first()
        if not level:
            return Response({"detail": "Job level not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = _require_org_write_access(request, company)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = JobLevelSerializer(level, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        level = serializer.save()
        _audit_event(request.user, "JOB_LEVEL_UPDATED", "JobLevel", str(level.id), {"name": level.name})
        return Response(JobLevelSerializer(level).data)


class PositionDirectoryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = Position.objects.filter(company=company).select_related(
            "org_unit",
            "location",
            "cost_center",
            "job_level",
            "manager_position",
        )
        org_unit = (request.GET.get("org_unit") or "").strip()
        location = (request.GET.get("location") or "").strip()
        manager = (request.GET.get("manager") or "").strip()
        query = (request.GET.get("q") or "").strip()

        if org_unit.isdigit():
            queryset = queryset.filter(org_unit_id=int(org_unit))
        if location.isdigit():
            queryset = queryset.filter(location_id=int(location))
        if manager.isdigit():
            queryset = queryset.filter(manager_position_id=int(manager))
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(org_unit__name__icontains=query)
                | Q(location__name__icontains=query)
                | Q(cost_center__code__icontains=query)
            )
        return Response(PositionSerializer(queryset.order_by("title"), many=True).data)

    def post(self, request):
        company = _company_from_request(request)
        org_unit_id = int(request.data.get("org_unit")) if str(request.data.get("org_unit")).isdigit() else None
        location_id = int(request.data.get("location")) if str(request.data.get("location")).isdigit() else None
        denied = _require_org_write_access(request, company, org_unit_id=org_unit_id, location_id=location_id)
        if denied:
            return denied
        payload = request.data.copy()
        payload["company"] = company.id
        serializer = PositionSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        position = serializer.save()
        _audit_event(request.user, "POSITION_CREATED", "Position", str(position.id), {"title": position.title})
        return Response(PositionSerializer(position).data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        company = _company_from_request(request)
        position_id = request.data.get("id") or request.query_params.get("id")
        if not str(position_id).isdigit():
            return Response({"detail": "id is required for patch."}, status=status.HTTP_400_BAD_REQUEST)
        position = Position.objects.filter(company=company, id=int(position_id)).first()
        if not position:
            return Response({"detail": "Position not found."}, status=status.HTTP_404_NOT_FOUND)

        org_unit_id = int(request.data.get("org_unit")) if str(request.data.get("org_unit")).isdigit() else position.org_unit_id
        location_id = int(request.data.get("location")) if str(request.data.get("location")).isdigit() else position.location_id
        denied = _require_org_write_access(request, company, org_unit_id=org_unit_id, location_id=location_id)
        if denied:
            return denied

        payload = request.data.copy()
        payload["company"] = company.id
        serializer = PositionSerializer(position, data=payload, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        position = serializer.save()
        _audit_event(request.user, "POSITION_UPDATED", "Position", str(position.id), {"title": position.title})
        return Response(PositionSerializer(position).data)


class HREmployeeDirectoryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        queryset = _hr_scoped_employee_queryset(request, company)
        org_unit = (request.GET.get("org_unit") or "").strip()
        location = (request.GET.get("location") or "").strip()
        manager = (request.GET.get("manager") or "").strip()
        status_filter = (request.GET.get("status") or "").strip().upper()
        query = (request.GET.get("q") or "").strip()

        if org_unit.isdigit():
            queryset = queryset.filter(position__org_unit_id=int(org_unit))
        if location.isdigit():
            queryset = queryset.filter(position__location_id=int(location))
        if status_filter in EmployeeRecord.Status.values:
            queryset = queryset.filter(status=status_filter)
        if query:
            queryset = queryset.filter(
                Q(user__username__icontains=query)
                | Q(user__email__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(position__title__icontains=query)
            )
        if manager.isdigit():
            manager_id = int(manager)
            matching_ids: list[int] = []
            for record in queryset:
                current = ManagerRelationship.current_for_employee(record)
                if current and current.manager_employee_id == manager_id:
                    matching_ids.append(record.id)
            queryset = queryset.filter(id__in=matching_ids) if matching_ids else queryset.none()
        return Response(EmployeeRecordSerializer(queryset.order_by("id"), many=True).data)

    def patch(self, request):
        company = _company_from_request(request)
        if not _is_admin_or_hr(request.user):
            return Response({"detail": "Only admin/HR can update employee records."}, status=status.HTTP_403_FORBIDDEN)
        employee_id = request.data.get("id") or request.query_params.get("id")
        if not str(employee_id).isdigit():
            return Response({"detail": "id is required for patch."}, status=status.HTTP_400_BAD_REQUEST)
        employee = EmployeeRecord.objects.filter(company=company, id=int(employee_id)).select_related(
            "position__org_unit",
            "position__location",
        ).first()
        if not employee:
            return Response({"detail": "Employee record not found."}, status=status.HTTP_404_NOT_FOUND)

        denied = _require_org_write_access(
            request,
            company,
            org_unit_id=employee.position.org_unit_id,
            location_id=employee.position.location_id,
        )
        if denied:
            return denied

        previous_position_id = employee.position_id
        update_fields: list[str] = []

        if "position" in request.data:
            position_id = request.data.get("position")
            if not str(position_id).isdigit():
                return Response({"detail": "Invalid position id."}, status=status.HTTP_400_BAD_REQUEST)
            position = Position.objects.filter(company=company, id=int(position_id)).first()
            if not position:
                return Response({"detail": "Position not found for this company."}, status=status.HTTP_404_NOT_FOUND)
            employee.position = position
            update_fields.append("position")

        if "status" in request.data:
            status_value = (request.data.get("status") or "").strip().upper()
            if status_value not in EmployeeRecord.Status.values:
                return Response({"detail": "Invalid status value."}, status=status.HTTP_400_BAD_REQUEST)
            employee.status = status_value
            update_fields.append("status")

        if "join_date" in request.data:
            parsed = _parse_iso_date(request.data.get("join_date"))
            if not parsed:
                return Response({"detail": "Invalid join_date. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
            employee.join_date = parsed
            update_fields.append("join_date")

        if "exit_date" in request.data:
            raw_exit = request.data.get("exit_date")
            if not raw_exit:
                employee.exit_date = None
            else:
                parsed = _parse_iso_date(raw_exit)
                if not parsed:
                    return Response({"detail": "Invalid exit_date. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
                employee.exit_date = parsed
            update_fields.append("exit_date")

        if "user" in request.data:
            user_id = request.data.get("user")
            if not str(user_id).isdigit():
                return Response({"detail": "Invalid user id."}, status=status.HTTP_400_BAD_REQUEST)
            linked_user = User.objects.filter(id=int(user_id)).first()
            if not linked_user:
                return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            employee.user = linked_user
            update_fields.append("user")

        if update_fields:
            update_fields.append("updated_at")
            employee.save(update_fields=update_fields)

        if previous_position_id != employee.position_id:
            emit_integration_event(
                "employee.position.changed",
                company=company,
                payload={
                    "employee_id": employee.id,
                    "old_position_id": previous_position_id,
                    "new_position_id": employee.position_id,
                },
                actor=request.user,
            )
            _audit_event(
                request.user,
                "EMPLOYEE_POSITION_CHANGED",
                "EmployeeRecord",
                str(employee.id),
                {"old_position_id": previous_position_id, "new_position_id": employee.position_id},
            )
        else:
            _audit_event(request.user, "EMPLOYEE_UPDATED", "EmployeeRecord", str(employee.id), {"fields": update_fields})
        return Response(EmployeeRecordSerializer(employee).data)


class ReportingChangeManagerAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    @transaction.atomic
    def post(self, request):
        company = _company_from_request(request)
        employee_id = request.data.get("employee_id")
        manager_employee_id = request.data.get("manager_employee_id")
        effective_from = _parse_iso_date(request.data.get("effective_from"), fallback=timezone.localdate())
        note = (request.data.get("note") or "").strip()

        if not str(employee_id).isdigit():
            return Response({"detail": "employee_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not effective_from:
            return Response({"detail": "effective_from must be YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        employee = EmployeeRecord.objects.filter(company=company, id=int(employee_id)).first()
        if not employee:
            return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)

        manager_employee = None
        if manager_employee_id not in (None, "", "null"):
            if not str(manager_employee_id).isdigit():
                return Response({"detail": "manager_employee_id must be numeric or null."}, status=status.HTTP_400_BAD_REQUEST)
            manager_employee = EmployeeRecord.objects.filter(company=company, id=int(manager_employee_id)).first()
            if not manager_employee:
                return Response({"detail": "Manager employee not found."}, status=status.HTTP_404_NOT_FOUND)
            if manager_employee.id == employee.id:
                return Response({"detail": "Employee cannot report to self."}, status=status.HTTP_400_BAD_REQUEST)

        denied = _require_org_write_access(
            request,
            company,
            org_unit_id=employee.position.org_unit_id,
            location_id=employee.position.location_id,
        )
        if denied:
            return denied

        relationship = change_manager(
            company=company,
            employee=employee,
            manager_employee=manager_employee,
            effective_from=effective_from,
            actor=request.user,
            note=note,
        )
        _audit_event(
            request.user,
            "MANAGER_CHANGED",
            "EmployeeRecord",
            str(employee.id),
            {
                "manager_employee_id": manager_employee.id if manager_employee else None,
                "effective_from": effective_from.isoformat(),
            },
        )
        payload = EmployeeRecordSerializer(employee).data
        payload["relationship_id"] = relationship.id if relationship else None
        return Response(payload)


class ReportingDirectReportsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        manager_id = request.query_params.get("manager_id")

        manager_employee = None
        if str(manager_id).isdigit():
            manager_employee = EmployeeRecord.objects.filter(company=company, id=int(manager_id)).first()
        else:
            manager_employee = get_employee_for_user(request.user, company)

        if not manager_employee:
            return Response({"detail": "Manager employee record not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _is_admin_or_hr(request.user):
            requester = get_employee_for_user(request.user, company)
            if not requester:
                return Response({"detail": "Requester employee record not found."}, status=status.HTTP_403_FORBIDDEN)
            allowed = {requester.id}
            allowed.update([emp.id for emp in get_indirect_reports(requester)])
            if manager_employee.id not in allowed:
                return Response({"detail": "You can only view your direct/indirect reporting scope."}, status=status.HTTP_403_FORBIDDEN)

        direct_reports = get_direct_reports(manager_employee)
        return Response(
            {
                "manager_employee_id": manager_employee.id,
                "count": len(direct_reports),
                "results": EmployeeRecordSerializer(direct_reports, many=True).data,
            }
        )


class ReportingTreeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        employee_id = request.query_params.get("employee_id")
        if str(employee_id).isdigit():
            employee = EmployeeRecord.objects.filter(company=company, id=int(employee_id)).first()
        else:
            employee = get_employee_for_user(request.user, company)

        if not employee:
            return Response({"detail": "Employee record not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _is_admin_or_hr(request.user):
            requester = get_employee_for_user(request.user, company)
            if not requester:
                return Response({"detail": "Requester employee record not found."}, status=status.HTTP_403_FORBIDDEN)
            allowed = {requester.id}
            allowed.update([emp.id for emp in get_indirect_reports(requester)])
            if employee.id not in allowed:
                return Response({"detail": "You can only view your direct/indirect reporting scope."}, status=status.HTTP_403_FORBIDDEN)

        return Response(build_reporting_tree(employee))


class TalentCandidateListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def get(self, request):
        company = _company_from_request(request)
        query = (request.GET.get("q") or "").strip()
        stage = (request.GET.get("stage") or "").strip().upper()
        owner_id = (request.GET.get("owner") or "").strip()
        org_unit_id = (request.GET.get("org_unit") or "").strip()
        location_id = (request.GET.get("location") or "").strip()
        manager_id = (request.GET.get("hiring_manager") or "").strip()
        queryset = TalentCandidate.objects.filter(company=company).select_related(
            "owner",
            "company",
            "org_unit",
            "location",
            "cost_center",
            "hiring_manager__user",
        ).prefetch_related("custom_fields__field")

        if query:
            queryset = queryset.filter(
                Q(full_name__icontains=query)
                | Q(email__icontains=query)
                | Q(role_applied__icontains=query)
                | Q(source__icontains=query)
                | Q(notes__icontains=query)
            )
        if stage in TalentCandidate.Stage.values:
            queryset = queryset.filter(stage=stage)
        if owner_id.isdigit():
            queryset = queryset.filter(owner_id=int(owner_id))
        if org_unit_id.isdigit():
            queryset = queryset.filter(org_unit_id=int(org_unit_id))
        if location_id.isdigit():
            queryset = queryset.filter(location_id=int(location_id))
        if manager_id.isdigit():
            queryset = queryset.filter(hiring_manager_id=int(manager_id))

        return Response(TalentCandidateSerializer(queryset.order_by("-updated_at")[:500], many=True).data)

    def post(self, request):
        company = _company_from_request(request)
        full_name = (request.data.get("full_name") or "").strip()
        email = (request.data.get("email") or "").strip().lower()
        role_applied = (request.data.get("role_applied") or "").strip()
        phone = (request.data.get("phone") or "").strip()
        source = (request.data.get("source") or "").strip()
        stage = (request.data.get("stage") or TalentCandidate.Stage.APPLIED).strip().upper()
        expected_join_raw = (request.data.get("expected_join") or "").strip()
        resume_link = (request.data.get("resume_link") or "").strip()
        owner_id = request.data.get("owner")
        org_unit_id = request.data.get("org_unit")
        location_id = request.data.get("location")
        location_name = (request.data.get("location_name") or "").strip()
        cost_center_id = request.data.get("cost_center")
        hiring_manager_id = request.data.get("hiring_manager")
        notes = (request.data.get("notes") or "").strip()

        if not full_name or not email or not role_applied:
            return Response(
                {"detail": "full_name, email, and role_applied are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if stage not in TalentCandidate.Stage.values:
            stage = TalentCandidate.Stage.APPLIED

        expected_join = None
        if expected_join_raw:
            try:
                expected_join = datetime.strptime(expected_join_raw, "%Y-%m-%d").date()
            except ValueError:
                return Response({"detail": "Invalid expected_join format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        owner = None
        if str(owner_id).isdigit():
            owner = User.objects.filter(pk=int(owner_id), organization=company).first()
            if not owner:
                return Response({"detail": "Invalid owner for selected company."}, status=status.HTTP_400_BAD_REQUEST)
        elif owner_id in (None, "", "null"):
            owner = request.user if getattr(request.user, "organization_id", None) == company.id else None

        org_unit = None
        if str(org_unit_id).isdigit():
            org_unit = OrgUnit.objects.filter(company=company, id=int(org_unit_id)).first()
            if not org_unit:
                return Response({"detail": "Invalid org_unit for selected company."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            location = _resolve_location_from_payload(company, location_id, location_name)
        except ValidationError as exc:
            return Response({"detail": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        cost_center = None
        if str(cost_center_id).isdigit():
            cost_center = CostCenter.objects.filter(company=company, id=int(cost_center_id)).first()
            if not cost_center:
                return Response({"detail": "Invalid cost_center for selected company."}, status=status.HTTP_400_BAD_REQUEST)

        hiring_manager = None
        if str(hiring_manager_id).isdigit():
            hiring_manager = EmployeeRecord.objects.filter(company=company, id=int(hiring_manager_id)).first()
            if not hiring_manager:
                return Response({"detail": "Invalid hiring_manager for selected company."}, status=status.HTTP_400_BAD_REQUEST)

        denied = _require_org_write_access(
            request,
            company,
            org_unit_id=org_unit.id if org_unit else None,
            location_id=location.id if location else None,
        )
        if denied:
            return denied

        try:
            with transaction.atomic():
                candidate = TalentCandidate.objects.create(
                    company=company,
                    full_name=full_name,
                    email=email,
                    role_applied=role_applied,
                    org_unit=org_unit,
                    location=location,
                    cost_center=cost_center,
                    hiring_manager=hiring_manager,
                    phone=phone,
                    source=source,
                    expected_join=expected_join,
                    resume_link=resume_link,
                    owner=owner,
                    stage=stage,
                    notes=notes,
                )
                _upsert_talent_custom_values(
                    candidate,
                    request.data.get("custom_fields"),
                    replace=True,
                )
        except ValidationError as exc:
            return Response({"detail": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        _audit_event(request.user, "TALENT_CANDIDATE_CREATED", "TalentCandidate", str(candidate.id), {"stage": candidate.stage})
        if candidate.stage == TalentCandidate.Stage.HIRED:
            _provision_employee_and_onboarding(candidate, request.user)
        return Response(TalentCandidateSerializer(candidate).data, status=status.HTTP_201_CREATED)


class TalentCandidateDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def get_object(self, request, pk: int) -> TalentCandidate | None:
        company = _company_from_request(request)
        return TalentCandidate.objects.select_related(
            "owner",
            "company",
            "org_unit",
            "location",
            "cost_center",
            "hiring_manager__user",
        ).prefetch_related("custom_fields__field").filter(pk=pk, company=company).first()

    def get(self, request, pk: int):
        candidate = self.get_object(request, pk)
        if not candidate:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(TalentCandidateSerializer(candidate).data)

    def patch(self, request, pk: int):
        candidate = self.get_object(request, pk)
        if not candidate:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        company = candidate.company or _company_from_request(request)
        if candidate.company_id and candidate.company_id != company.id:
            return Response({"detail": "Candidate belongs to a different company context."}, status=status.HTTP_400_BAD_REQUEST)

        denied = _require_org_write_access(
            request,
            company,
            org_unit_id=candidate.org_unit_id,
            location_id=candidate.location_id,
        )
        if denied:
            return denied

        for field in ["full_name", "email", "phone", "role_applied", "source", "resume_link", "notes"]:
            if field in request.data:
                setattr(candidate, field, (request.data.get(field) or "").strip())
        if "stage" in request.data:
            stage = (request.data.get("stage") or "").strip().upper()
            if stage not in TalentCandidate.Stage.values:
                return Response({"detail": "Invalid stage value."}, status=status.HTTP_400_BAD_REQUEST)
            candidate.stage = stage

        if "company" in request.data and str(request.data.get("company") or "") not in ("", str(company.id)):
            return Response({"detail": "Candidate company cannot be changed across organizations."}, status=status.HTTP_400_BAD_REQUEST)

        if "org_unit" in request.data:
            raw = request.data.get("org_unit")
            if raw in (None, "", "null"):
                candidate.org_unit = None
            elif str(raw).isdigit():
                org_unit = OrgUnit.objects.filter(company=company, id=int(raw)).first()
                if not org_unit:
                    return Response({"detail": "Invalid org_unit for selected company."}, status=status.HTTP_400_BAD_REQUEST)
                candidate.org_unit = org_unit
            else:
                return Response({"detail": "Invalid org_unit value."}, status=status.HTTP_400_BAD_REQUEST)

        if "location" in request.data or "location_name" in request.data:
            raw = request.data.get("location")
            raw_name = request.data.get("location_name")
            try:
                candidate.location = _resolve_location_from_payload(company, raw, raw_name)
            except ValidationError as exc:
                return Response({"detail": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        if "cost_center" in request.data:
            raw = request.data.get("cost_center")
            if raw in (None, "", "null"):
                candidate.cost_center = None
            elif str(raw).isdigit():
                cost_center = CostCenter.objects.filter(company=company, id=int(raw)).first()
                if not cost_center:
                    return Response({"detail": "Invalid cost_center for selected company."}, status=status.HTTP_400_BAD_REQUEST)
                candidate.cost_center = cost_center
            else:
                return Response({"detail": "Invalid cost_center value."}, status=status.HTTP_400_BAD_REQUEST)

        if "hiring_manager" in request.data:
            raw = request.data.get("hiring_manager")
            if raw in (None, "", "null"):
                candidate.hiring_manager = None
            elif str(raw).isdigit():
                manager_record = EmployeeRecord.objects.filter(company=company, id=int(raw)).first()
                if not manager_record:
                    return Response({"detail": "Invalid hiring_manager for selected company."}, status=status.HTTP_400_BAD_REQUEST)
                candidate.hiring_manager = manager_record
            else:
                return Response({"detail": "Invalid hiring_manager value."}, status=status.HTTP_400_BAD_REQUEST)

        if "expected_join" in request.data:
            expected_join_raw = (request.data.get("expected_join") or "").strip()
            if not expected_join_raw:
                candidate.expected_join = None
            else:
                try:
                    candidate.expected_join = datetime.strptime(expected_join_raw, "%Y-%m-%d").date()
                except ValueError:
                    return Response(
                        {"detail": "Invalid expected_join format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        if "owner" in request.data:
            owner_id = request.data.get("owner")
            if str(owner_id).isdigit():
                candidate.owner = User.objects.filter(pk=int(owner_id), organization=company).first()
            else:
                candidate.owner = None

        candidate.save()
        if "custom_fields" in request.data:
            try:
                _upsert_talent_custom_values(
                    candidate,
                    request.data.get("custom_fields"),
                    replace=True,
                )
            except ValidationError as exc:
                return Response({"detail": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        _audit_event(request.user, "TALENT_CANDIDATE_UPDATED", "TalentCandidate", str(candidate.id), {"stage": candidate.stage})
        if candidate.stage == TalentCandidate.Stage.HIRED:
            _provision_employee_and_onboarding(candidate, request.user)
        return Response(TalentCandidateSerializer(candidate).data)

    def delete(self, request, pk: int):
        candidate = self.get_object(request, pk)
        if not candidate:
            return Response(status=status.HTTP_204_NO_CONTENT)
        candidate.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OnboardingTaskListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def get(self, request):
        company = _company_from_request(request)
        candidate_id = (request.GET.get("candidate") or "").strip()
        status_filter = (request.GET.get("status") or "").strip().upper()
        category_filter = (request.GET.get("category") or "").strip().upper()
        queryset = OnboardingTask.objects.filter(company=company).select_related("candidate", "owner").prefetch_related("custom_fields__field")

        if candidate_id.isdigit():
            queryset = queryset.filter(candidate_id=int(candidate_id))
        if status_filter in OnboardingTask.Status.values:
            queryset = queryset.filter(status=status_filter)
        if category_filter in OnboardingTask.Category.values:
            queryset = queryset.filter(category=category_filter)

        return Response(OnboardingTaskSerializer(queryset[:800], many=True).data)

    def post(self, request):
        company = _company_from_request(request)
        candidate_id = request.data.get("candidate")
        title = (request.data.get("title") or "").strip()
        description = (request.data.get("description") or "").strip()
        due_date_raw = (request.data.get("due_date") or "").strip()
        status_value = (request.data.get("status") or OnboardingTask.Status.PENDING).strip().upper()
        category_value = (request.data.get("category") or OnboardingTask.Category.GENERAL).strip().upper()
        owner_id = request.data.get("owner")

        if not str(candidate_id).isdigit() or not title:
            return Response(
                {"detail": "candidate and title are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        candidate = TalentCandidate.objects.filter(company=company, pk=int(candidate_id)).first()
        if not candidate:
            return Response({"detail": "Candidate not found."}, status=status.HTTP_404_NOT_FOUND)
        if status_value not in OnboardingTask.Status.values:
            status_value = OnboardingTask.Status.PENDING
        if category_value not in OnboardingTask.Category.values:
            category_value = OnboardingTask.Category.GENERAL

        due_date_value = None
        if due_date_raw:
            try:
                due_date_value = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
            except ValueError:
                return Response({"detail": "Invalid due_date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        owner = None
        if str(owner_id).isdigit():
            owner = User.objects.filter(pk=int(owner_id), organization=company).first()
            if not owner:
                return Response({"detail": "Invalid owner for selected company."}, status=status.HTTP_400_BAD_REQUEST)

        denied = _require_org_write_access(
            request,
            company,
            org_unit_id=candidate.org_unit_id,
            location_id=candidate.location_id,
        )
        if denied:
            return denied

        try:
            with transaction.atomic():
                task = OnboardingTask.objects.create(
                    company=company,
                    candidate=candidate,
                    title=title,
                    description=description,
                    due_date=due_date_value,
                    status=status_value,
                    category=category_value,
                    owner=owner,
                )
                _upsert_onboarding_custom_values(
                    task,
                    request.data.get("custom_fields"),
                    replace=True,
                )
        except ValidationError as exc:
            return Response({"detail": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        _audit_event(request.user, "ONBOARDING_TASK_CREATED", "OnboardingTask", str(task.id), {"status": task.status})
        return Response(OnboardingTaskSerializer(task).data, status=status.HTTP_201_CREATED)


class OnboardingTaskDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def get_object(self, request, pk: int) -> OnboardingTask | None:
        company = _company_from_request(request)
        return (
            OnboardingTask.objects.select_related("candidate", "owner", "company")
            .prefetch_related("custom_fields__field")
            .filter(pk=pk, company=company)
            .first()
        )

    def patch(self, request, pk: int):
        task = self.get_object(request, pk)
        if not task:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        denied = _require_org_write_access(
            request,
            task.company or _company_from_request(request),
            org_unit_id=task.candidate.org_unit_id if task.candidate_id else None,
            location_id=task.candidate.location_id if task.candidate_id else None,
        )
        if denied:
            return denied

        if "candidate" in request.data:
            candidate_id = request.data.get("candidate")
            if not str(candidate_id).isdigit():
                return Response({"detail": "Invalid candidate id."}, status=status.HTTP_400_BAD_REQUEST)
            candidate = TalentCandidate.objects.filter(pk=int(candidate_id), company=task.company).first()
            if not candidate:
                return Response({"detail": "Candidate not found."}, status=status.HTTP_404_NOT_FOUND)
            task.candidate = candidate

        for field in ["title", "description"]:
            if field in request.data:
                setattr(task, field, (request.data.get(field) or "").strip())

        if "due_date" in request.data:
            raw_due = (request.data.get("due_date") or "").strip()
            if not raw_due:
                task.due_date = None
            else:
                try:
                    task.due_date = datetime.strptime(raw_due, "%Y-%m-%d").date()
                except ValueError:
                    return Response(
                        {"detail": "Invalid due_date format. Use YYYY-MM-DD."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        if "status" in request.data:
            status_value = (request.data.get("status") or "").strip().upper()
            if status_value not in OnboardingTask.Status.values:
                return Response({"detail": "Invalid status value."}, status=status.HTTP_400_BAD_REQUEST)
            task.status = status_value

        if "category" in request.data:
            category_value = (request.data.get("category") or "").strip().upper()
            if category_value not in OnboardingTask.Category.values:
                return Response({"detail": "Invalid category value."}, status=status.HTTP_400_BAD_REQUEST)
            task.category = category_value

        if "owner" in request.data:
            owner_id = request.data.get("owner")
            if str(owner_id).isdigit():
                task.owner = User.objects.filter(pk=int(owner_id), organization=task.company).first()
            else:
                task.owner = None

        task.save()
        if "custom_fields" in request.data:
            try:
                _upsert_onboarding_custom_values(
                    task,
                    request.data.get("custom_fields"),
                    replace=True,
                )
            except ValidationError as exc:
                return Response({"detail": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        _audit_event(request.user, "ONBOARDING_TASK_UPDATED", "OnboardingTask", str(task.id), {"status": task.status})
        return Response(OnboardingTaskSerializer(task).data)

    def delete(self, request, pk: int):
        task = self.get_object(request, pk)
        if not task:
            return Response(status=status.HTTP_204_NO_CONTENT)
        denied = _require_org_write_access(
            request,
            task.company or _company_from_request(request),
            org_unit_id=task.candidate.org_unit_id if task.candidate_id else None,
            location_id=task.candidate.location_id if task.candidate_id else None,
        )
        if denied:
            return denied
        _audit_event(request.user, "ONBOARDING_TASK_DELETED", "OnboardingTask", str(task.id), {})
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LeaveExportCSVAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def get(self, request):
        queryset = _filtered_leave_queryset(request)
        csv_buffer = StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(
            [
                "employee",
                "email",
                "leave_type",
                "start_date",
                "end_date",
                "portion",
                "units",
                "status",
                "approver",
                "created_at",
            ]
        )
        for leave_request in queryset:
            writer.writerow(
                [
                    leave_request.employee.get_full_name() or leave_request.employee.username,
                    leave_request.employee.email,
                    leave_request.leave_type.name,
                    leave_request.start_date,
                    leave_request.end_date,
                    leave_request.get_portion_display(),
                    leave_request.requested_units,
                    leave_request.get_status_display(),
                    leave_request.approver.get_full_name() if leave_request.approver else "",
                    leave_request.created_at,
                ]
            )

        response = HttpResponse(csv_buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="leave-board-{timezone.localdate().isoformat()}.csv"'
        )
        return response


class MyIcalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        approved_requests = LeaveRequest.objects.filter(
            employee=request.user,
            organization=company,
            status=LeaveRequest.Status.APPROVED,
            is_deleted=False,
        ).order_by("start_date")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Leave Tracker//EN",
        ]
        for item in approved_requests:
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:leave-{item.pk}@leave-tracker",
                    f"DTSTAMP:{timezone.now().strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTSTART;VALUE=DATE:{item.start_date.strftime('%Y%m%d')}",
                    f"DTEND;VALUE=DATE:{(item.end_date + timedelta(days=1)).strftime('%Y%m%d')}",
                    f"SUMMARY:{item.leave_type.name} Leave",
                    f"DESCRIPTION:{item.display_reason or 'Leave'}",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        response = HttpResponse("\r\n".join(lines), content_type="text/calendar")
        response["Content-Disposition"] = "attachment; filename=my-leaves.ics"
        return response


class ProfileAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def patch(self, request):
        profile = request.user.profile
        fields = {
            "phone_number": request.data.get("phone_number", profile.phone_number),
            "current_project": request.data.get("current_project", profile.current_project),
            "project_status": request.data.get("project_status", profile.project_status),
            "initiatives_to_take": request.data.get("initiatives_to_take", profile.initiatives_to_take),
        }
        for key, value in fields.items():
            setattr(profile, key, value or "")
        if request.FILES.get("photo"):
            profile.photo = request.FILES["photo"]
        profile.save()
        return Response(UserSerializer(request.user, context={"request": request}).data)


class CalendarAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company = _company_from_request(request)
        mode = (request.GET.get("mode") or "month").strip().lower()
        month_value = (request.GET.get("month") or "").strip()
        day_value = (request.GET.get("day") or "").strip()
        week_date_value = (request.GET.get("week_date") or "").strip()
        today = timezone.localdate()

        if month_value:
            try:
                anchor = datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
            except ValueError:
                anchor = today.replace(day=1)
        else:
            anchor = today.replace(day=1)

        week_anchor = today
        if week_date_value:
            try:
                week_anchor = datetime.strptime(week_date_value, "%Y-%m-%d").date()
            except ValueError:
                pass

        week_start = week_anchor - timedelta(days=week_anchor.weekday())
        week_days = [week_start + timedelta(days=i) for i in range(7)]
        week_end = week_days[-1]

        year, month = anchor.year, anchor.month
        first_day = date(year, month, 1)
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)

        leave_qs = LeaveRequest.objects.select_related("employee", "leave_type").filter(
            organization=company,
            status=LeaveRequest.Status.APPROVED,
            is_deleted=False,
            start_date__lte=last_day,
            end_date__gte=first_day,
        )
        if not _is_admin_or_hr(request.user):
            scope = Q(employee=request.user)
            if _is_manager(request.user):
                manager_employee = get_employee_for_user(request.user, company)
                if manager_employee:
                    report_user_ids = [emp.user_id for emp in get_indirect_reports(manager_employee) if emp.user_id]
                    if report_user_ids:
                        scope |= Q(employee_id__in=report_user_ids)
                fallback_report_ids = list(User.objects.filter(manager=request.user).values_list("id", flat=True))
                if fallback_report_ids:
                    scope |= Q(employee_id__in=fallback_report_ids)
            leave_qs = leave_qs.filter(scope)
        elif not _is_admin(request.user):
            scoped_user_ids = []
            records = (
                EmployeeRecord.objects.filter(company=company)
                .select_related("position__org_unit", "position__location")
                .only("user_id", "position__org_unit_id", "position__location_id")
            )
            for rec in records:
                if rec.user_id and has_hr_scope_access(
                    request.user,
                    company,
                    org_unit_id=rec.position.org_unit_id,
                    location_id=rec.position.location_id,
                ):
                    scoped_user_ids.append(rec.user_id)
            if scoped_user_ids:
                leave_qs = leave_qs.filter(employee_id__in=scoped_user_ids)
            else:
                leave_qs = leave_qs.none()
        approved_leaves = list(leave_qs.order_by("start_date"))

        leaves_by_day: dict[int, list[dict]] = {}
        for day in range(1, last_day.day + 1):
            current = date(year, month, day)
            entries = [
                {
                    "id": leave.id,
                    "employee_name": leave.employee.get_full_name() or leave.employee.username,
                    "leave_type": leave.leave_type.name,
                    "start_date": leave.start_date,
                    "end_date": leave.end_date,
                }
                for leave in approved_leaves
                if leave.start_date <= current <= leave.end_date
            ]
            if entries:
                leaves_by_day[day] = entries

        calendar_rows: list[list[dict]] = []
        for week in monthcalendar(year, month):
            row: list[dict] = []
            for day in week:
                if not day:
                    row.append({"day": None, "entries": []})
                else:
                    row.append({"day": day, "entries": leaves_by_day.get(day, [])})
            calendar_rows.append(row)

        selected_date = None
        selected_entries: list[dict] = []
        if day_value:
            try:
                selected_date = datetime.strptime(day_value, "%Y-%m-%d").date()
                selected_entries = [
                    {
                        "id": leave.id,
                        "employee_name": leave.employee.get_full_name() or leave.employee.username,
                        "leave_type": leave.leave_type.name,
                        "start_date": leave.start_date,
                        "end_date": leave.end_date,
                    }
                    for leave in approved_leaves
                    if leave.start_date <= selected_date <= leave.end_date
                ]
            except ValueError:
                selected_date = None

        week_entries = [
            {
                "day": day.isoformat(),
                "entries": [
                    {
                        "id": leave.id,
                        "employee_name": leave.employee.get_full_name() or leave.employee.username,
                        "leave_type": leave.leave_type.name,
                        "start_date": leave.start_date,
                        "end_date": leave.end_date,
                    }
                    for leave in approved_leaves
                    if leave.start_date <= day <= leave.end_date
                ],
            }
            for day in week_days
        ]

        holidays = Holiday.objects.filter(organization=company, date__range=(first_day, last_day)).order_by("date")
        return Response(
            {
                "mode": mode,
                "anchor": anchor.isoformat(),
                "prev_month": (first_day - timedelta(days=1)).strftime("%Y-%m"),
                "next_month": next_month.strftime("%Y-%m"),
                "calendar_rows": calendar_rows,
                "selected_date": selected_date.isoformat() if selected_date else None,
                "selected_entries": selected_entries,
                "week_anchor": week_anchor.isoformat(),
                "week_entries": week_entries,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "holidays": HolidaySerializer(holidays, many=True).data,
            }
        )


class AdminAccountListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]

    def get(self, request):
        queryset = AdminAccount.objects.select_related("user", "organization").order_by("user__username")
        return Response(AdminAccountSerializer(queryset, many=True).data)

    def post(self, request):
        user_id = request.data.get("user")
        if not str(user_id).isdigit():
            return Response({"detail": "user is required."}, status=status.HTTP_400_BAD_REQUEST)
        target_user = User.objects.filter(pk=int(user_id)).first()
        if not target_user:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        level = str(request.data.get("level") or AdminAccount.Level.ORGANIZATION).strip().upper()
        if level not in {AdminAccount.Level.PLATFORM, AdminAccount.Level.ORGANIZATION}:
            return Response({"detail": "Invalid level."}, status=status.HTTP_400_BAD_REQUEST)

        organization_id = request.data.get("organization")
        organization = None
        if level == AdminAccount.Level.ORGANIZATION:
            if not str(organization_id).isdigit():
                return Response({"detail": "organization is required for organization admin."}, status=status.HTTP_400_BAD_REQUEST)
            organization = Company.objects.filter(pk=int(organization_id), active=True).first()
            if not organization:
                return Response({"detail": "Organization not found."}, status=status.HTTP_400_BAD_REQUEST)

        admin_account, _ = AdminAccount.objects.get_or_create(user=target_user)
        admin_account.level = level
        admin_account.organization = organization
        admin_account.can_manage_users = _to_bool(request.data.get("can_manage_users"), default=True)
        admin_account.can_manage_organizations = _to_bool(request.data.get("can_manage_organizations"), default=False)
        admin_account.save()
        return Response(AdminAccountSerializer(admin_account).data, status=status.HTTP_201_CREATED)


class AdminUserListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        queryset = User.objects.select_related(
            "manager",
            "organization",
            "created_by",
            "created_in_organization",
        ).order_by("username")
        if _is_platform_admin(request.user):
            pass
        elif _is_admin(request.user):
            org_admin_company_id = _organization_admin_company_id(request.user)
            if org_admin_company_id:
                queryset = queryset.filter(organization_id=org_admin_company_id)
            else:
                company = _company_from_request(request)
                queryset = queryset.filter(organization=company)
        else:
            company = _company_from_request(request)
            queryset = queryset.filter(organization=company)
        if query:
            queryset = queryset.filter(
                Q(username__icontains=query)
                | Q(email__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            )
        return Response(UserSerializer(queryset[:300], many=True, context={"request": request}).data)

    def post(self, request):
        company = _company_from_request(request)
        raw_company_id = str(request.data.get("company_id") or "").strip()
        raw_company_name = str(request.data.get("company_name") or "").strip()
        raw_company_slug = str(request.data.get("company_slug") or "").strip().lower()
        if raw_company_id:
            if not raw_company_id.isdigit():
                return Response({"detail": "Invalid company id."}, status=status.HTTP_400_BAD_REQUEST)
            target_company = Company.objects.filter(pk=int(raw_company_id), active=True).first()
            if not target_company:
                return Response({"detail": "Company not found or inactive."}, status=status.HTTP_400_BAD_REQUEST)
            if not _is_admin(request.user) and request.user.organization_id != target_company.id:
                return Response(
                    {"detail": "You cannot assign users to another company."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            company = target_company
        elif raw_company_name or raw_company_slug:
            target_company = None
            if raw_company_slug:
                target_company = Company.objects.filter(slug=raw_company_slug, active=True).first()
            if not target_company and raw_company_name:
                target_company = Company.objects.filter(name__iexact=raw_company_name, active=True).first()

            if not target_company:
                return Response(
                    {"detail": "Company not found. Add the company name first in Admin Users > Company Assignment Context."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not _is_admin(request.user) and request.user.organization_id != target_company.id:
                return Response(
                    {"detail": "You cannot assign users to another company."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            company = target_company

        email = (request.data.get("email") or "").strip().lower()
        first_name = (request.data.get("first_name") or "").strip()
        last_name = (request.data.get("last_name") or "").strip()
        role = (request.data.get("role") or UserModel.Role.EMPLOYEE).strip().upper()
        portal_access = (request.data.get("portal_access") or UserModel.PortalAccess.BOTH).strip().upper()
        manager_id = request.data.get("manager")
        if not email:
            return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username__iexact=email).exists():
            return Response({"detail": "A user with this email already exists."}, status=status.HTTP_400_BAD_REQUEST)
        if role not in {UserModel.Role.EMPLOYEE, UserModel.Role.MANAGER, UserModel.Role.HR}:
            role = UserModel.Role.EMPLOYEE
        if portal_access not in {
            UserModel.PortalAccess.MAIN,
            UserModel.PortalAccess.ORGANIZATION,
            UserModel.PortalAccess.BOTH,
        }:
            portal_access = UserModel.PortalAccess.BOTH

        manager = None
        if role == UserModel.Role.EMPLOYEE and str(manager_id).isdigit():
            manager = User.objects.filter(
                pk=int(manager_id),
                role=UserModel.Role.MANAGER,
                organization=company,
            ).first()

        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            organization=company,
            created_by=request.user if getattr(request.user, "is_authenticated", False) else None,
            created_in_organization=company,
            role=role,
            manager=manager,
            portal_access=portal_access,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        return Response(UserSerializer(user, context={"request": request}).data, status=status.HTTP_201_CREATED)


class AdminUserDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def patch(self, request, pk: int):
        actor_is_platform_admin = _is_platform_admin(request.user)
        user = _scoped_admin_target_user(request, pk)
        if not user:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if "company_id" in request.data:
            if not actor_is_platform_admin:
                return Response(
                    {"detail": "Only platform admin can change company assignment."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            raw_company_id = str(request.data.get("company_id") or "").strip()
            if not raw_company_id.isdigit():
                return Response({"detail": "Invalid company id."}, status=status.HTTP_400_BAD_REQUEST)
            target_company = Company.objects.filter(pk=int(raw_company_id), active=True).first()
            if not target_company:
                return Response({"detail": "Company not found or inactive."}, status=status.HTTP_400_BAD_REQUEST)
            user.organization = target_company
            if user.manager_id and user.manager and user.manager.organization_id != target_company.id:
                user.manager = None

        if "portal_access" in request.data:
            portal_access = str(request.data.get("portal_access") or "").strip().upper()
            allowed_values = {
                UserModel.PortalAccess.MAIN,
                UserModel.PortalAccess.ORGANIZATION,
                UserModel.PortalAccess.BOTH,
            }
            if portal_access not in allowed_values:
                return Response({"detail": "Invalid portal access value."}, status=status.HTTP_400_BAD_REQUEST)
            user.portal_access = portal_access
        user.save()
        return Response(UserSerializer(user, context={"request": request}).data)

    def delete(self, request, pk: int):
        user = _scoped_admin_target_user(request, pk)
        if not user:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_account = AdminAccount.objects.filter(user=user).first()
        if admin_account and admin_account.level == AdminAccount.Level.PLATFORM:
            return Response({"detail": "Cannot delete platform admin from this endpoint."}, status=status.HTTP_400_BAD_REQUEST)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserPasswordAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def post(self, request, pk: int):
        target = _scoped_admin_target_user(request, pk)
        if not target:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        actor_is_admin = _is_admin(request.user)
        if not actor_is_admin:
            if target.role != UserModel.Role.EMPLOYEE:
                return Response(
                    {"detail": "HR can only set password for employees in their organization."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if AdminAccount.objects.filter(user=target).exists():
                return Response(
                    {"detail": "HR cannot set password for admin users."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        raw_password = request.data.get("password")
        password = str(raw_password or "")
        confirm_password = request.data.get("confirm_password")
        if not password.strip():
            return Response({"detail": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)
        if confirm_password is not None and password != str(confirm_password):
            return Response({"detail": "Password and confirm password do not match."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password, user=target)
        except ValidationError as exc:
            return Response(
                {"detail": " ".join(exc.messages), "errors": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target.set_password(password)
        target.save(update_fields=["password"])

        _audit_event(
            request.user,
            "USER_PASSWORD_SET",
            "User",
            str(target.id),
            {
                "target_username": target.username,
                "target_role": target.role,
            },
        )
        return Response({"detail": "Password updated successfully."})


class AuditEventListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHR]

    def get(self, request):
        queryset = AuditEvent.objects.select_related("actor").order_by("-created_at")
        paginator = PageNumberPagination()
        paginator.page_size = 30
        page = paginator.paginate_queryset(queryset, request)
        serializer = AuditEventSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
