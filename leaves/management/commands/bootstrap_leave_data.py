from __future__ import annotations

from django.core.management.base import BaseCommand

from leaves.models import LeaveReasonPreset, LeaveType
from organization.models import Company


class Command(BaseCommand):
    help = "Create default leave types and reason presets."

    def handle(self, *args, **options):
        companies = list(Company.objects.filter(active=True).order_by("id"))
        if not companies:
            companies = [Company.objects.create(name="Default Company", slug="default")]

        defaults = [
            ("Annual", 30, True),
            ("Sick", 15, True),
            ("Unpaid", 10, False),
        ]
        for company in companies:
            for name, max_days, is_paid in defaults:
                LeaveType.objects.get_or_create(
                    organization=company,
                    name=name,
                    defaults={"max_days": max_days, "is_paid": is_paid, "active": True},
                )

        reasons = [
            "Vacation",
            "Medical",
            "Family Emergency",
            "Personal Work",
            "Bereavement",
        ]
        for company in companies:
            for label in reasons:
                LeaveReasonPreset.objects.get_or_create(
                    organization=company,
                    label=label,
                    defaults={"active": True},
                )

        self.stdout.write(self.style.SUCCESS("Default leave data bootstrapped."))
