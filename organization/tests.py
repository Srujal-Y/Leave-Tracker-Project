from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from rest_framework.test import APITestCase
from rest_framework.exceptions import ParseError, PermissionDenied

from leaves.models import LeaveRequest, LeaveType, TalentCandidate
from users.models import AdminAccount

from .context import resolve_company_context
from .models import Company, OrganizationDirectory, OrganizationTenant
from .tenancy import postgres_schema_tenancy_enabled, resolve_tenant_schema, validate_schema_name

User = get_user_model()


class OrganizationContextResolverTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.company_alpha = Company.objects.create(name="Alpha Corp", slug="alpha", active=True)
        self.company_beta = Company.objects.create(name="Beta Corp", slug="beta", active=True)

        directory = OrganizationDirectory.objects.create(
            name="Alpha Corp",
            slug="alpha",
            active=True,
            company=self.company_alpha,
        )
        OrganizationTenant.objects.create(
            directory=directory,
            company=self.company_alpha,
            schema_name="alpha",
            domain="alpha.example.com",
            active=True,
        )

    def test_resolves_company_from_schema_header_for_regular_user(self):
        user = User.objects.create_user(
            username="hr@alpha.com",
            email="hr@alpha.com",
            password="TestPass123!",
            role=User.Role.HR,
            organization=self.company_alpha,
        )
        request = self.factory.get(
            "/api/dashboard/summary/",
            HTTP_X_DTS_SCHEMA="alpha",
        )
        company = resolve_company_context(request, user, allow_request_data=False)
        self.assertEqual(company.id, self.company_alpha.id)

    def test_rejects_mismatched_schema_and_company_id(self):
        admin_user = User.objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="TestPass123!",
            role=User.Role.HR,
        )
        AdminAccount.objects.create(
            user=admin_user,
            level=AdminAccount.Level.PLATFORM,
            can_manage_users=True,
            can_manage_organizations=True,
        )
        request = self.factory.get(
            "/api/org/units/",
            {
                "company_id": str(self.company_beta.id),
            },
            HTTP_X_DTS_SCHEMA="alpha",
        )
        with self.assertRaises(ParseError):
            resolve_company_context(request, admin_user, allow_request_data=False)

    def test_rejects_company_without_access(self):
        user = User.objects.create_user(
            username="employee@alpha.com",
            email="employee@alpha.com",
            password="TestPass123!",
            role=User.Role.EMPLOYEE,
            organization=self.company_alpha,
        )
        request = self.factory.get(
            "/api/leave/requests/",
            {
                "company_id": str(self.company_beta.id),
            },
        )
        with self.assertRaises(PermissionDenied):
            resolve_company_context(request, user, allow_request_data=False)


