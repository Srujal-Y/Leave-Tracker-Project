from __future__ import annotations

from rest_framework.permissions import BasePermission
from users.permissions import is_admin as user_is_admin


class IsAdminOrHR(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user_is_admin(user) or getattr(user, "role", "") == "HR")
        )


class IsAdminOnly(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user_is_admin(user))

