from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_notification_email(subject: str, message: str, recipients: list[str]):
    recipients = [r for r in recipients if r]
    if not recipients:
        return
    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=recipients,
        fail_silently=getattr(settings, "EMAIL_FAIL_SILENTLY", True),
    )