class OrganizationAccessMatrixAPITests(APITestCase):
    def setUp(self):
        self.company_alpha = Company.objects.create(name="Alpha Corp", slug="alpha", active=True)
        self.company_beta = Company.objects.create(name="Beta Corp", slug="beta", active=True)

        alpha_directory = OrganizationDirectory.objects.create(
            name="Alpha Corp",
            slug="alpha",
            active=True,
            company=self.company_alpha,
        )
        beta_directory = OrganizationDirectory.objects.create(
            name="Beta Corp",
            slug="beta",
            active=True,
            company=self.company_beta,
        )
        OrganizationTenant.objects.create(
            directory=alpha_directory,
            company=self.company_alpha,
            schema_name="alpha",
            domain="alpha.example.com",
            active=True,
        )
        OrganizationTenant.objects.create(
            directory=beta_directory,
            company=self.company_beta,
            schema_name="beta",
            domain="beta.example.com",
            active=True,
        )

        self.platform_admin = User.objects.create_user(
            username="platform@example.com",
            email="platform@example.com",
            password="TestPass123!",
            role=User.Role.HR,
        )
        AdminAccount.objects.create(
            user=self.platform_admin,
            level=AdminAccount.Level.PLATFORM,
            can_manage_users=True,
            can_manage_organizations=True,
        )

        self.org_admin_alpha = User.objects.create_user(
            username="orgadmin@alpha.com",
            email="orgadmin@alpha.com",
            password="TestPass123!",
            role=User.Role.HR,
            organization=self.company_alpha,
        )
        AdminAccount.objects.create(
            user=self.org_admin_alpha,
            level=AdminAccount.Level.ORGANIZATION,
            organization=self.company_alpha,
            can_manage_users=True,
            can_manage_organizations=False,
        )

        self.hr_alpha = User.objects.create_user(
            username="hr@alpha.com",
            email="hr@alpha.com",
            password="TestPass123!",
            role=User.Role.HR,
            organization=self.company_alpha,
        )
        self.hr_beta = User.objects.create_user(
            username="hr@beta.com",
            email="hr@beta.com",
            password="TestPass123!",
            role=User.Role.HR,
            organization=self.company_beta,
        )
        self.employee_alpha = User.objects.create_user(
            username="employee1@alpha.com",
            email="employee1@alpha.com",
            password="TestPass123!",
            role=User.Role.EMPLOYEE,
            organization=self.company_alpha,
        )
        self.employee_alpha_peer = User.objects.create_user(
            username="employee2@alpha.com",
            email="employee2@alpha.com",
            password="TestPass123!",
            role=User.Role.EMPLOYEE,
            organization=self.company_alpha,
        )
        self.employee_beta = User.objects.create_user(
            username="employee@beta.com",
            email="employee@beta.com",
            password="TestPass123!",
            role=User.Role.EMPLOYEE,
            organization=self.company_beta,
        )

        self.leave_type_alpha = LeaveType.objects.create(
            organization=self.company_alpha,
            name="Annual Alpha",
            max_days=20,
            is_paid=True,
            active=True,
        )
        self.leave_type_beta = LeaveType.objects.create(
            organization=self.company_beta,
            name="Annual Beta",
            max_days=20,
            is_paid=True,
            active=True,
        )

        leave_day = date(2026, 2, 10)
        self.leave_alpha_self = LeaveRequest.objects.create(
            organization=self.company_alpha,
            employee=self.employee_alpha,
            leave_type=self.leave_type_alpha,
            leave_label=self.leave_type_alpha.name,
            reason_text="Self leave",
            start_date=leave_day,
            end_date=leave_day,
            requested_units=Decimal("1.00"),
            status=LeaveRequest.Status.PENDING,
        )
        self.leave_alpha_peer = LeaveRequest.objects.create(
            organization=self.company_alpha,
            employee=self.employee_alpha_peer,
            leave_type=self.leave_type_alpha,
            leave_label=self.leave_type_alpha.name,
            reason_text="Peer leave",
            start_date=leave_day,
            end_date=leave_day,
            requested_units=Decimal("1.00"),
            status=LeaveRequest.Status.PENDING,
        )
        self.leave_beta = LeaveRequest.objects.create(
            organization=self.company_beta,
            employee=self.employee_beta,
            leave_type=self.leave_type_beta,
            leave_label=self.leave_type_beta.name,
            reason_text="Beta leave",
            start_date=leave_day,
            end_date=leave_day,
            requested_units=Decimal("1.00"),
            status=LeaveRequest.Status.PENDING,
        )

        self.candidate_alpha = TalentCandidate.objects.create(
            full_name="Alpha Candidate",
            email="candidate.alpha@example.com",
            role_applied="Engineer",
            company=self.company_alpha,
            owner=self.hr_alpha,
        )
        self.candidate_beta = TalentCandidate.objects.create(
            full_name="Beta Candidate",
            email="candidate.beta@example.com",
            role_applied="Engineer",
            company=self.company_beta,
            owner=self.hr_beta,
        )

    @staticmethod
    def _org_headers(company: Company, schema: str | None = None) -> dict:
        headers = {"HTTP_X_COMPANY_ID": str(company.id)}
        if schema:
            headers["HTTP_X_DTS_SCHEMA"] = schema
        return headers

    def test_strict_mode_requires_explicit_context_for_protected_api(self):
        self.client.force_login(self.hr_alpha)
        with self.settings(REQUIRE_EXPLICIT_ORG_CONTEXT=True):
            protected = self.client.get("/api/dashboard/summary/")
            self.assertEqual(protected.status_code, 400)
            self.assertIn("Organization context is required", protected.json().get("detail", ""))

            exempt = self.client.get("/api/org/companies/")
            self.assertEqual(exempt.status_code, 200)

    def test_schema_company_mismatch_returns_400(self):
        self.client.force_login(self.platform_admin)
        response = self.client.get(
            "/api/dashboard/summary/",
            **self._org_headers(self.company_alpha, schema="beta"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("do not match", response.json().get("detail", ""))

    def test_hr_cannot_access_other_company_context(self):
        self.client.force_login(self.hr_alpha)
        response = self.client.get("/api/talent/candidates/", **self._org_headers(self.company_beta, schema="beta"))
        self.assertEqual(response.status_code, 403)

    def test_platform_admin_can_list_users_across_companies(self):
        self.client.force_login(self.platform_admin)
        response = self.client.get("/api/admin/users/", **self._org_headers(self.company_alpha, schema="alpha"))
        self.assertEqual(response.status_code, 200)
        usernames = {row["username"] for row in response.json()}
        self.assertIn(self.hr_alpha.username, usernames)
        self.assertIn(self.hr_beta.username, usernames)

    def test_org_admin_user_list_is_scoped_to_assigned_company(self):
        self.client.force_login(self.org_admin_alpha)
        response = self.client.get("/api/admin/users/", **self._org_headers(self.company_beta, schema="beta"))
        self.assertEqual(response.status_code, 200)
        usernames = {row["username"] for row in response.json()}
        self.assertIn(self.hr_alpha.username, usernames)
        self.assertNotIn(self.hr_beta.username, usernames)
        self.assertNotIn(self.employee_beta.username, usernames)

    def test_employee_cannot_open_admin_users_endpoint(self):
        self.client.force_login(self.employee_alpha)
        response = self.client.get("/api/admin/users/", **self._org_headers(self.company_alpha, schema="alpha"))
        self.assertEqual(response.status_code, 403)

    def test_employee_leave_list_is_self_only(self):
        self.client.force_login(self.employee_alpha)
        response = self.client.get("/api/leave/requests/", **self._org_headers(self.company_alpha, schema="alpha"))
        self.assertEqual(response.status_code, 200)
        results = response.json().get("results", [])
        leave_ids = {row["id"] for row in results}
        self.assertIn(self.leave_alpha_self.id, leave_ids)
        self.assertNotIn(self.leave_alpha_peer.id, leave_ids)
        self.assertNotIn(self.leave_beta.id, leave_ids)

    def test_talent_list_isolation_by_selected_company(self):
        self.client.force_login(self.hr_alpha)
        response = self.client.get("/api/talent/candidates/", **self._org_headers(self.company_alpha, schema="alpha"))
        self.assertEqual(response.status_code, 200)
        candidate_ids = {row["id"] for row in response.json()}
        self.assertIn(self.candidate_alpha.id, candidate_ids)
        self.assertNotIn(self.candidate_beta.id, candidate_ids)

    def test_org_context_endpoint_returns_schema_runtime_flags(self):
        self.client.force_login(self.hr_alpha)
        response = self.client.get("/api/org/context/", **self._org_headers(self.company_alpha, schema="alpha"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("postgres_schema_tenancy_enabled", payload)
        self.assertIn("resolved_schema", payload)
        self.assertIn("schema_switched", payload)
        self.assertEqual(payload["resolved_schema"], "alpha")
        self.assertFalse(payload["schema_switched"])


class OrganizationSchemaTenancyTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Delta Corp", slug="delta", active=True)
        directory = OrganizationDirectory.objects.create(
            name="Delta Corp",
            slug="delta",
            active=True,
            company=self.company,
        )
        OrganizationTenant.objects.create(
            directory=directory,
            company=self.company,
            schema_name="delta_schema",
            domain="delta.example.com",
            active=True,
        )

    def test_validate_schema_name_rejects_invalid_schema(self):
        with self.assertRaises(ParseError):
            validate_schema_name("Bad-Schema")

    def test_resolve_tenant_schema_prefers_tenant_mapping(self):
        schema = resolve_tenant_schema(self.company)
        self.assertEqual(schema, "delta_schema")

    def test_schema_tenancy_switch_is_disabled_on_non_postgres(self):
        with self.settings(ENABLE_POSTGRES_SCHEMA_TENANCY=True):
            self.assertFalse(postgres_schema_tenancy_enabled())
