from django.conf import settings
from django.db import models

class EmployeeProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee_profile")
    phone_number = models.CharField(max_length=30, blank=True, default="")
    current_project = models.CharField(max_length=200, blank=True, default="")
    current_tasks = models.TextField(blank=True, default="")

    def __str__(self):
        return f"EmployeeProfile({self.user.username})"


class AllowedEmail(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email
