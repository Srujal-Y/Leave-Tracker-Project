from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import EmployeeProfile, AllowedEmail

User = get_user_model()

@receiver(post_save, sender=User)
def ensure_employee_profile(sender, instance, created, **kwargs):
    EmployeeProfile.objects.get_or_create(user=instance)
    email = (instance.email or "").strip().lower()
    if email:
        AllowedEmail.objects.get_or_create(email=email)
