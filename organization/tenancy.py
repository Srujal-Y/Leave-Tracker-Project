from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.db import connection
from rest_framework.exceptions import ParseError

from .models import OrganizationTenant

_SCHEMA_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _clean(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_schema_name(schema_name: str) -> str:
    cleaned = _clean(schema_name)
    if not cleaned:
        raise ParseError("Tenant schema is empty.")
    if not _SCHEMA_RE.fullmatch(cleaned):
        raise ParseError("Invalid tenant schema name.")
    return cleaned


def postgres_schema_tenancy_enabled() -> bool:
    return bool(getattr(settings, "ENABLE_POSTGRES_SCHEMA_TENANCY", False) and connection.vendor == "postgresql")


def resolve_tenant_schema(company, preferred_schema: str = "") -> str:
    schema_name = _clean(preferred_schema)
    if not schema_name:
        tenant = OrganizationTenant.objects.filter(company=company, active=True).only("schema_name").first()
        if tenant and tenant.schema_name:
            schema_name = tenant.schema_name
        else:
            schema_name = getattr(company, "slug", "") or ""
    return validate_schema_name(schema_name)


def tenant_schema_exists(schema_name: str) -> bool:
    schema_name = validate_schema_name(schema_name)
    if connection.vendor != "postgresql":
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s LIMIT 1", [schema_name])
        return bool(cursor.fetchone())


def ensure_tenant_schema(schema_name: str, *, auto_create: bool = False) -> bool:
    schema_name = validate_schema_name(schema_name)
    if connection.vendor != "postgresql":
        return False
    if tenant_schema_exists(schema_name):
        return True
    if not auto_create:
        return False
    with connection.cursor() as cursor:
        # Schema name is validated strictly before interpolation.
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
    return tenant_schema_exists(schema_name)


def activate_tenant_search_path(schema_name: str) -> str:
    schema_name = validate_schema_name(schema_name)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('search_path')")
        previous = (cursor.fetchone() or ["public"])[0] or "public"
        cursor.execute(
            "SELECT set_config('search_path', %s, false)",
            [f'"{schema_name}", public'],
        )
    return previous


def restore_search_path(previous_search_path: str):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('search_path', %s, false)",
            [previous_search_path or "public"],
        )
