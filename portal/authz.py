from django.conf import settings
from django.contrib.auth.decorators import user_passes_test

def is_manager_email(email: str) -> bool:
    if not email:
        return False
    email = email.strip().lower()
    return email in getattr(settings, "MANAGER_EMAILS", [])

def manager_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and is_manager_email(getattr(u, "email", "")))(view_func)
