from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from rest_framework.exceptions import APIException, ParseError

from .context import extract_requested_org_context, resolve_company_context
from .tenancy import (
    activate_tenant_search_path,
    ensure_tenant_schema,
    postgres_schema_tenancy_enabled,
    resolve_tenant_schema,
    restore_search_path,
)

logger = logging.getLogger(__name__)


class OrganizationContextMiddleware:
    """
    Resolves and caches organization context early for authenticated API calls.
    This preserves current behavior while allowing optional strict context mode.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _is_exempt_path(self, path: str) -> bool:
        exact_paths = set(getattr(settings, "ORG_CONTEXT_EXEMPT_PATHS", []))
        if path in exact_paths:
            return True
        prefixes = tuple(getattr(settings, "ORG_CONTEXT_EXEMPT_PATH_PREFIXES", []))
        return any(path.startswith(prefix) for prefix in prefixes)

    def _audit_enabled(self) -> bool:
        return bool(getattr(settings, "ORG_CONTEXT_AUDIT_LOG", False))

    def _log_event(self, event: str, payload: dict, level: int = logging.INFO):
        if not self._audit_enabled():
            return
        logger.log(level, "ORG_CONTEXT_%s %s", event, json.dumps(payload, default=str, sort_keys=True))

    def __call__(self, request):
        path = request.path or ""
        is_api = path.startswith("/api/")
        if not is_api or request.method == "OPTIONS" or self._is_exempt_path(path):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return self.get_response(request)

        require_explicit = bool(getattr(settings, "REQUIRE_EXPLICIT_ORG_CONTEXT", False))
        schema_value, company_id_value = extract_requested_org_context(request, allow_request_data=False)
        base_payload = {
            "path": path,
            "method": request.method,
            "user_id": getattr(user, "id", None),
            "require_explicit": require_explicit,
            "header_company_id": company_id_value,
            "header_schema": schema_value,
        }
        try:
            company = resolve_company_context(
                request,
                user,
                allow_request_data=False,
                require_explicit=require_explicit,
                bind_user_organization=True,
            )
        except Exception as exc:  # pragma: no cover - defensive response guard
            status_code = 400
            detail = str(exc)
            if isinstance(exc, APIException):
                status_code = int(getattr(exc, "status_code", 400))
                detail = str(getattr(exc, "detail", detail))
            self._log_event(
                "DENIED",
                {
                    **base_payload,
                    "status_code": status_code,
                    "detail": detail,
                },
                level=logging.WARNING,
            )
            return JsonResponse({"detail": detail}, status=status_code)

        active_schema = ""
        previous_search_path = None
        schema_switched = False
        if postgres_schema_tenancy_enabled():
            try:
                active_schema = resolve_tenant_schema(company, preferred_schema=schema_value)
                auto_create_schema = bool(getattr(settings, "TENANCY_AUTO_CREATE_SCHEMA", False))
                if not ensure_tenant_schema(active_schema, auto_create=auto_create_schema):
                    raise ParseError(
                        "Tenant schema is not provisioned. Set TENANCY_AUTO_CREATE_SCHEMA=1 or provision schema manually."
                    )
                previous_search_path = activate_tenant_search_path(active_schema)
                schema_switched = True
            except Exception as exc:
                status_code = 400
                detail = str(exc)
                if isinstance(exc, APIException):
                    status_code = int(getattr(exc, "status_code", 400))
                    detail = str(getattr(exc, "detail", detail))
                self._log_event(
                    "DENIED",
                    {
                        **base_payload,
                        "status_code": status_code,
                        "detail": detail,
                    },
                    level=logging.WARNING,
                )
                return JsonResponse({"detail": detail}, status=status_code)

        request.organization_context = company
        request.organization_context_id = company.id
        request.organization_context_slug = company.slug
        request.organization_context_schema = active_schema or company.slug
        request.organization_context_schema_switched = schema_switched
        self._log_event(
            "RESOLVED",
            {
                **base_payload,
                "resolved_company_id": company.id,
                "resolved_company_slug": company.slug,
                "resolved_schema": request.organization_context_schema,
                "schema_switched": schema_switched,
            },
            level=logging.INFO,
        )
        logger.debug(
            "Organization context resolved: path=%s user_id=%s company_id=%s company_slug=%s schema=%s switched=%s",
            path,
            getattr(user, "id", None),
            company.id,
            company.slug,
            request.organization_context_schema,
            schema_switched,
        )
        try:
            return self.get_response(request)
        finally:
            if schema_switched and previous_search_path is not None:
                restore_search_path(previous_search_path)
