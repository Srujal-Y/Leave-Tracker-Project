from django.contrib import admin

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


@admin.register(WorkspaceThread)
class WorkspaceThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "module", "title", "created_by", "created_at")
    list_filter = ("company", "module")
    search_fields = ("title", "created_by__username", "created_by__email")


@admin.register(WorkspaceComment)
class WorkspaceCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "thread", "author", "created_at")
    list_filter = ("company",)
    search_fields = ("thread__title", "author__username", "body")


@admin.register(WorkspaceMention)
class WorkspaceMentionAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "comment", "mentioned_user", "created_at")
    list_filter = ("company",)
    search_fields = ("mentioned_user__username", "mentioned_user__email")


@admin.register(WorkspacePresence)
class WorkspacePresenceAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "user", "status", "last_seen_at")
    list_filter = ("company", "status")
    search_fields = ("user__username", "user__email")


@admin.register(IdpIdentity)
class IdpIdentityAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "provider", "external_subject", "linked_at")
    list_filter = ("provider",)
    search_fields = ("user__username", "user__email", "external_subject")


@admin.register(MfaFactor)
class MfaFactorAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "factor_type", "enabled", "created_at")
    list_filter = ("factor_type", "enabled")
    search_fields = ("user__username", "user__email", "factor_ref")


@admin.register(AccessRole)
class AccessRoleAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name")
    search_fields = ("code", "name")


@admin.register(AccessPermission)
class AccessPermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name")
    search_fields = ("code", "name")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "role", "permission")
    list_filter = ("role",)


@admin.register(UserRoleBinding)
class UserRoleBindingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "company", "assigned_at")
    list_filter = ("company", "role")
    search_fields = ("user__username", "user__email")


@admin.register(SessionToken)
class SessionTokenAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "company", "token_jti", "risk_level", "issued_at", "expires_at", "revoked_at")
    list_filter = ("company", "risk_level")
    search_fields = ("token_jti", "user__username", "user__email")


@admin.register(ImmutableAuditEvent)
class ImmutableAuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "actor_user", "event_type", "entity_type", "entity_id", "created_at")
    list_filter = ("company", "event_type")
    search_fields = ("event_type", "entity_type", "entity_id")


@admin.register(WorkflowRule)
class WorkflowRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "module", "trigger_event", "sla_minutes", "active", "created_at")
    list_filter = ("company", "module", "active")
    search_fields = ("trigger_event",)


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "rule", "entity_type", "entity_id", "status", "started_at", "finished_at")
    list_filter = ("company", "status")
    search_fields = ("entity_type", "entity_id")


@admin.register(WorkflowStepRun)
class WorkflowStepRunAdmin(admin.ModelAdmin):
    list_display = ("id", "instance", "step_name", "status", "attempt_no", "run_at")
    list_filter = ("status",)
    search_fields = ("step_name",)


@admin.register(JobQueueEntry)
class JobQueueEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "job_type", "status", "available_at", "created_at")
    list_filter = ("company", "status", "job_type")
    search_fields = ("job_type",)


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "recipient_user", "channel", "template_code", "status", "created_at")
    list_filter = ("company", "channel", "status")
    search_fields = ("template_code", "recipient_user__username", "recipient_user__email")


@admin.register(TenantConnection)
class TenantConnectionAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "db_host", "db_name", "db_user", "region", "active")
    list_filter = ("active", "region")
    search_fields = ("company__name", "db_host", "db_name", "db_user")


@admin.register(TenantProvisionJob)
class TenantProvisionJobAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "job_type", "status", "created_at", "finished_at")
    list_filter = ("company", "job_type", "status")
    search_fields = ("company__name",)


@admin.register(TenantSchemaMigration)
class TenantSchemaMigrationAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "schema_name", "migration_name", "applied_at")
    list_filter = ("schema_name",)
    search_fields = ("schema_name", "migration_name")
