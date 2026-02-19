from __future__ import annotations

from rest_framework import serializers

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


class WorkspaceThreadSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceThread
        fields = "__all__"


class WorkspaceCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceComment
        fields = "__all__"


class WorkspaceMentionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceMention
        fields = "__all__"


class WorkspacePresenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspacePresence
        fields = "__all__"


class IdpIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = IdpIdentity
        fields = "__all__"


class MfaFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = MfaFactor
        fields = "__all__"


class AccessRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessRole
        fields = "__all__"


class AccessPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessPermission
        fields = "__all__"


class RolePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = "__all__"


class UserRoleBindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserRoleBinding
        fields = "__all__"


class SessionTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionToken
        fields = "__all__"


class ImmutableAuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImmutableAuditEvent
        fields = "__all__"


class WorkflowRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowRule
        fields = "__all__"


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowInstance
        fields = "__all__"


class WorkflowStepRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStepRun
        fields = "__all__"


class JobQueueEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = JobQueueEntry
        fields = "__all__"


class NotificationOutboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationOutbox
        fields = "__all__"


class TenantConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantConnection
        fields = "__all__"


class TenantProvisionJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantProvisionJob
        fields = "__all__"


class TenantSchemaMigrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSchemaMigration
        fields = "__all__"
