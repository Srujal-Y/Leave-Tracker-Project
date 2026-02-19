from __future__ import annotations

import logging
from datetime import timedelta
from secrets import randbelow

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

from organization.models import Company
from organization.services import resolve_company

from .forms import (
    AdminCreateUserForm,
    EmailLoginForm,
    PasswordResetRequestForm,
    PasswordResetVerifyForm,
    ProfileForm,
)
from .models import PasswordResetOTP
from .models import AdminAccount
from .permissions import admin_or_hr_required, is_admin as user_is_admin

User = get_user_model()
logger = logging.getLogger(__name__)


def _current_company(request):
    company = None
    selected_company_id = request.session.get("selected_company_id")
    if selected_company_id:
        try:
            company = resolve_company(request.user, company_id=int(selected_company_id))
        except (TypeError, ValueError):
            company = None

    company = company or resolve_company(request.user)
    if company:
        request.session["selected_company_id"] = company.id
        return company
    company, _ = Company.objects.get_or_create(
        slug="default",
        defaults={"name": "Default Company", "active": True},
    )
    if (
        getattr(request.user, "is_authenticated", False)
        and not user_is_admin(request.user)
        and not getattr(request.user, "organization_id", None)
    ):
        request.user.organization = company
        request.user.save(update_fields=["organization"])
    request.session["selected_company_id"] = company.id
    return company


def _requested_company(request):
    raw_company_id = (request.POST.get("company_id") or request.GET.get("company_id") or "").strip()
    raw_company_slug = (request.POST.get("company_slug") or request.GET.get("company_slug") or "").strip().lower()
    raw_company_name = (request.POST.get("company_name") or request.GET.get("company_name") or "").strip()

    company = None
    if raw_company_id:
        if raw_company_id.isdigit():
            company = Company.objects.filter(id=int(raw_company_id), active=True).first()
        else:
            return None, "Invalid organization id."

    if raw_company_slug:
        slug_company = Company.objects.filter(slug=raw_company_slug, active=True).first()
        if not slug_company:
            return None, "Organization not found."
        if company and company.id != slug_company.id:
            return None, "Organization id and slug do not match."
        company = slug_company

    if raw_company_name:
        matches = Company.objects.filter(name__iexact=raw_company_name, active=True).order_by("id")
        if not matches.exists():
            return None, "Organization name not found."
        if matches.count() > 1:
            return None, "Multiple organizations share this name. Use a unique company name."
        name_company = matches.first()
        if company and company.id != name_company.id:
            return None, "Organization name does not match selected organization."
        company = name_company

    return company, None


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or "/dashboard/"
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return "/dashboard/"


def _organization_server_employee_queryset(company):
    return (
        User.objects.filter(
            organization=company,
            role=User.Role.EMPLOYEE,
            created_in_organization=company,
            created_by__role=User.Role.HR,
            created_by__organization=company,
        )
        .select_related("created_by", "created_in_organization")
        .order_by("username")
    )


