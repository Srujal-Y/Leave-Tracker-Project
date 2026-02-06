from __future__ import annotations

import calendar
import csv
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from employees.models import EmployeeProfile

from .forms import HolidayForm, LeaveBoardFilterForm, LeaveReasonPresetForm, LeaveRequestForm, LeaveTypeForm
from .models import Holiday, LeaveReasonPreset, LeaveRequest, LeaveRevision, LeaveType


def _can_admin_leave(user) -> bool:
    profile = EmployeeProfile.objects.filter(user=user).first()
    return bool(user.is_staff or (profile and profile.can_manage_leave_config))


def _snapshot(leave: LeaveRequest) -> dict:
    return {
        "start_date": str(leave.start_date),
        "end_date": str(leave.end_date),
        "portion": leave.portion,
        "requested_units": str(leave.requested_units),
        "reason_text": leave.reason_text,
        "status": leave.status,
        "deleted_at": str(leave.deleted_at) if leave.deleted_at else None,
    }


def _holiday_and_weekend_count(start_date, end_date) -> tuple[int, int]:
    holidays = Holiday.objects.filter(day__gte=start_date, day__lte=end_date, active=True).count()
    weekends = 0
    day = start_date
    while day <= end_date:
        if day.weekday() >= 5:
            weekends += 1
        day += timedelta(days=1)
    return holidays, weekends


@login_required
def apply_leave(request):
    holiday_hint = None
    if request.method == "POST":
        recent_count = LeaveRequest.objects.filter(employee=request.user, created_at__gte=timezone.now() - timedelta(minutes=1)).count()
        if recent_count >= 12:
            messages.error(request, "Rate limit reached. Please wait one minute before creating more leave requests.")
            return redirect("leave:apply_leave")

        form = LeaveRequestForm(request.POST, user=request.user)
        if form.is_valid():
            lr: LeaveRequest = form.save(commit=False)
            lr.employee = request.user
            lr.status = LeaveRequest.Status.PENDING
            lr.save()
            AuditEvent.objects.create(actor=request.user, action="Created leave", entity_type="LeaveRequest", entity_id=str(lr.pk))
            LeaveRevision.objects.create(leave=lr, actor=request.user, snapshot_json=_snapshot(lr))
            if settings.EMAIL_NOTIFY_ON_LEAVE and settings.HR_NOTIFICATION_EMAILS:
                send_mail(
                    "New Leave Created",
                    f"{request.user.get_username()} created leave {lr.start_date} to {lr.end_date}",
                    settings.DEFAULT_FROM_EMAIL,
                    settings.HR_NOTIFICATION_EMAILS,
                    fail_silently=True,
                )
            messages.success(request, "Leave request submitted successfully. Authentication waiting.")
            return redirect(f"{reverse('leave:company_leaves')}?highlight={lr.pk}")
    else:
        form = LeaveRequestForm(user=request.user)

    start_preview = request.GET.get("start")
    end_preview = request.GET.get("end")
    if start_preview and end_preview:
        try:
            start_dt = datetime.strptime(start_preview, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_preview, "%Y-%m-%d").date()
            holidays, weekends = _holiday_and_weekend_count(start_dt, end_dt)
            holiday_hint = {"holidays": holidays, "weekends": weekends}
        except ValueError:
            holiday_hint = None

    return render(request, "leave/apply_leave.html", {"form": form, "holiday_hint": holiday_hint})


@login_required
def company_leaves(request):
    qs = LeaveRequest.objects.select_related("employee", "employee__employee_profile", "leave_type", "reason_preset").filter(deleted_at__isnull=True)

    form = LeaveBoardFilterForm(request.GET or None)
    q = (request.GET.get("q") or "").strip()
    if form.is_valid():
        data = form.cleaned_data
        if data.get("employee"):
            emp = data["employee"]
            qs = qs.filter(Q(employee__first_name__icontains=emp) | Q(employee__last_name__icontains=emp) | Q(employee__email__icontains=emp))
        if data.get("leave_type"):
            qs = qs.filter(leave_type=data["leave_type"])
        if data.get("portion"):
            qs = qs.filter(portion=data["portion"])
        if data.get("status"):
            qs = qs.filter(status=data["status"])
        if data.get("month"):
            qs = qs.filter(start_date__year=data["month"].year, start_date__month=data["month"].month)
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

    qs = qs.annotate(emp_total_units=Sum("employee__leaverequest__requested_units"), emp_leave_count=Count("employee__leaverequest", distinct=True)).order_by("-start_date", "-id")
    paginator = Paginator(qs, 15)
    page = paginator.get_page(request.GET.get("page") or 1)

    for lr in page.object_list:
        lr.profile = EmployeeProfile.objects.filter(user_id=lr.employee_id).first()
        lr.can_edit = (request.user == lr.employee) or _can_admin_leave(request.user)

    return render(
        request,
        "leave/company_leaves.html",
        {
            "leaves": page.object_list,
            "page_obj": page,
            "q": q,
            "filter_form": form,
            "highlight": request.GET.get("highlight", ""),
            "can_admin_leave": _can_admin_leave(request.user),
        },
    )


