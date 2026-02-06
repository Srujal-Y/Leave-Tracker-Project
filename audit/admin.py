from django.contrib import admin
from .models import AuditEvent

@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "entity_type", "entity_id")
    search_fields = ("action", "actor__username", "entity_type", "entity_id")
    list_filter = ("action", "entity_type", "created_at")
