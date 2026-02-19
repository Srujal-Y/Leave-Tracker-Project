from __future__ import annotations

from django.conf import settings
from django.core.exceptions import FieldError
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from rest_framework import permissions, viewsets

from organization.context import resolve_company_context
from users.permissions import is_admin as user_is_admin

from .models import (
    AccessPermission,
    AccessRole,
    IdpIdentity,
    ImmutableAuditEvent,
    JobQueueEntry,
    MfaFactor,
    NotificationOutbox,
    RolePermission,
    SessionToken,
    TenantConnection,
    TenantProvisionJob,
    TenantSchemaMigration,
    UserRoleBinding,
    WorkflowInstance,
    WorkflowRule,
    WorkflowStepRun,
    WorkspaceComment,
    WorkspaceMention,
    WorkspacePresence,
    WorkspaceThread,
)
from .serializers import (
    AccessPermissionSerializer,
    AccessRoleSerializer,
    IdpIdentitySerializer,
    ImmutableAuditEventSerializer,
    JobQueueEntrySerializer,
    MfaFactorSerializer,
    NotificationOutboxSerializer,
    RolePermissionSerializer,
    SessionTokenSerializer,
    TenantConnectionSerializer,
    TenantProvisionJobSerializer,
    TenantSchemaMigrationSerializer,
    UserRoleBindingSerializer,
    WorkflowInstanceSerializer,
    WorkflowRuleSerializer,
    WorkflowStepRunSerializer,
    WorkspaceCommentSerializer,
    WorkspaceMentionSerializer,
    WorkspacePresenceSerializer,
    WorkspaceThreadSerializer,
)


def _company_from_request(request):
    return resolve_company_context(
        request,
        request.user,
        allow_request_data=True,
        require_explicit=bool(getattr(settings, "REQUIRE_EXPLICIT_ORG_CONTEXT", False)),
        bind_user_organization=True,
    )


class IsAdminOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and user_is_admin(request.user))


class CompanyScopedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    company_field_name = "company"

    def get_company(self):
        return _company_from_request(self.request)

    def get_queryset(self):
        model = self.queryset.model
        field_names = {f.name for f in model._meta.get_fields()}
        queryset = self.queryset
        company = self.get_company()

        if self.company_field_name:
            try:
                return queryset.filter(**{self.company_field_name: company})
            except FieldError:
                pass
        if "tenant" in field_names:
            return queryset.filter(tenant__company=company)
        if "user" in field_names:
            return queryset.filter(
                Q(user__organization=company) | Q(user__employee_record__company=company)
            ).distinct()
        return queryset

    @staticmethod
    def _instance_company_id(value):
        if value is None:
            return None
        if hasattr(value, "company_id") and getattr(value, "company_id", None):
            return value.company_id
        if hasattr(value, "organization_id") and getattr(value, "organization_id", None):
            return value.organization_id
        if hasattr(value, "tenant_id") and getattr(value, "tenant_id", None):
            tenant = getattr(value, "tenant", None)
            return getattr(tenant, "company_id", None)
        if hasattr(value, "instance_id") and getattr(value, "instance_id", None):
            instance = getattr(value, "instance", None)
            return getattr(instance, "company_id", None)
        if hasattr(value, "rule_id") and getattr(value, "rule_id", None):
            rule = getattr(value, "rule", None)
            return getattr(rule, "company_id", None)
        if hasattr(value, "thread_id") and getattr(value, "thread_id", None):
            thread = getattr(value, "thread", None)
            return getattr(thread, "company_id", None)
        if hasattr(value, "comment_id") and getattr(value, "comment_id", None):
            comment = getattr(value, "comment", None)
            return getattr(comment, "company_id", None)
        return None

    def _validate_company_consistency(self, serializer, company):
        instance = getattr(serializer, "instance", None)
        instance_company_id = self._instance_company_id(instance)
        if instance_company_id and instance_company_id != company.id:
            raise PermissionDenied("Cross-organization updates are not allowed.")

        for value in serializer.validated_data.values():
            if not hasattr(value, "_meta"):
                continue
            related_company_id = self._instance_company_id(value)
            if related_company_id and related_company_id != company.id:
                raise PermissionDenied("Cross-organization references are not allowed.")

    def perform_update(self, serializer):
        company = self.get_company()
        self._validate_company_consistency(serializer, company)
        serializer.save()

    def perform_create(self, serializer):
        model = self.queryset.model
        field_names = {f.name for f in model._meta.get_fields()}
        company = self.get_company()
        payload = {}

        self._validate_company_consistency(serializer, company)

        if self.company_field_name in field_names:
            payload[self.company_field_name] = company
        if "created_by" in field_names and not serializer.validated_data.get("created_by"):
            payload["created_by"] = self.request.user
        if "author" in field_names and not serializer.validated_data.get("author"):
            payload["author"] = self.request.user
        if "actor_user" in field_names and "actor_user" not in serializer.validated_data:
            payload["actor_user"] = self.request.user

        serializer.save(**payload)


