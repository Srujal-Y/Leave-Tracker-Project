from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

from leave.models import LeaveType, LeaveReasonPreset


class Command(BaseCommand):
    help = "Create baseline auth objects (Managers group)."

    def handle(self, *args, **options):
        # Optional: keep the group for future RBAC, even though approvals are removed.
        _, _ = Group.objects.get_or_create(name="Managers")

        # Seed some sensible defaults (fully editable in Django admin).
        default_types = ["Annual Leave", "Sick Leave", "Work From Home", "Personal", "Emergency"]
        for t in default_types:
            LeaveType.objects.get_or_create(name=t)

        default_reasons = ["Doctor visit", "Family emergency", "Travel", "Mental health", "Government appointment"]
        for r in default_reasons:
            LeaveReasonPreset.objects.get_or_create(label=r)

        self.stdout.write("\nOnboarding checklist:")
        self.stdout.write("1) Create staff users for employees so they can log in.")
        self.stdout.write("2) (Optional) Use Django Admin to edit Leave Types and Reason Presets.")
        self.stdout.write("3) Employees can update their current project/tasks in their Profile.")
        self.stdout.write("4) Use /leave/company/ to view the company-wide leave board.")
