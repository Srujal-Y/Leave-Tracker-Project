from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from organization.models import Company

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Backfill user creator metadata for legacy employee users. "
        "Sets created_in_organization from organization and, when possible, "
        "sets created_by to the only HR in the same organization."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))

        updated_created_in_org = 0
        updated_created_by = 0
        skipped_ambiguous_hr = 0
        total_candidates = 0

        employees = User.objects.filter(role=User.Role.EMPLOYEE, organization__isnull=False).select_related("organization")

        for user in employees.iterator():
            total_candidates += 1
            dirty_fields: list[str] = []

            if not user.created_in_organization_id and user.organization_id:
                user.created_in_organization = user.organization
                dirty_fields.append("created_in_organization")
                updated_created_in_org += 1

            if not user.created_by_id and user.organization_id:
                hr_users = list(
                    User.objects.filter(
                        role=User.Role.HR,
                        organization_id=user.organization_id,
                    ).order_by("id")[:2]
                )
                if len(hr_users) == 1:
                    user.created_by = hr_users[0]
                    dirty_fields.append("created_by")
                    updated_created_by += 1
                elif len(hr_users) > 1:
                    skipped_ambiguous_hr += 1

            if dirty_fields and not dry_run:
                user.save(update_fields=dirty_fields)

        company_count = Company.objects.filter(active=True).count()
        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Backfill completed."))
        self.stdout.write(f"Active companies scanned: {company_count}")
        self.stdout.write(f"Employee users scanned: {total_candidates}")
        self.stdout.write(f"created_in_organization updated: {updated_created_in_org}")
        self.stdout.write(f"created_by updated: {updated_created_by}")
        self.stdout.write(f"Skipped (ambiguous HR in company): {skipped_ambiguous_hr}")
