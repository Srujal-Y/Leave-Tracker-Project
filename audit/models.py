from django.conf import settings
from django.db import models

class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80, blank=True, default="")
    entity_id = models.CharField(max_length=80, blank=True, default="")
    meta_json = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
