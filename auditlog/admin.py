from __future__ import annotations

from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "entity_type", "entity_id")
    list_filter = ("action", "entity_type", "created_at")
    search_fields = ("action", "actor__username", "actor__email", "entity_type", "entity_id")
