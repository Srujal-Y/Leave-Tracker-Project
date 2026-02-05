from .authz import is_manager_email

def portal_globals(request):
    email = getattr(getattr(request, "user", None), "email", "") if getattr(request, "user", None) else ""
    return {
        "PORTAL_APP_NAME": "Alemeno Leave Tracker",
        "IS_MANAGER": bool(request.user.is_authenticated and is_manager_email(email)),
    }
