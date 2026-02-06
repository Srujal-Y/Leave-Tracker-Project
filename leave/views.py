from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from employees.models import EmployeeProfile

from .forms import LeaveRequestForm
from .models import LeaveRequest


@login_required
def apply_leave(request):
    """Create a leave request (no approvals; it becomes visible company-wide).

    The employee can select a leave type + preset reason, but may also type custom.
    """

    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            lr: LeaveRequest = form.save(commit=False)
            lr.employee = request.user
            lr.save()
            messages.success(request, "Leave recorded. It is now visible to the company.")
            return redirect("leave:company_leaves")
    else:
        form = LeaveRequestForm()

    return render(request, "leave/apply_leave.html", {"form": form})


@login_required
def company_leaves(request):
    """All leaves for all employees (company-wide visibility)."""

    q = (request.GET.get("q") or "").strip()
    qs = LeaveRequest.objects.select_related(
        "employee",
        "employee__employee_profile",
        "leave_type",
        "reason_preset",
    ).annotate(
        emp_total_units=Sum("employee__leaverequest__requested_units"),
        emp_leave_count=Count("employee__leaverequest", distinct=True),
    )
    if q:
        qs = qs.filter(
            Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(employee__username__icontains=q)
            | Q(employee__email__icontains=q)
            | Q(leave_label__icontains=q)
            | Q(leave_type__name__icontains=q)
            | Q(reason_text__icontains=q)
            | Q(reason_preset__label__icontains=q)
        )

    leaves = list(qs.order_by("-start_date", "-id")[:200])
    for lr in leaves:
        try:
            lr.profile = lr.employee.employee_profile
        except EmployeeProfile.DoesNotExist:
            lr.profile = None

    return render(
        request,
        "leave/company_leaves.html",
        {
            "leaves": leaves,
            "q": q,
        },
    )


@login_required
def employee_detail(request, user_id: int):
    """Employee profile details (photo + current project/tasks)."""

    profile = get_object_or_404(EmployeeProfile, user_id=user_id)
    leaves = (
        LeaveRequest.objects.filter(employee_id=user_id)
        .select_related("leave_type", "reason_preset")
        .order_by("-start_date", "-id")[:50]
    )

    return render(request, "leave/employee_detail.html", {"profile": profile, "leaves": leaves})


@login_required
def leave_detail(request, pk: int):
    """Detail view for a single leave request."""

    lr = (
        LeaveRequest.objects.select_related("employee", "leave_type", "reason_preset").annotate(
        emp_total_units=Sum("employee__leaverequest__requested_units"),
        emp_leave_count=Count("employee__leaverequest", distinct=True),
    )
        .filter(pk=pk)
        .first()
    )
    if not lr:
        lr = get_object_or_404(LeaveRequest, pk=pk)

    profile = EmployeeProfile.objects.filter(user_id=lr.employee_id).first()
    return render(request, "leave/leave_detail.html", {"r": lr, "profile": profile})
