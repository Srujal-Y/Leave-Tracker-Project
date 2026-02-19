from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from organization.models import Company, OrganizationDirectory, OrganizationTenant
from organization.tenancy import ensure_tenant_schema, validate_schema_name


class Command(BaseCommand):
    help = "Provision OrganizationTenant metadata and PostgreSQL schema for a company."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id",
            type=int,
            required=True,
            help="Company id to provision.",
        )
        parser.add_argument(
            "--schema",
            type=str,
            default="",
            help="Schema name override. Defaults to current tenant schema or company slug.",
        )
        parser.add_argument(
            "--domain",
            type=str,
            default="",
            help="Tenant domain override. Defaults to <schema>.local.",
        )
        parser.add_argument(
            "--create-schema",
            action="store_true",
            help="Create PostgreSQL schema if it does not exist.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Tenant schema provisioning requires PostgreSQL as DATABASE_URL backend.")

        company = Company.objects.filter(pk=options["company_id"], active=True).first()
        if not company:
            raise CommandError("Company not found or inactive.")

        existing_tenant = OrganizationTenant.objects.filter(company=company).first()
        raw_schema = (
            (options.get("schema") or "").strip().lower()
            or (existing_tenant.schema_name if existing_tenant else "")
            or company.slug
        )
        schema_name = validate_schema_name(raw_schema)
        domain = (
            (options.get("domain") or "").strip().lower()
            or (existing_tenant.domain if existing_tenant else "")
            or f"{schema_name}.local"
        )

        with transaction.atomic():
            directory, _ = OrganizationDirectory.objects.get_or_create(
                slug=company.slug,
                defaults={
                    "name": company.name,
                    "active": company.active,
                    "company": company,
                },
            )
            if directory.company_id != company.id:
                directory.company = company
                directory.save(update_fields=["company"])

            tenant, created = OrganizationTenant.objects.get_or_create(
                company=company,
                defaults={
                    "directory": directory,
                    "schema_name": schema_name,
                    "domain": domain,
                    "active": True,
                },
            )
            if not created:
                updates = []
                if tenant.directory_id != directory.id:
                    tenant.directory = directory
                    updates.append("directory")
                if tenant.schema_name != schema_name:
                    tenant.schema_name = schema_name
                    updates.append("schema_name")
                if tenant.domain != domain:
                    tenant.domain = domain
                    updates.append("domain")
                if not tenant.active:
                    tenant.active = True
                    updates.append("active")
                if updates:
                    tenant.save(update_fields=updates)

        created_schema = ensure_tenant_schema(schema_name, auto_create=bool(options.get("create_schema")))
        if options.get("create_schema") and not created_schema:
            raise CommandError("Schema creation failed.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Tenant metadata ready: company={company.id} schema={schema_name} domain={domain} "
                f"schema_exists={'yes' if created_schema else 'no'}"
            )
        )
        if not options.get("create_schema"):
            self.stdout.write(
                "Schema was not auto-created. Re-run with --create-schema if you want Django to create it."
            )
