from __future__ import annotations

import json
from collections import deque
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Company, EmployeeRecord, IntegrationEvent, ManagerRelationship, OrgAccessScope
from users.permissions import is_admin as user_is_admin


def resolve_company(user, company_id: int | None = None) -> Company | None:
    if company_id:
        requested = Company.objects.filter(id=company_id, active=True).first()
        if not requested:
            return None
        if user_is_admin(user):
            return requested
        if getattr(user, "organization_id", None) == requested.id:
            return requested
        return None

    if getattr(user, "organization_id", None):
        company = Company.objects.filter(id=user.organization_id, active=True).first()
        if company:
            return company

    employee = EmployeeRecord.objects.filter(user=user).select_related("company").first()
    if employee:
        return employee.company
    return Company.objects.filter(active=True).order_by("id").first()


def can_access_company(user, company: Company) -> bool:
    if not company or not company.active:
        return False
    if user_is_admin(user):
        return True
    if getattr(user, "organization_id", None) == company.id:
        return True
    return EmployeeRecord.objects.filter(user=user, company=company).exists()


def emit_integration_event(event_type: str, company: Company, payload: dict, actor=None):
    IntegrationEvent.objects.create(
        company=company,
        event_type=event_type,
        payload_json=json.dumps(payload, default=str),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )


def get_employee_for_user(user, company: Company | None = None) -> EmployeeRecord | None:
    queryset = EmployeeRecord.objects.select_related("position__org_unit", "position__location", "company").filter(user=user)
    if company:
        queryset = queryset.filter(company=company)
    elif getattr(user, "organization_id", None):
        queryset = queryset.filter(company_id=user.organization_id)
    return queryset.first()


def get_current_manager(employee: EmployeeRecord, on_date: date | None = None) -> EmployeeRecord | None:
    rel = ManagerRelationship.current_for_employee(employee, at_date=on_date)
    return rel.manager_employee if rel else None


def get_direct_reports(manager_employee: EmployeeRecord, on_date: date | None = None):
    point = on_date or timezone.localdate()
    relationships = (
        ManagerRelationship.objects.filter(
            company=manager_employee.company,
            manager_employee=manager_employee,
            effective_from__lte=point,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=point))
        .select_related("employee")
        .order_by("employee_id")
    )
    return [rel.employee for rel in relationships]


def get_indirect_reports(manager_employee: EmployeeRecord, on_date: date | None = None):
    point = on_date or timezone.localdate()
    visited: set[int] = set()
    queue: deque[EmployeeRecord] = deque([manager_employee])
    reports: list[EmployeeRecord] = []
    while queue:
        current = queue.popleft()
        for employee in get_direct_reports(current, point):
            if employee.id in visited:
                continue
            visited.add(employee.id)
            reports.append(employee)
            queue.append(employee)
    return reports


def get_manager_chain(employee: EmployeeRecord, on_date: date | None = None):
    point = on_date or timezone.localdate()
    chain: list[EmployeeRecord] = []
    seen: set[int] = set()
    current = employee
    while True:
        manager = get_current_manager(current, point)
        if not manager or manager.id in seen:
            break
        seen.add(manager.id)
        chain.append(manager)
        current = manager
    return chain


def build_reporting_tree(employee: EmployeeRecord, on_date: date | None = None):
    point = on_date or timezone.localdate()

    def node_for(emp: EmployeeRecord):
        children = get_direct_reports(emp, point)
        return {
            "employee_id": emp.id,
            "user_id": emp.user_id,
            "name": (emp.user.get_full_name() if emp.user_id else "") or f"Employee #{emp.id}",
            "position_id": emp.position_id,
            "position_title": emp.position.title,
            "children": [node_for(child) for child in children],
        }

    chain = get_manager_chain(employee, point)
    return {
        "employee": node_for(employee),
        "manager_chain": [
            {
                "employee_id": manager.id,
                "user_id": manager.user_id,
                "name": (manager.user.get_full_name() if manager.user_id else "") or f"Employee #{manager.id}",
                "position_id": manager.position_id,
                "position_title": manager.position.title,
            }
            for manager in chain
        ],
    }


def has_hr_scope_access(user, company: Company, org_unit_id: int | None = None, location_id: int | None = None) -> bool:
    if user_is_admin(user):
        return True
    if getattr(user, "role", "") != "HR":
        return False
    scopes = OrgAccessScope.objects.filter(company=company, user=user, active=True)
    if not scopes.exists():
        return True
    for scope in scopes:
        unit_match = scope.org_unit_id is None or scope.org_unit_id == org_unit_id
        loc_match = scope.location_id is None or scope.location_id == location_id
        if unit_match and loc_match:
            return True
    return False


def change_manager(
    *,
    company: Company,
    employee: EmployeeRecord,
    manager_employee: EmployeeRecord | None,
    effective_from: date,
    actor=None,
    note: str = "",
):
    old_relations = ManagerRelationship.objects.filter(
        company=company,
        employee=employee,
        effective_to__isnull=True,
        effective_from__lte=effective_from,
    )
    for rel in old_relations:
        end_date = effective_from - timedelta(days=1)
        if end_date >= rel.effective_from:
            rel.effective_to = end_date
            rel.save(update_fields=["effective_to"])

    created = None
    if manager_employee:
        created = ManagerRelationship.objects.create(
            company=company,
            employee=employee,
            manager_employee=manager_employee,
            effective_from=effective_from,
            changed_by=actor if getattr(actor, "is_authenticated", False) else None,
            note=note.strip(),
        )

    if employee.user_id:
        employee.user.manager = manager_employee.user if manager_employee and manager_employee.user_id else None
        employee.user.save(update_fields=["manager"])

    emit_integration_event(
        "employee.manager.changed",
        company,
        {
            "employee_id": employee.id,
            "manager_employee_id": manager_employee.id if manager_employee else None,
            "effective_from": effective_from.isoformat(),
        },
        actor=actor,
    )
    return created

