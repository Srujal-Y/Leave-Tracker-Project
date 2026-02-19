from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AccessPermissionViewSet,
    AccessRoleViewSet,
    IdpIdentityViewSet,
    ImmutableAuditEventViewSet,
    JobQueueEntryViewSet,
    MfaFactorViewSet,
    NotificationOutboxViewSet,
    RolePermissionViewSet,
    SessionTokenViewSet,
    TenantConnectionViewSet,
    TenantProvisionJobViewSet,
    TenantSchemaMigrationViewSet,
    UserRoleBindingViewSet,
    WorkflowInstanceViewSet,
    WorkflowRuleViewSet,
    WorkflowStepRunViewSet,
    WorkspaceCommentViewSet,
    WorkspaceMentionViewSet,
    WorkspacePresenceViewSet,
    WorkspaceThreadViewSet,
)

router = DefaultRouter()
router.register("workspace/threads", WorkspaceThreadViewSet, basename="arch_workspace_threads")
router.register("workspace/comments", WorkspaceCommentViewSet, basename="arch_workspace_comments")
router.register("workspace/mentions", WorkspaceMentionViewSet, basename="arch_workspace_mentions")
router.register("workspace/presence", WorkspacePresenceViewSet, basename="arch_workspace_presence")
router.register("compliance/idp-identities", IdpIdentityViewSet, basename="arch_idp_identities")
router.register("compliance/mfa-factors", MfaFactorViewSet, basename="arch_mfa_factors")
router.register("compliance/roles", AccessRoleViewSet, basename="arch_access_roles")
router.register("compliance/permissions", AccessPermissionViewSet, basename="arch_access_permissions")
router.register("compliance/role-permissions", RolePermissionViewSet, basename="arch_role_permissions")
router.register("compliance/user-role-bindings", UserRoleBindingViewSet, basename="arch_user_role_bindings")
router.register("compliance/session-tokens", SessionTokenViewSet, basename="arch_session_tokens")
router.register("compliance/immutable-audit-events", ImmutableAuditEventViewSet, basename="arch_immutable_audit_events")
router.register("workflow/rules", WorkflowRuleViewSet, basename="arch_workflow_rules")
router.register("workflow/instances", WorkflowInstanceViewSet, basename="arch_workflow_instances")
router.register("workflow/step-runs", WorkflowStepRunViewSet, basename="arch_workflow_step_runs")
router.register("workflow/job-queue", JobQueueEntryViewSet, basename="arch_job_queue_entries")
router.register("workflow/notification-outbox", NotificationOutboxViewSet, basename="arch_notification_outbox")
router.register("control/tenant-connections", TenantConnectionViewSet, basename="arch_tenant_connections")
router.register("control/tenant-provision-jobs", TenantProvisionJobViewSet, basename="arch_tenant_provision_jobs")
router.register("control/tenant-schema-migrations", TenantSchemaMigrationViewSet, basename="arch_tenant_schema_migrations")

urlpatterns = [
    path("", include(router.urls)),
]
