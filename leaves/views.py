from __future__ import annotations

import csv
import json
from calendar import monthcalendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from auditlog.models import AuditEvent
from organization.models import Company
from organization.services import resolve_company
from users.permissions import admin_only_required, admin_or_hr_required, is_admin as user_is_admin

from .forms import HolidayForm, LeaveReasonPresetForm, LeaveRequestForm, LeaveTypeForm
from .models import Holiday, LeaveAttachment, LeaveBalance, LeaveReasonPreset, LeaveRequest, LeaveType

User = get_user_model()


def _current_company(request):
    company = resolve_company(request.user)
    if company:
        return company
    company, _ = Company.objects.get_or_create(
        slug="default",
        defaults={"name": "Default Company", "active": True},
    )
    if getattr(request.user, "is_authenticated", False) and not getattr(request.user, "organization_id", None):
        request.user.organization = company
        request.user.save(update_fields=["organization"])
    return company


def _audit(actor, action: str, leave_request: LeaveRequest, extra: dict | None = None):
    payload = {
        "status": leave_request.status,
        "start_date": str(leave_request.start_date),
        "end_date": str(leave_request.end_date),
        "units": str(leave_request.requested_units),
    }
    if extra:
        payload.update(extra)
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        entity_type="LeaveRequest",
        entity_id=str(leave_request.pk),
        meta_json=json.dumps(payload),
    )


def _dispatch_email(subject: str, body: str, recipients: list[str]):
    recipients = [r for r in recipients if r]
    if not recipients:
        return
    if getattr(settings, "USE_CELERY", False):
        try:
            from .tasks import send_notification_email

            send_notification_email.delay(subject, body, recipients)
            return
        except Exception:
            pass
    send_mail(
        subject=subject,
        message=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=recipients,
        fail_silently=getattr(settings, "EMAIL_FAIL_SILENTLY", True),
    )


