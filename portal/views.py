from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from leaves.models import LeaveBalance, LeaveRequest
from organization.models import Company
from organization.services import resolve_company
from users.permissions import is_admin_or_hr


def home(request):
    if request.user.is_authenticated:
        return redirect("portal:dashboard")
    return redirect("users:login")


def health(request):
    return JsonResponse({"status": "ok", "timestamp": timezone.now().isoformat()})


@login_required
def dashboard(request):
    selected_company_id = request.session.get("selected_company_id")
    company = None
    if selected_company_id:
        try:
            company = resolve_company(request.user, company_id=int(selected_company_id))
        except (TypeError, ValueError):
            company = None
    company = company or resolve_company(request.user)
    if not company:
        company, _ = Company.objects.get_or_create(
            slug="default",
            defaults={"name": "Default Company", "active": True},
        )
        if not getattr(request.user, "organization_id", None):
            request.user.organization = company
            request.user.save(update_fields=["organization"])
    request.session["selected_company_id"] = company.id
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

    requests = (
        LeaveRequest.objects.filter(employee=request.user, organization=company, is_deleted=False)
        .select_related("leave_type")
        .order_by("-created_at")[:5]
    )
    return render(
        request,
        "portal/dashboard.html",
        {
            "profile": request.user.profile,
            "current_year": current_year,
            "total_leaves": total_leaves,
            "leaves_taken": leaves_taken,
            "remaining_balance": remaining_balance,
            "recent_requests": requests,
            "is_admin_or_hr": is_admin_or_hr(request.user),
        },
    )
