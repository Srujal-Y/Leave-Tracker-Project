from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class WorkspaceThread(models.Model):
    class Module(models.TextChoices):
        LEAVE = "LEAVE", "Leave"
        TALENT = "TALENT", "Talent"
        ONBOARDING = "ONBOARDING", "Onboarding"
        GENERAL = "GENERAL", "General"

    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="workspace_threads")
    module = models.CharField(max_length=32, choices=Module.choices, default=Module.GENERAL)
    title = models.CharField(max_length=180)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_workspace_threads")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "module", "-created_at"])]


class WorkspaceComment(models.Model):
    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="workspace_comments")
    thread = models.ForeignKey(WorkspaceThread, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_comments")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["company", "thread", "created_at"])]

    def clean(self):
        super().clean()
        if self.thread_id and self.company_id and self.thread.company_id != self.company_id:
            raise ValidationError("Comment company must match thread company.")
        if self.author_id and self.company_id and getattr(self.author, "organization_id", None):
            if self.author.organization_id != self.company_id:
                raise ValidationError("Comment author organization must match comment company.")

    def save(self, *args, **kwargs):
        if not self.company_id and self.thread_id:
            self.company_id = self.thread.company_id
        super().save(*args, **kwargs)


class WorkspaceMention(models.Model):
    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="workspace_mentions")
    comment = models.ForeignKey(WorkspaceComment, on_delete=models.CASCADE, related_name="mentions")
    mentioned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_mentions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["comment", "mentioned_user"], name="uniq_workspace_mention_per_comment"),
        ]

    def clean(self):
        super().clean()
        if self.comment_id and self.company_id and self.comment.company_id != self.company_id:
            raise ValidationError("Mention company must match comment company.")
        if self.mentioned_user_id and self.company_id and getattr(self.mentioned_user, "organization_id", None):
            if self.mentioned_user.organization_id != self.company_id:
                raise ValidationError("Mentioned user organization must match mention company.")

    def save(self, *args, **kwargs):
        if not self.company_id and self.comment_id:
            self.company_id = self.comment.company_id
        super().save(*args, **kwargs)


class WorkspacePresence(models.Model):
    class Status(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        AWAY = "AWAY", "Away"
        OFFLINE = "OFFLINE", "Offline"

    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="workspace_presence")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_presence")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OFFLINE)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["company", "user"], name="uniq_workspace_presence_per_user_company"),
        ]

    def clean(self):
        super().clean()
        if self.user_id and self.company_id and getattr(self.user, "organization_id", None):
            if self.user.organization_id != self.company_id:
                raise ValidationError("Presence user organization must match presence company.")


class IdpIdentity(models.Model):
    class Provider(models.TextChoices):
        SAML = "SAML", "SAML"
        OIDC = "OIDC", "OIDC"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="idp_identity")
    provider = models.CharField(max_length=32, choices=Provider.choices)
    external_subject = models.CharField(max_length=255, unique=True)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-linked_at"]


class MfaFactor(models.Model):
    class FactorType(models.TextChoices):
        TOTP = "TOTP", "TOTP"
        EMAIL_OTP = "EMAIL_OTP", "Email OTP"
        SMS_OTP = "SMS_OTP", "SMS OTP"
        WEBAUTHN = "WEBAUTHN", "WebAuthn"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_factors")
    factor_type = models.CharField(max_length=24, choices=FactorType.choices)
    factor_ref = models.CharField(max_length=255, blank=True, default="")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "enabled"])]


class AccessRole(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class AccessPermission(models.Model):
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class RolePermission(models.Model):
    role = models.ForeignKey(AccessRole, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(AccessPermission, on_delete=models.CASCADE, related_name="permission_roles")

    class Meta:
        ordering = ["role__code", "permission__code"]
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="uniq_role_permission"),
        ]


class UserRoleBinding(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_bindings")
    role = models.ForeignKey(AccessRole, on_delete=models.CASCADE, related_name="user_bindings")
    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="user_role_bindings")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assigned_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "role", "company"], name="uniq_user_role_company_binding"),
        ]

    def clean(self):
        super().clean()
        if self.user_id and self.company_id and getattr(self.user, "organization_id", None):
            if self.user.organization_id != self.company_id:
                raise ValidationError("Role binding user organization must match company.")


class SessionToken(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="session_tokens")
    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="session_tokens")
    token_jti = models.CharField(max_length=64, unique=True)
    risk_level = models.CharField(max_length=12, choices=RiskLevel.choices, default=RiskLevel.LOW)
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at", "-id"]
        indexes = [models.Index(fields=["company", "user", "-issued_at"])]

    def clean(self):
        super().clean()
        if self.user_id and self.company_id and getattr(self.user, "organization_id", None):
            if self.user.organization_id != self.company_id:
                raise ValidationError("Session token user organization must match company.")


