import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from employees.models import EmployeeProfile
from leave.models import LeaveRequest
from .forms import (
    UsernameLoginForm,
    ProfileForm,
    PasswordResetQuestionForm,
    RegistrationForm,
    AdminEmployeeCreateForm,
)
from .authz import is_manager_email
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

def home(request):
    if request.user.is_authenticated:
        return redirect("portal:me_dashboard")
    return redirect("portal:login")


def register_view(request):
    if request.user.is_authenticated:
        return redirect("portal:me_dashboard")

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            form.add_error("username", "Username already exists.")
        else:
            user = User.objects.create_user(
                username=username,
                password=form.cleaned_data["password"],
            )
            EmployeeProfile.objects.get_or_create(user=user)
            login(request, user)
            return redirect("portal:me_dashboard")

    return render(request, "portal/register.html", {"form": form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect("portal:me_dashboard")

    form = UsernameLoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("portal:me_dashboard")
        messages.error(request, "Invalid email/password.")
    return render(request, "portal/login.html", {"form": form})

@login_required
def logout_view(request):
    logout(request)
    return redirect("portal:login")

@login_required
def me_dashboard(request):
    EmployeeProfile.objects.get_or_create(user=request.user)
    profile = request.user.employee_profile
    # LeaveRequest uses `employee` (FK to AUTH_USER_MODEL), not `user`.
    my_recent = (
        LeaveRequest.objects.filter(employee=request.user)
        .select_related("leave_type")
        .order_by("-created_at")[:10]
    )
    company_recent = (
        LeaveRequest.objects.select_related("employee__employee_profile", "leave_type")
        .order_by("-created_at")[:8]
    )
    is_mgr = is_manager_email(getattr(request.user, "email", ""))
    return render(
        request,
        "portal/me_dashboard.html",
        {
            "profile": profile,
            "my_recent": my_recent,
            "company_recent": company_recent,
            "my_recent_requests": my_recent,
            "company_recent_requests": company_recent,
            "is_manager": is_mgr,
        },
    )

@login_required
def edit_profile(request):
    profile, _ = EmployeeProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("portal:me_dashboard")
    else:
        form = ProfileForm(instance=profile)
    return render(request, "portal/edit_profile.html", {"form": form})


def password_reset_question(request):
    """Reset password via a simple challenge question (no email/OTP).

    NOTE: This is intentionally weak security and should only be used for demos.
    """

    form = PasswordResetQuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = (form.cleaned_data["username"] or "").strip().lower()
        User = get_user_model()

        # In this app we use email as username, but we also fall back to email lookup.
        user = (
            User.objects.filter(username__iexact=username).first()
            or User.objects.filter(email__iexact=username).first()
        )
        if not user:
            form.add_error("username", "No account found for this email.")
        elif not user.is_active:
            form.add_error("username", "This account is disabled. Contact an admin.")
        else:
            user.set_password(form.cleaned_data["new_password"])
            user.save(update_fields=["password"])
            messages.success(request, "Password updated. You can now log in.")
            return redirect("portal:login")

    return render(request, "portal/password_reset_question.html", {"form": form})


@login_required
def manager_alias(request):
    """Legacy route: send users to the company leave board."""
    return redirect("leave:company_leaves")


def staff_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)


@staff_required
def admin_panel(request):
    """Custom Admin Panel (portal UI) for managing employee accounts."""

    User = get_user_model()
    q = (request.GET.get("q") or "").strip()

    # This panel is for employee accounts only (not staff/superusers).
    users = User.objects.filter(is_staff=False, is_superuser=False).order_by("username")
    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    return render(
        request,
        "portal/admin_panel.html",
        {
            "users": users[:300],
            "q": q,
        },
    )


@staff_required
def admin_create_employee(request):
    User = get_user_model()

    form = AdminEmployeeCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=form.cleaned_data.get("first_name", ""),
            last_name=form.cleaned_data.get("last_name", ""),
        )
        # Force employees to set their password via the "Forgot password" page.
        user.set_unusable_password()
        user.save(update_fields=["password"])

        EmployeeProfile.objects.get_or_create(user=user)
        messages.success(request, f"Employee created: {email}. They can set their password via Forgot password.")
        return redirect("portal:admin_panel")

    return render(request, "portal/admin_create_employee.html", {"form": form})


@staff_required
def admin_toggle_user_active(request, user_id: int):
    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)

    if request.method != "POST":
        return redirect("portal:admin_panel")

    if user.is_superuser or user.is_staff:
        messages.error(request, "This panel can only modify employee accounts (not staff/superusers).")
        return redirect("portal:admin_panel")

    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"Updated {user.username}: is_active={user.is_active}")
    return redirect("portal:admin_panel")


@staff_required
def admin_delete_user(request, user_id: int):
    User = get_user_model()
    user = get_object_or_404(User, pk=user_id)

    if user.is_superuser or user.is_staff:
        messages.error(request, "This panel can only delete employee accounts (not staff/superusers).")
        return redirect("portal:admin_panel")

    if request.method == "POST":
        username = user.username
        user.delete()
        messages.success(request, f"Deleted user: {username}")
        return redirect("portal:admin_panel")

    return render(request, "portal/admin_delete_user.html", {"u": user})