class WorkspaceThreadViewSet(CompanyScopedModelViewSet):
    queryset = WorkspaceThread.objects.select_related("company", "created_by").all()
    serializer_class = WorkspaceThreadSerializer


class WorkspaceCommentViewSet(CompanyScopedModelViewSet):
    queryset = WorkspaceComment.objects.select_related("company", "thread", "author").all()
    serializer_class = WorkspaceCommentSerializer


class WorkspaceMentionViewSet(CompanyScopedModelViewSet):
    queryset = WorkspaceMention.objects.select_related("company", "comment", "mentioned_user").all()
    serializer_class = WorkspaceMentionSerializer


class WorkspacePresenceViewSet(CompanyScopedModelViewSet):
    queryset = WorkspacePresence.objects.select_related("company", "user").all()
    serializer_class = WorkspacePresenceSerializer


class IdpIdentityViewSet(CompanyScopedModelViewSet):
    queryset = IdpIdentity.objects.select_related("user").all()
    serializer_class = IdpIdentitySerializer


class MfaFactorViewSet(CompanyScopedModelViewSet):
    queryset = MfaFactor.objects.select_related("user").all()
    serializer_class = MfaFactorSerializer


class AccessRoleViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]
    queryset = AccessRole.objects.all()
    serializer_class = AccessRoleSerializer


class AccessPermissionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]
    queryset = AccessPermission.objects.all()
    serializer_class = AccessPermissionSerializer


class RolePermissionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOnly]
    queryset = RolePermission.objects.select_related("role", "permission").all()
    serializer_class = RolePermissionSerializer


class UserRoleBindingViewSet(CompanyScopedModelViewSet):
    queryset = UserRoleBinding.objects.select_related("user", "role", "company").all()
    serializer_class = UserRoleBindingSerializer


class SessionTokenViewSet(CompanyScopedModelViewSet):
    queryset = SessionToken.objects.select_related("user", "company").all()
    serializer_class = SessionTokenSerializer


class ImmutableAuditEventViewSet(CompanyScopedModelViewSet):
    queryset = ImmutableAuditEvent.objects.select_related("company", "actor_user").all()
    serializer_class = ImmutableAuditEventSerializer


class WorkflowRuleViewSet(CompanyScopedModelViewSet):
    queryset = WorkflowRule.objects.select_related("company").all()
    serializer_class = WorkflowRuleSerializer


class WorkflowInstanceViewSet(CompanyScopedModelViewSet):
    queryset = WorkflowInstance.objects.select_related("company", "rule").all()
    serializer_class = WorkflowInstanceSerializer


class WorkflowStepRunViewSet(CompanyScopedModelViewSet):
    queryset = WorkflowStepRun.objects.select_related("instance").all()
    serializer_class = WorkflowStepRunSerializer
    company_field_name = "instance__company"


class JobQueueEntryViewSet(CompanyScopedModelViewSet):
    queryset = JobQueueEntry.objects.select_related("company").all()
    serializer_class = JobQueueEntrySerializer


class NotificationOutboxViewSet(CompanyScopedModelViewSet):
    queryset = NotificationOutbox.objects.select_related("company", "recipient_user").all()
    serializer_class = NotificationOutboxSerializer


class TenantConnectionViewSet(CompanyScopedModelViewSet):
    queryset = TenantConnection.objects.select_related("company").all()
    serializer_class = TenantConnectionSerializer


class TenantProvisionJobViewSet(CompanyScopedModelViewSet):
    queryset = TenantProvisionJob.objects.select_related("company").all()
    serializer_class = TenantProvisionJobSerializer


class TenantSchemaMigrationViewSet(CompanyScopedModelViewSet):
    queryset = TenantSchemaMigration.objects.select_related("tenant", "tenant__company").all()
    serializer_class = TenantSchemaMigrationSerializer