def _dedupe_emails(emails: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for email in emails:
        normalized = (email or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _submission_recipients(leave_request: LeaveRequest) -> list[str]:
    manager_email = leave_request.employee.manager.email if leave_request.employee.manager and leave_request.employee.manager.email else ""
    manager_fallbacks = list(getattr(settings, "MANAGER_EMAILS", []))
    hr_mailbox = getattr(settings, "HR_MAILBOX", "")
    team_list = list(getattr(settings, "TEAM_DISTRIBUTION_EMAILS", []))
    target = getattr(settings, "LEAVE_NOTIFICATION_TARGET", "MANAGER")

    recipients: list[str] = []
    if target == "MANAGER":
        recipients.extend([manager_email] + manager_fallbacks)
    elif target == "HR":
        recipients.extend([hr_mailbox] + manager_fallbacks)
    elif target == "TEAM":
        recipients.extend(team_list)
    elif target in {"BOTH", "ALL"}:
        recipients.extend([manager_email, hr_mailbox] + manager_fallbacks + team_list)
    else:
        recipients.extend([manager_email] + manager_fallbacks)
    return _dedupe_emails(recipients)


def _notify_leave_submission(leave_request: LeaveRequest):
    if not getattr(settings, "LEAVE_EMAIL_NOTIFICATIONS_ENABLED", True):
        return

    employee_name = leave_request.employee.get_full_name() or leave_request.employee.username
    _dispatch_email(
        subject=f"Pending leave request: {employee_name}",
        body=(
            f"{employee_name} submitted a leave request.\n\n"
            f"Type: {leave_request.leave_type.name}\n"
            f"From: {leave_request.start_date}\n"
            f"To: {leave_request.end_date}\n"
            f"Working days: {leave_request.requested_units}\n"
            f"Reason: {leave_request.display_reason or '-'}\n"
            f"Status: Pending Approval"
        ),
        recipients=_submission_recipients(leave_request),
    )


def _notify_employee_decision(leave_request: LeaveRequest):
    if not getattr(settings, "LEAVE_EMAIL_NOTIFICATIONS_ENABLED", True):
        return

    if not leave_request.employee.email:
        return

    _dispatch_email(
        subject=f"Leave request {leave_request.get_status_display()}",
        body=(
            f"Your leave request {leave_request.start_date} to {leave_request.end_date} "
            f"is {leave_request.get_status_display()}.\n\n"
            f"Note: {leave_request.manager_note or '-'}"
        ),
        recipients=[leave_request.employee.email],
    )


def _ensure_balance(user, leave_type: LeaveType, year: int, organization=None) -> LeaveBalance:
    target_org = organization or leave_type.organization or getattr(user, "organization", None)
    balance, _ = LeaveBalance.objects.get_or_create(
        organization=target_org,
        user=user,
        leave_type=leave_type,
        year=year,
        defaults={"allocated_days": Decimal(str(leave_type.max_days or 0))},
    )
    return balance


def _validate_balance(leave_request: LeaveRequest) -> list[str]:
    errors: list[str] = []
    for year, units in leave_request.units_by_year().items():
        balance = _ensure_balance(
            leave_request.employee,
            leave_request.leave_type,
            year,
            organization=leave_request.organization,
        )
        if not balance.can_consume(units):
            errors.append(
                f"Insufficient balance for {leave_request.leave_type.name} ({year}): "
                f"requested {units}, remaining {balance.remaining_days}."
            )
    return errors


def _team_conflicts(leave_request: LeaveRequest) -> list[date]:
    threshold = int(getattr(settings, "LEAVE_TEAM_OFF_THRESHOLD", 3) or 3)
    manager = leave_request.employee.manager
    if not manager:
        return []
    team_ids = list(User.objects.filter(manager=manager).values_list("id", flat=True))
    conflicts: list[date] = []
    for day in leave_request.business_dates(leave_request.start_date, leave_request.end_date):
        off_count = (
            LeaveRequest.objects.filter(
                organization=leave_request.organization,
                employee_id__in=team_ids,
                status__in=[LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED],
                start_date__lte=day,
                end_date__gte=day,
                is_deleted=False,
            )
            .exclude(pk=leave_request.pk)
            .count()
        )
        if off_count >= threshold:
            conflicts.append(day)
    return conflicts


def _leave_preview(
    start_date: date | None,
    end_date: date | None,
    portion: str | None,
    organization_id: int | None = None,
) -> dict | None:
    if not start_date or not end_date:
        return None
    if end_date < start_date:
        return None
    portion_value = portion or LeaveRequest.Portion.FULL
    calendar_days = (end_date - start_date).days + 1
    business_days = len(LeaveRequest.business_dates(start_date, end_date, organization_id=organization_id))
    non_working_days = max(calendar_days - business_days, 0)
    if business_days <= 0:
        requested_units = Decimal("0.00")
    elif business_days == 1:
        requested_units = LeaveRequest._portion_units(portion_value)
    else:
        requested_units = Decimal(business_days - 1) + LeaveRequest._portion_units(portion_value)
    return {
        "calendar_days": calendar_days,
        "business_days": business_days,
        "non_working_days": non_working_days,
        "requested_units": requested_units,
    }


def _extract_preview_from_payload(payload, organization_id: int | None = None) -> dict | None:
    start = payload.get("start_date")
    end = payload.get("end_date")
    portion = payload.get("portion") or LeaveRequest.Portion.FULL
    if not start or not end:
        return None
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return None
    return _leave_preview(start_date, end_date, portion, organization_id=organization_id)


def _base_company_queryset(request):
    company = _current_company(request)
    q = (request.GET.get("q") or "").strip()
    employee_id = (request.GET.get("employee") or "").strip()
    leave_type_id = (request.GET.get("leave_type") or "").strip()
    month = (request.GET.get("month") or "").strip()
    portion = (request.GET.get("portion") or "").strip()
    status = (request.GET.get("status") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    qs = LeaveRequest.objects.select_related("employee", "leave_type", "approver").filter(
        is_deleted=False,
        organization=company,
    )

    if q:
        qs = qs.filter(
            Q(employee__first_name__icontains=q)
            | Q(employee__last_name__icontains=q)
            | Q(employee__username__icontains=q)
            | Q(employee__email__icontains=q)
            | Q(reason_text__icontains=q)
            | Q(leave_label__icontains=q)
        )

    if employee_id.isdigit():
        qs = qs.filter(employee_id=int(employee_id))
    if leave_type_id.isdigit():
        qs = qs.filter(leave_type_id=int(leave_type_id))
    if portion in {LeaveRequest.Portion.FULL, LeaveRequest.Portion.HALF, LeaveRequest.Portion.QUARTER}:
        qs = qs.filter(portion=portion)
    if status in {
        LeaveRequest.Status.PENDING,
        LeaveRequest.Status.APPROVED,
        LeaveRequest.Status.REJECTED,
        LeaveRequest.Status.CANCELLED,
    }:
        qs = qs.filter(status=status)

    if month:
        try:
            month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
            qs = qs.filter(start_date__lte=month_end, end_date__gte=month_start)
        except ValueError:
            pass

    if date_from:
        qs = qs.filter(end_date__gte=date_from)
    if date_to:
        qs = qs.filter(start_date__lte=date_to)

    return qs.order_by("-start_date", "-id"), {
        "q": q,
        "employee": employee_id,
        "leave_type": leave_type_id,
        "month": month,
        "portion": portion,
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
    }


@login_required
def apply_leave(request):
    company = _current_company(request)
    preview = _extract_preview_from_payload(
        request.POST if request.method == "POST" else request.GET,
        organization_id=company.id if company else None,
    )
    if request.method == "POST":
        form = LeaveRequestForm(request.POST, request.FILES, user=request.user, company=company)
        if form.is_valid():
            recent_cutoff = timezone.now() - timedelta(minutes=1)
            if LeaveRequest.objects.filter(
                employee=request.user,
                organization=company,
                created_at__gte=recent_cutoff,
            ).count() >= settings.LEAVE_RATE_LIMIT_PER_MINUTE:
                form.add_error(None, "Rate limit exceeded. Please wait a minute before creating another request.")
            else:
                leave_request: LeaveRequest = form.save(commit=False)
                leave_request.organization = company
                leave_request.employee = request.user
                leave_request.status = LeaveRequest.Status.PENDING
                leave_request.requested_units = leave_request.compute_requested_units()

                balance_errors = _validate_balance(leave_request)
                if balance_errors:
                    form.add_error(None, " ".join(balance_errors))
                else:
                    leave_request.save()
                    for document in form.cleaned_data.get("documents", []):
                        LeaveAttachment.objects.create(
                            leave_request=leave_request,
                            file=document,
                            uploaded_by=request.user,
                        )
                    _audit(request.user, "LEAVE_CREATED", leave_request)

                    conflicts = _team_conflicts(leave_request)
                    if conflicts:
                        day_text = ", ".join(str(d) for d in conflicts[:3])
                        messages.warning(request, f"Team conflict warning on: {day_text}")

                    _notify_leave_submission(leave_request)
                    messages.success(request, "Leave request submitted and marked as Pending approval.")
                    return redirect(f"{reverse('leaves:company_board')}?highlight={leave_request.pk}")
    else:
        form = LeaveRequestForm(user=request.user, company=company)
    return render(
        request,
        "leaves/apply_leave.html",
        {
            "form": form,
            "editing": False,
            "leave_preview": preview,
        },
    )


@login_required
def edit_leave(request, pk: int):
    company = _current_company(request)
    leave_request = get_object_or_404(
        LeaveRequest,
        pk=pk,
        employee=request.user,
        organization=company,
        is_deleted=False,
    )
    if leave_request.status != LeaveRequest.Status.PENDING:
        messages.error(request, "Only pending requests can be edited.")
        return redirect("portal:dashboard")

    preview = _extract_preview_from_payload(
        request.POST if request.method == "POST" else request.GET,
        organization_id=company.id if company else None,
    )

    if request.method == "POST":
        form = LeaveRequestForm(
            request.POST,
            request.FILES,
            instance=leave_request,
            user=request.user,
            company=company,
        )
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.organization = company
            leave_request.status = LeaveRequest.Status.PENDING
            leave_request.requested_units = leave_request.compute_requested_units()
            balance_errors = _validate_balance(leave_request)
            if balance_errors:
                form.add_error(None, " ".join(balance_errors))
            else:
                leave_request.save()
                for document in form.cleaned_data.get("documents", []):
                    LeaveAttachment.objects.create(
                        leave_request=leave_request,
                        file=document,
                        uploaded_by=request.user,
                    )
                _audit(request.user, "LEAVE_EDITED", leave_request)
                messages.success(request, "Leave request updated.")
                return redirect("portal:dashboard")
    else:
        form = LeaveRequestForm(instance=leave_request, user=request.user, company=company)
        preview = _leave_preview(
            leave_request.start_date,
            leave_request.end_date,
            leave_request.portion,
            organization_id=company.id if company else None,
        )

    return render(
        request,
        "leaves/apply_leave.html",
        {
            "form": form,
            "editing": True,
            "editing_request": leave_request,
            "attachments": leave_request.attachments.all(),
            "leave_preview": preview,
        },
    )


@login_required
def cancel_leave(request, pk: int):
    company = _current_company(request)
    leave_request = get_object_or_404(
        LeaveRequest,
        pk=pk,
        employee=request.user,
        organization=company,
        is_deleted=False,
    )
    if request.method == "POST":
        if leave_request.status == LeaveRequest.Status.APPROVED:
            messages.error(request, "Approved leave cannot be cancelled.")
        elif leave_request.status != LeaveRequest.Status.PENDING:
            messages.error(request, "Only pending leave requests can be cancelled.")
        else:
            leave_request.status = LeaveRequest.Status.CANCELLED
            leave_request.cancelled_at = timezone.now()
            leave_request.save(update_fields=["status", "cancelled_at", "updated_at"])
            _audit(request.user, "LEAVE_CANCELLED", leave_request)
            messages.success(request, "Leave request cancelled.")
    return redirect("portal:dashboard")


@login_required
def company_board(request):
    company = _current_company(request)
    queryset, filters = _base_company_queryset(request)
    paginator = Paginator(queryset, 12)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    highlight = (request.GET.get("highlight") or "").strip()

    return render(
        request,
        "leaves/company_board.html",
        {
            "leaves": list(page_obj.object_list),
            "page_obj": page_obj,
            "filters": filters,
            "employees": User.objects.filter(
                organization=company,
            ).order_by("first_name", "last_name", "username"),
            "leave_types": LeaveType.objects.filter(active=True, organization=company).order_by("name"),
            "highlight_id": highlight,
        },
    )


@login_required
def leave_detail(request, pk: int):
    company = _current_company(request)
    leave_request = get_object_or_404(
        LeaveRequest.objects.select_related("employee", "leave_type", "approver"),
        pk=pk,
        organization=company,
        is_deleted=False,
    )
    return render(
        request,
        "leaves/leave_detail.html",
        {
            "leave_request": leave_request,
            "attachments": leave_request.attachments.all(),
        },
    )


@admin_or_hr_required
def approval_queue(request):
    company = _current_company(request)
    status_filter = (request.GET.get("status") or LeaveRequest.Status.PENDING).strip()
    qs = LeaveRequest.objects.select_related("employee", "leave_type").filter(
        is_deleted=False,
        organization=company,
    )
    if status_filter in {
        LeaveRequest.Status.PENDING,
        LeaveRequest.Status.APPROVED,
        LeaveRequest.Status.REJECTED,
        LeaveRequest.Status.CANCELLED,
    }:
        qs = qs.filter(status=status_filter)
    qs = qs.order_by("-created_at")
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    return render(
        request,
        "leaves/approval_queue.html",
        {"requests": page_obj.object_list, "page_obj": page_obj, "status_filter": status_filter},
    )


@admin_or_hr_required
def review_leave(request, pk: int):
    company = _current_company(request)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, organization=company, is_deleted=False)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        note = (request.POST.get("manager_note") or "").strip()
        leave_request.manager_note = note
        leave_request.approver = request.user

        if action == "approve":
            leave_request.status = LeaveRequest.Status.APPROVED
            leave_request.approved_at = timezone.now()
            leave_request.rejected_at = None
            leave_request.save()
            _audit(request.user, "LEAVE_APPROVED", leave_request)
            _notify_employee_decision(leave_request)
            messages.success(request, "Request approved.")
        elif action == "reject":
            leave_request.status = LeaveRequest.Status.REJECTED
            leave_request.rejected_at = timezone.now()
            leave_request.approved_at = None
            leave_request.save()
            _audit(request.user, "LEAVE_REJECTED", leave_request)
            _notify_employee_decision(leave_request)
            messages.success(request, "Request rejected.")
        return redirect("leaves:approval_queue")

    return render(request, "leaves/review_leave.html", {"leave_request": leave_request})


@admin_or_hr_required
def manage_policies(request):
    company = _current_company(request)
    leave_types = LeaveType.objects.filter(organization=company).order_by("name")
    reason_presets = LeaveReasonPreset.objects.filter(organization=company).order_by("label")
    holidays = Holiday.objects.filter(organization=company).order_by("date")
    return render(
        request,
        "leaves/manage_policies.html",
        {
            "leave_types": leave_types,
            "reason_presets": reason_presets,
            "holidays": holidays,
            "is_admin_user": user_is_admin(request.user),
        },
    )


@admin_or_hr_required
def leave_type_create(request):
    company = _current_company(request)
    form = LeaveTypeForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        leave_type = form.save()
        messages.success(request, f"Leave type '{leave_type.name}' created.")
        return redirect("leaves:manage_policies")
    return render(
        request,
        "leaves/policy_form.html",
        {"form": form, "title": "Create Leave Type", "back_url": "leaves:manage_policies"},
    )


@admin_or_hr_required
def leave_type_edit(request, pk: int):
    company = _current_company(request)
    leave_type = get_object_or_404(LeaveType, pk=pk, organization=company)
    form = LeaveTypeForm(request.POST or None, instance=leave_type, company=company)
    if request.method == "POST" and form.is_valid():
        leave_type = form.save()
        messages.success(request, f"Leave type '{leave_type.name}' updated.")
        return redirect("leaves:manage_policies")
    return render(
        request,
        "leaves/policy_form.html",
        {"form": form, "title": f"Edit Leave Type: {leave_type.name}", "back_url": "leaves:manage_policies"},
    )


@admin_or_hr_required
def reason_preset_create(request):
    company = _current_company(request)
    form = LeaveReasonPresetForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        reason = form.save()
        messages.success(request, f"Reason preset '{reason.label}' created.")
        return redirect("leaves:manage_policies")
    return render(
        request,
        "leaves/policy_form.html",
        {"form": form, "title": "Create Reason Preset", "back_url": "leaves:manage_policies"},
    )


@admin_or_hr_required
def reason_preset_edit(request, pk: int):
    company = _current_company(request)
    reason = get_object_or_404(LeaveReasonPreset, pk=pk, organization=company)
    form = LeaveReasonPresetForm(request.POST or None, instance=reason, company=company)
    if request.method == "POST" and form.is_valid():
        reason = form.save()
        messages.success(request, f"Reason preset '{reason.label}' updated.")
        return redirect("leaves:manage_policies")
    return render(
        request,
        "leaves/policy_form.html",
        {"form": form, "title": f"Edit Reason Preset: {reason.label}", "back_url": "leaves:manage_policies"},
    )


@admin_only_required
def holiday_create(request):
    company = _current_company(request)
    form = HolidayForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        holiday = form.save()
        messages.success(request, f"Holiday '{holiday.name}' added for {holiday.date}.")
        return redirect("leaves:manage_policies")
    return render(
        request,
        "leaves/policy_form.html",
        {"form": form, "title": "Add Public Holiday", "back_url": "leaves:manage_policies"},
    )


@admin_only_required
def holiday_edit(request, pk: int):
    company = _current_company(request)
    holiday = get_object_or_404(Holiday, pk=pk, organization=company)
    form = HolidayForm(request.POST or None, instance=holiday, company=company)
    if request.method == "POST" and form.is_valid():
        holiday = form.save()
        messages.success(request, f"Holiday '{holiday.name}' updated.")
        return redirect("leaves:manage_policies")
    return render(
        request,
        "leaves/policy_form.html",
        {"form": form, "title": f"Edit Holiday: {holiday.name}", "back_url": "leaves:manage_policies"},
    )


@admin_only_required
def holiday_delete(request, pk: int):
    company = _current_company(request)
    holiday = get_object_or_404(Holiday, pk=pk, organization=company)
    if request.method == "POST":
        holiday_name = holiday.name
        holiday.delete()
        messages.success(request, f"Holiday '{holiday_name}' deleted.")
    return redirect("leaves:manage_policies")


@admin_or_hr_required
def export_csv(request):
    qs, _ = _base_company_queryset(request)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="leave-board-{timezone.localdate().isoformat()}.csv"'
    writer = csv.writer(response)
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
    for leave_request in qs:
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
    return response


@login_required
def team_calendar(request):
    company = _current_company(request)
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
            week_anchor = today
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

    approved_leaves = list(
        LeaveRequest.objects.select_related("employee", "leave_type")
        .filter(
            status=LeaveRequest.Status.APPROVED,
            organization=company,
            is_deleted=False,
            start_date__lte=last_day,
            end_date__gte=first_day,
        )
        .order_by("start_date")
    )

    leaves_by_day: dict[int, list[LeaveRequest]] = {}
    for day in range(1, last_day.day + 1):
        current = date(year, month, day)
        entries = [lr for lr in approved_leaves if lr.start_date <= current <= lr.end_date]
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
    selected_entries: list[LeaveRequest] = []
    if day_value:
        try:
            selected_date = datetime.strptime(day_value, "%Y-%m-%d").date()
            selected_entries = [lr for lr in approved_leaves if lr.start_date <= selected_date <= lr.end_date]
        except ValueError:
            selected_date = None

    week_entries = [
        {
            "day": d,
            "entries": [lr for lr in approved_leaves if lr.start_date <= d <= lr.end_date],
        }
        for d in week_days
    ]

    prev_week = (week_start - timedelta(days=7)).strftime("%Y-%m-%d")
    next_week = (week_start + timedelta(days=7)).strftime("%Y-%m-%d")

    return render(
        request,
        "leaves/team_calendar.html",
        {
            "mode": mode,
            "anchor": anchor,
            "prev_month": (first_day - timedelta(days=1)).strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
            "calendar_rows": calendar_rows,
            "selected_date": selected_date,
            "selected_entries": selected_entries,
            "week_anchor": week_anchor,
            "week_entries": week_entries,
            "prev_week": prev_week,
            "next_week": next_week,
            "week_start": week_start,
            "week_end": week_end,
        },
    )


@admin_or_hr_required
def audit_trail(request):
    events = AuditEvent.objects.select_related("actor").order_by("-created_at")
    paginator = Paginator(events, 30)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    return render(request, "leaves/audit_trail.html", {"page_obj": page_obj})


@login_required
def my_ical(request):
    company = _current_company(request)
    requests = LeaveRequest.objects.filter(
        employee=request.user,
        organization=company,
        status=LeaveRequest.Status.APPROVED,
        is_deleted=False,
    ).order_by("start_date")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Red Samurai Leave Tracker//EN",
    ]
    for item in requests:
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