def login_view(request):
    login_company, company_error = _requested_company(request)
    next_url = _safe_next_url(request)

    if request.user.is_authenticated:
        if not login_company:
            return redirect("portal:dashboard")
        if user_is_admin(request.user):
            request.session["selected_company_id"] = login_company.id
            return redirect(next_url)
        if (
            request.user.role == User.Role.HR
            and request.user.organization_id
            and request.user.organization_id == login_company.id
            and getattr(request.user, "portal_access", User.PortalAccess.BOTH)
            in {User.PortalAccess.ORGANIZATION, User.PortalAccess.BOTH}
        ):
            request.session["selected_company_id"] = login_company.id
            return redirect(next_url)
        logout(request)

    form = EmailLoginForm(request, login_company, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        if login_company:
            request.session["selected_company_id"] = login_company.id
        elif getattr(user, "organization_id", None):
            request.session["selected_company_id"] = user.organization_id
        return redirect(next_url)
    if request.method == "POST" and company_error:
        form.add_error(None, company_error)
    return render(
        request,
        "registration/login.html",
        {
            "form": form,
            "login_company": login_company,
            "next": next_url,
        },
    )


@login_required
def logout_view(request):
    logout(request)
    return redirect("users:login")


def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = (form.cleaned_data["email"] or "").strip().lower()
        user = User.objects.filter(email__iexact=email).first() or User.objects.filter(username__iexact=email).first()
        if not user:
            form.add_error("email", "No account found with this email.")
        else:
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
            reset_link = request.build_absolute_uri(
                redirect("users:password_reset_verify", token=otp.token).url
            )
            try:
                sent_count = send_mail(
                    "Leave Tracker OTP Password Reset",
                    f"OTP: {otp.code}\nExpires in 10 minutes.\nReset link: {reset_link}",
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                if sent_count < 1:
                    raise RuntimeError("SMTP accepted no recipients (send_mail returned 0).")
                messages.success(request, "OTP sent to your email.")
                if settings.DEBUG and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
                    messages.warning(
                        request,
                        f"Dev mode: email backend is Console. OTP is {otp.code}. Check terminal output too.",
                    )
                return redirect("users:password_reset_verify", token=otp.token)
            except Exception:
                logger.exception("Failed sending OTP email to %s", email)
                messages.error(
                    request,
                    "OTP email could not be sent. Configure SMTP settings in your .env and try again.",
                )
    return render(
        request,
        "registration/password_reset_request.html",
        {
            "form": form,
            "using_console_email_backend": settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend",
        },
    )


def password_reset_verify(request, token):
    otp = get_object_or_404(PasswordResetOTP, token=token)
    if otp.used_at:
        messages.error(request, "OTP already used. Request a new one.")
        return redirect("users:password_reset_request")
    if otp.is_expired():
        messages.error(request, "OTP expired. Request a new one.")
        return redirect("users:password_reset_request")

    form = PasswordResetVerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["code"] != otp.code:
            form.add_error("code", "Incorrect OTP.")
        else:
            user = otp.user
            user.set_password(form.cleaned_data["new_password"])
            user.save(update_fields=["password"])
            otp.mark_used()
            messages.success(request, "Password updated. Please login.")
            return redirect("users:login")
    return render(request, "registration/password_reset_verify.html", {"form": form})


@login_required
def edit_profile(request):
    profile = request.user.profile
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("portal:dashboard")
    return render(request, "portal/edit_profile.html", {"form": form})


@admin_or_hr_required
def admin_panel(request):
    company = _current_company(request)
    q = (request.GET.get("q") or "").strip()
    users = _organization_server_employee_queryset(company)
    total_company_employees = User.objects.filter(organization=company, role=User.Role.EMPLOYEE).count()
    if q:
        users = users.filter(
            models.Q(username__icontains=q)
            | models.Q(email__icontains=q)
            | models.Q(first_name__icontains=q)
            | models.Q(last_name__icontains=q)
        )
    visible_count = users.count()
    hidden_count = max(total_company_employees - visible_count, 0)
    return render(
        request,
        "portal/admin_panel.html",
        {
            "users": users[:300],
            "q": q,
            "company": company,
            "visible_count": visible_count,
            "hidden_count": hidden_count,
        },
    )


@admin_or_hr_required
def admin_create_user(request):
    company = _current_company(request)
    form = AdminCreateUserForm(
        request.POST or None,
        organization=company,
        organization_server_mode=True,
    )
    if request.method == "POST" and form.is_valid():
        if request.user.role != User.Role.HR or request.user.organization_id != company.id:
            form.add_error(None, "Only HR of the selected organization can create employees in Organization Server.")
            return render(request, "portal/admin_create_user.html", {"form": form})

        email = form.cleaned_data["email"]
        role = User.Role.EMPLOYEE
        manager = form.cleaned_data["manager"]
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=form.cleaned_data.get("first_name", ""),
            last_name=form.cleaned_data.get("last_name", ""),
            organization=company,
            created_by=request.user,
            created_in_organization=company,
            role=role,
            portal_access=form.cleaned_data.get("portal_access") or User.PortalAccess.BOTH,
            manager=manager if role == User.Role.EMPLOYEE else None,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        messages.success(request, f"Created user {email}. They can set password via OTP reset.")
        return redirect("users:admin_panel")
    return render(request, "portal/admin_create_user.html", {"form": form})


@admin_or_hr_required
def admin_toggle_user(request, user_id: int):
    if request.method != "POST":
        return redirect("users:admin_panel")
    company = _current_company(request)
    user = get_object_or_404(_organization_server_employee_queryset(company), pk=user_id)
    if request.user.role not in {User.Role.HR} and not user_is_admin(request.user):
        messages.error(request, "Only HR/Admin can modify employee access in this organization.")
        return redirect("users:admin_panel")
    if AdminAccount.objects.filter(user=user, level=AdminAccount.Level.PLATFORM).exists():
        messages.error(request, "Cannot modify platform admin from portal.")
        return redirect("users:admin_panel")
    current_access = getattr(user, "portal_access", User.PortalAccess.BOTH)
    next_access = User.PortalAccess.MAIN if current_access == User.PortalAccess.BOTH else User.PortalAccess.BOTH
    user.portal_access = next_access
    user.save(update_fields=["portal_access"])
    messages.success(request, f"Updated {user.username}: portal_access={user.portal_access}")
    return redirect("users:admin_panel")


@admin_or_hr_required
def admin_delete_user(request, user_id: int):
    company = _current_company(request)
    user = get_object_or_404(_organization_server_employee_queryset(company), pk=user_id)
    if request.user.role not in {User.Role.HR} and not user_is_admin(request.user):
        messages.error(request, "Only HR/Admin can delete employee accounts in this organization.")
        return redirect("users:admin_panel")
    if AdminAccount.objects.filter(user=user, level=AdminAccount.Level.PLATFORM).exists():
        messages.error(request, "Cannot delete platform admin from portal.")
        return redirect("users:admin_panel")

    if request.method == "POST":
        username = user.username
        user.delete()
        messages.success(request, f"Deleted user: {username}")
        return redirect("users:admin_panel")
    return render(request, "portal/admin_delete_user.html", {"target_user": user})
