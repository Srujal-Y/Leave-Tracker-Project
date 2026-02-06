from django.conf import settings
from django.db import models

class EmployeeProfile(models.Model):
    class Role(models.TextChoices):
        EMPLOYEE = "EMPLOYEE", "Employee"
        HR = "HR", "HR"
        ADMIN = "ADMIN", "Admin"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee_profile")
    photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    phone_number = models.CharField(max_length=30, blank=True, default="")
    current_project = models.CharField(max_length=200, blank=True, default="")
    current_tasks = models.TextField(blank=True, default="")

    @property
    def can_manage_leave_config(self) -> bool:
        return self.role in {self.Role.HR, self.Role.ADMIN} or self.user.is_staff

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
