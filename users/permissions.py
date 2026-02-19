from __future__ import annotations

from django.contrib.auth.decorators import user_passes_test

from .models import AdminAccount, User


def _admin_account(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.admin_account
    except AdminAccount.DoesNotExist:
        return None


def is_admin(user, company_id: int | None = None) -> bool:
    admin_account = _admin_account(user)
    if not admin_account:
        return False
    if admin_account.level == AdminAccount.Level.PLATFORM:
        return True
    if admin_account.level == AdminAccount.Level.ORGANIZATION:
        if company_id is None:
            return True
        return admin_account.organization_id == company_id
    return False


def can_manage_organizations(user) -> bool:
    admin_account = _admin_account(user)
    return bool(admin_account and (admin_account.level == AdminAccount.Level.PLATFORM or admin_account.can_manage_organizations))


def is_admin_or_hr(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (is_admin(user) or getattr(user, "role", "") == User.Role.HR)
    )


def is_manager_or_above(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            is_admin(user)
            or getattr(user, "role", "") in {User.Role.HR, User.Role.MANAGER}
        )
    )


def admin_or_hr_required(view_func):
    return user_passes_test(is_admin_or_hr)(view_func)


def admin_only_required(view_func):
    return user_passes_test(is_admin)(view_func)