@login_required
def leave_detail(request, pk: int):
    lr = get_object_or_404(LeaveRequest.objects.select_related("employee", "leave_type", "reason_preset"), pk=pk)
    can_edit = request.user == lr.employee or _can_admin_leave(request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "authenticate" and _can_admin_leave(request.user):
            lr.status = LeaveRequest.Status.AUTHENTICATED
            lr.save(update_fields=["status", "updated_at"])
            AuditEvent.objects.create(actor=request.user, action="Authenticated leave", entity_type="LeaveRequest", entity_id=str(lr.pk))
            messages.success(request, "Leave authenticated.")
        elif action == "cancel" and can_edit:
            LeaveRevision.objects.create(leave=lr, actor=request.user, snapshot_json=_snapshot(lr))
            lr.status = LeaveRequest.Status.CANCELLED
            lr.deleted_at = timezone.now()
            lr.save(update_fields=["status", "deleted_at", "updated_at"])
            AuditEvent.objects.create(actor=request.user, action="Cancelled leave", entity_type="LeaveRequest", entity_id=str(lr.pk))
            messages.success(request, "Leave deleted/cancelled successfully.")
        return redirect("leave:leave_detail", pk=lr.pk)

    profile = EmployeeProfile.objects.filter(user_id=lr.employee_id).first()
    return render(request, "leave/leave_detail.html", {"r": lr, "profile": profile, "can_admin_leave": _can_admin_leave(request.user), "can_edit": can_edit})


@login_required
def edit_leave(request, pk: int):
    lr = get_object_or_404(LeaveRequest, pk=pk, deleted_at__isnull=True)
    if not (request.user == lr.employee or _can_admin_leave(request.user)):
        messages.error(request, "You cannot edit this leave.")
        return redirect("leave:company_leaves")

    form = LeaveRequestForm(request.POST or None, instance=lr, user=lr.employee)
    if request.method == "POST" and form.is_valid():
        LeaveRevision.objects.create(leave=lr, actor=request.user, snapshot_json=_snapshot(lr))
        form.save()
        AuditEvent.objects.create(actor=request.user, action="Edited leave", entity_type="LeaveRequest", entity_id=str(lr.pk))
        messages.success(request, "Leave updated.")
        return redirect("leave:leave_detail", pk=lr.pk)
    return render(request, "leave/apply_leave.html", {"form": form, "editing": True, "leave": lr})


@login_required
def calendar_view(request):
    mode = request.GET.get("mode", "month")
    day_param = request.GET.get("day")
    month_param = request.GET.get("month")

    try:
        current = datetime.strptime(month_param, "%Y-%m").date() if month_param else timezone.now().date().replace(day=1)
    except ValueError:
        current = timezone.now().date().replace(day=1)

    if mode == "week":
        focus_day = datetime.strptime(day_param, "%Y-%m-%d").date() if day_param else timezone.now().date()
        start = focus_day - timedelta(days=focus_day.weekday())
        end = start + timedelta(days=6)
    else:
        start = current
        end = (current.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    leaves = LeaveRequest.overlapping(start, end).select_related("employee")
    by_day: dict[str, list[LeaveRequest]] = {}
    for leave in leaves:
        day = leave.start_date
        while day <= leave.end_date:
            if start <= day <= end:
                by_day.setdefault(day.isoformat(), []).append(leave)
            day += timedelta(days=1)

    selected_day_items = by_day.get(day_param, []) if day_param else []

    month_grid = []
    if mode == "month":
        cal = calendar.Calendar(firstweekday=0)
        for week in cal.monthdatescalendar(current.year, current.month):
            week_cells = []
            for day in week:
                iso = day.isoformat()
                week_cells.append({
                    "day": day,
                    "iso": iso,
                    "in_month": day.month == current.month,
                    "count": len(by_day.get(iso, [])),
                })
            month_grid.append(week_cells)

    return render(
        request,
        "leave/calendar.html",
        {
            "current": current,
            "mode": mode,
            "selected_day": day_param,
            "selected_day_items": selected_day_items,
            "by_day": by_day,
            "month_grid": month_grid,
            "week_cells": [
                {"day": d, "iso": d.isoformat(), "count": len(by_day.get(d.isoformat(), []))}
                for d in ([start + timedelta(days=i) for i in range(7)] if mode == "week" else [])
            ],
        },
    )


@login_required
def export_csv(request):
    start = request.GET.get("start")
    end = request.GET.get("end")
    qs = LeaveRequest.objects.filter(deleted_at__isnull=True).select_related("employee", "leave_type")
    if start:
        qs = qs.filter(start_date__gte=start)
    if end:
        qs = qs.filter(end_date__lte=end)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=company-leaves.csv"
    writer = csv.writer(response)
    writer.writerow(["Employee", "Email", "Leave Type", "From", "To", "Units", "Status", "Reason"])
    for r in qs.order_by("-start_date"):
        writer.writerow([r.employee.get_full_name() or r.employee.username, r.employee.email, r.leave_type.name if r.leave_type else "", r.start_date, r.end_date, r.requested_units, r.get_status_display(), r.reason_text])
    return response


@login_required
def team_conflicts(request):
    date_str = request.GET.get("date")
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else timezone.now().date()
    leaves = LeaveRequest.overlapping(date_obj, date_obj).exclude(status=LeaveRequest.Status.CANCELLED)
    return render(request, "leave/team_conflicts.html", {"date_obj": date_obj, "leaves": leaves, "warning": leaves.count() >= 3})


@login_required
def my_ical(request):
    leaves = LeaveRequest.objects.filter(employee=request.user, deleted_at__isnull=True)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Leave Tracker//EN"]
    for leave in leaves:
        lines += [
            "BEGIN:VEVENT",
            f"UID:leave-{leave.pk}@leavetracker",
            f"DTSTAMP:{timezone.now().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;VALUE=DATE:{leave.start_date.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(leave.end_date + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{leave.leave_label}",
            f"DESCRIPTION:{leave.reason_text}",
            "END:VEVENT",
        ]

    for holiday in Holiday.objects.filter(active=True):
        lines += [
            "BEGIN:VEVENT",
            f"UID:holiday-{holiday.pk}@leavetracker",
            f"DTSTAMP:{timezone.now().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;VALUE=DATE:{holiday.day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(holiday.day + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:Holiday - {holiday.title}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    response = HttpResponse("\r\n".join(lines), content_type="text/calendar")
    response["Content-Disposition"] = "attachment; filename=my-leave.ics"
    return response


@login_required
def audit_trail(request):
    if not _can_admin_leave(request.user):
        messages.error(request, "Admins/HR only")
        return redirect("portal:me_dashboard")
    events = AuditEvent.objects.select_related("actor").order_by("-created_at")[:300]
    return render(request, "leave/audit_trail.html", {"events": events})


@login_required
def leave_settings(request):
    if not _can_admin_leave(request.user):
        messages.error(request, "Only HR/Admin can manage leave types and reason presets.")
        return redirect("portal:me_dashboard")

    type_form = LeaveTypeForm(request.POST or None, prefix="type")
    reason_form = LeaveReasonPresetForm(request.POST or None, prefix="reason")
    holiday_form = HolidayForm(request.POST or None, prefix="holiday")

    if request.method == "POST":
        if "create_type" in request.POST and type_form.is_valid():
            type_form.save()
            messages.success(request, "Leave type saved.")
            return redirect("leave:leave_settings")
        if "create_reason" in request.POST and reason_form.is_valid():
            reason_form.save()
            messages.success(request, "Reason preset saved.")
            return redirect("leave:leave_settings")

        if "toggle_type" in request.POST:
            leave_type = get_object_or_404(LeaveType, pk=request.POST.get("toggle_type"))
            leave_type.active = not leave_type.active
            leave_type.save(update_fields=["active"])
            messages.success(request, f"Updated leave type: {leave_type.name}")
            return redirect("leave:leave_settings")
        if "delete_type" in request.POST:
            leave_type = get_object_or_404(LeaveType, pk=request.POST.get("delete_type"))
            leave_type.delete()
            messages.success(request, "Leave type deleted.")
            return redirect("leave:leave_settings")
        if "toggle_reason" in request.POST:
            reason = get_object_or_404(LeaveReasonPreset, pk=request.POST.get("toggle_reason"))
            reason.active = not reason.active
            reason.save(update_fields=["active"])
            messages.success(request, f"Updated reason preset: {reason.label}")
            return redirect("leave:leave_settings")
        if "delete_reason" in request.POST:
            reason = get_object_or_404(LeaveReasonPreset, pk=request.POST.get("delete_reason"))
            reason.delete()
            messages.success(request, "Reason preset deleted.")
            return redirect("leave:leave_settings")
        if "create_holiday" in request.POST and holiday_form.is_valid():
            holiday_form.save()
            messages.success(request, "Holiday saved.")
            return redirect("leave:leave_settings")
        if "toggle_holiday" in request.POST:
            holiday = get_object_or_404(Holiday, pk=request.POST.get("toggle_holiday"))
            holiday.active = not holiday.active
            holiday.save(update_fields=["active"])
            messages.success(request, f"Updated holiday: {holiday.title}")
            return redirect("leave:leave_settings")
        if "delete_holiday" in request.POST:
            holiday = get_object_or_404(Holiday, pk=request.POST.get("delete_holiday"))
            holiday.delete()
            messages.success(request, "Holiday deleted.")
            return redirect("leave:leave_settings")

    return render(
        request,
        "leave/settings.html",
        {
            "type_form": type_form,
            "reason_form": reason_form,
            "holiday_form": holiday_form,
            "leave_types": LeaveType.objects.order_by("name"),
            "reasons": LeaveReasonPreset.objects.order_by("label"),
            "holidays": Holiday.objects.order_by("day"),
        },
    )