class ImmutableAuditEvent(models.Model):
    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="immutable_audit_events")
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="immutable_audit_events",
    )
    event_type = models.CharField(max_length=120)
    entity_type = models.CharField(max_length=80, blank=True, default="")
    entity_id = models.CharField(max_length=64, blank=True, default="")
    payload_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "-created_at"])]

    def clean(self):
        super().clean()
        if self.actor_user_id and self.company_id and getattr(self.actor_user, "organization_id", None):
            if self.actor_user.organization_id != self.company_id and not getattr(self.actor_user, "is_superuser", False):
                raise ValidationError("Audit actor organization must match company.")


class WorkflowRule(models.Model):
    class Module(models.TextChoices):
        LEAVE = "LEAVE", "Leave"
        TALENT = "TALENT", "Talent"
        ONBOARDING = "ONBOARDING", "Onboarding"

    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="workflow_rules")
    module = models.CharField(max_length=24, choices=Module.choices)
    trigger_event = models.CharField(max_length=80)
    conditions_json = models.JSONField(default=dict, blank=True)
    actions_json = models.JSONField(default=dict, blank=True)
    sla_minutes = models.IntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "module", "active"])]


class WorkflowInstance(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"

    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="workflow_instances")
    rule = models.ForeignKey(WorkflowRule, on_delete=models.CASCADE, related_name="instances")
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [models.Index(fields=["company", "status", "-started_at"])]

    def clean(self):
        super().clean()
        if self.rule_id and self.company_id and self.rule.company_id != self.company_id:
            raise ValidationError("Workflow instance company must match workflow rule company.")


class WorkflowStepRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"

    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, related_name="steps")
    step_name = models.CharField(max_length=80)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_no = models.IntegerField(default=1)
    last_error = models.TextField(blank=True, default="")
    run_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-run_at", "-id"]
        indexes = [models.Index(fields=["instance", "status", "-run_at"])]


class JobQueueEntry(models.Model):
    class Status(models.TextChoices):
        READY = "READY", "Ready"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"
        DEAD = "DEAD", "Dead"

    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="job_queue_entries")
    job_type = models.CharField(max_length=64)
    payload_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    available_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["available_at", "id"]
        indexes = [models.Index(fields=["company", "status", "available_at"])]


class NotificationOutbox(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        INAPP = "INAPP", "In App"
        WEBHOOK = "WEBHOOK", "Webhook"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="notification_outbox")
    recipient_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_outbox")
    channel = models.CharField(max_length=16, choices=Channel.choices)
    template_code = models.CharField(max_length=80)
    payload_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "status", "-created_at"])]

    def clean(self):
        super().clean()
        if self.recipient_user_id and self.company_id and getattr(self.recipient_user, "organization_id", None):
            if self.recipient_user.organization_id != self.company_id:
                raise ValidationError("Notification recipient organization must match company.")


class TenantConnection(models.Model):
    company = models.OneToOneField("organization.Company", on_delete=models.CASCADE, related_name="tenant_connection")
    db_host = models.CharField(max_length=255)
    db_name = models.CharField(max_length=120)
    db_user = models.CharField(max_length=120)
    secret_ref = models.CharField(max_length=255)
    region = models.CharField(max_length=80, blank=True, default="")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name"]


class TenantProvisionJob(models.Model):
    class JobType(models.TextChoices):
        CREATE_DB = "CREATE_DB", "Create DB"
        MIGRATE = "MIGRATE", "Migrate"
        BACKUP = "BACKUP", "Backup"
        RESTORE = "RESTORE", "Restore"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"

    company = models.ForeignKey("organization.Company", on_delete=models.CASCADE, related_name="tenant_provision_jobs")
    job_type = models.CharField(max_length=40, choices=JobType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    details_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["company", "status", "-created_at"])]


class TenantSchemaMigration(models.Model):
    tenant = models.ForeignKey("organization.OrganizationTenant", on_delete=models.CASCADE, related_name="schema_migrations")
    schema_name = models.CharField(max_length=80)
    migration_name = models.CharField(max_length=255)
    applied_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-applied_at", "-id"]
        indexes = [models.Index(fields=["tenant", "-applied_at"])]

    def clean(self):
        super().clean()
        if self.tenant_id and self.schema_name and self.tenant.schema_name != self.schema_name:
            raise ValidationError("Schema migration schema_name must match tenant schema_name.")
