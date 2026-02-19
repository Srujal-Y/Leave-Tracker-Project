from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import ParseError, PermissionDenied

from users.permissions import is_admin as user_is_admin

from .models import Company, EmployeeRecord, OrganizationTenant
from .services import can_access_company, resolve_company


def get_or_create_default_company() -> Company:
    company = Company.objects.order_by("id").first()
    if company:
        return company
    company, _ = Company.objects.get_or_create(
        slug="default",
        defaults={"name": "Default Company", "active": True},
    )
    return company


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _read_query_param(request, key: str) -> str:
    query = getattr(request, "query_params", None)
    if query is not None and hasattr(query, "get"):
        value = query.get(key)
        if value not in (None, ""):
            return _clean(value)
    get_values = getattr(request, "GET", None)
    if get_values is not None and hasattr(get_values, "get"):
        value = get_values.get(key)
        if value not in (None, ""):
            return _clean(value)
    return ""


def _read_data_param(request, key: str) -> str:
    data = getattr(request, "data", None)
    if data is not None and hasattr(data, "get"):
        value = data.get(key)
        if value not in (None, ""):
            return _clean(value)
    post = getattr(request, "POST", None)
    if post is not None and hasattr(post, "get"):
        value = post.get(key)
        if value not in (None, ""):
            return _clean(value)
    return ""


def _read_header(request, key: str) -> str:
    headers = getattr(request, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        value = headers.get(key)
        if value not in (None, ""):
            return _clean(value)
    meta_key = f"HTTP_{key.upper().replace('-', '_')}"
    meta = getattr(request, "META", None) or {}
    value = meta.get(meta_key)
    if value not in (None, ""):
        return _clean(value)
    return ""


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def extract_requested_org_context(request, *, allow_request_data: bool = True) -> tuple[str, str]:
    schema_value = _first_non_empty(
        _read_query_param(request, "schema"),
        _read_query_param(request, "company_slug"),
        _read_header(request, "X-DTS-SCHEMA"),
        _read_header(request, "X-COMPANY-SLUG"),
        _read_data_param(request, "schema") if allow_request_data else "",
        _read_data_param(request, "company_slug") if allow_request_data else "",
    ).lower()

    company_id_value = _first_non_empty(
        _read_query_param(request, "company"),
        _read_query_param(request, "company_id"),
        _read_header(request, "X-Company-Id"),
        _read_data_param(request, "company") if allow_request_data else "",
        _read_data_param(request, "company_id") if allow_request_data else "",
    )
    return schema_value, company_id_value


def _resolve_schema_company(schema_value: str) -> Company | None:
    if not schema_value:
        return None
    tenant = (
        OrganizationTenant.objects.select_related("company")
        .filter(schema_name=schema_value, active=True, company__active=True)
        .first()
    )
    if tenant:
        return tenant.company
    return Company.objects.filter(slug=schema_value, active=True).first()


def _resolve_id_company(raw_company_id: str) -> Company | None:
    if not raw_company_id:
        return None
    if not raw_company_id.isdigit():
        raise ParseError("Invalid organization id.")
    return Company.objects.filter(id=int(raw_company_id), active=True).first()


def resolve_company_context(
    request,
    user,
    *,
    allow_request_data: bool = True,
    require_explicit: bool = False,
    bind_user_organization: bool = True,
) -> Company:
    schema_value, company_id_value = extract_requested_org_context(
        request,
        allow_request_data=allow_request_data,
    )

    has_explicit_context = bool(schema_value or company_id_value)
    if require_explicit and not has_explicit_context:
        raise ParseError("Organization context is required. Select an organization and retry.")

    schema_company = None
    if schema_value:
        schema_company = _resolve_schema_company(schema_value)
        if not schema_company:
            raise ParseError("Invalid tenant schema. Please select a valid organization.")
        if user and not isinstance(user, AnonymousUser) and not can_access_company(user, schema_company):
            raise PermissionDenied("You do not have access to this organization schema.")

    id_company = None
    if company_id_value:
        id_company = _resolve_id_company(company_id_value)
        if not id_company:
            raise ParseError("Organization not found or inactive.")
        if user and not isinstance(user, AnonymousUser) and not can_access_company(user, id_company):
            raise PermissionDenied("You do not have access to this organization.")

    if schema_company and id_company and schema_company.id != id_company.id:
        raise ParseError("Tenant schema and organization id do not match.")

    company = schema_company or id_company
    if not company:
        company = resolve_company(user, company_id=None) if user and not isinstance(user, AnonymousUser) else None
    company = company or get_or_create_default_company()

    if (
        bind_user_organization
        and user
        and not isinstance(user, AnonymousUser)
        and getattr(user, "is_authenticated", False)
        and not user_is_admin(user)
        and not getattr(user, "organization_id", None)
    ):
        user.organization = company
        user.save(update_fields=["organization"])

    return company


def infer_company_ids_for_user(user) -> list[int]:
    if not user or isinstance(user, AnonymousUser) or not getattr(user, "is_authenticated", False):
        return []
    if user_is_admin(user):
        return list(Company.objects.filter(active=True).values_list("id", flat=True))
    if getattr(user, "organization_id", None):
        return [user.organization_id]
    return list(EmployeeRecord.objects.filter(user=user).values_list("company_id", flat=True))
