from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import LeaveBalance, LeaveRequest, LeaveType

User = get_user_model()


def _default_allocation(leave_type: LeaveType) -> Decimal:
    return Decimal(str(leave_type.max_days or 0))


def _ensure_balance(user, leave_type: LeaveType, year: int, organization=None) -> LeaveBalance:
    target_org = organization or leave_type.organization or getattr(user, "organization", None)
    balance, _ = LeaveBalance.objects.get_or_create(
        organization=target_org,
        user=user,
        leave_type=leave_type,
        year=year,
        defaults={"allocated_days": _default_allocation(leave_type)},
    )
    return balance


@receiver(post_save, sender=User)
def create_initial_leave_balances(sender, instance, created, **kwargs):
    """Create LeaveBalance records when a new user is created."""
    if not created:
        return
    if not getattr(instance, "organization_id", None):
        return
    current_year = date.today().year
    for leave_type in LeaveType.objects.filter(active=True, organization_id=instance.organization_id):
        _ensure_balance(instance, leave_type, current_year, organization=instance.organization)


@receiver(post_save, sender=LeaveType)
def create_leave_type_balances_for_all_users(sender, instance, created, **kwargs):
    if not instance.organization_id:
        return
    current_year = date.today().year
    default_quota = _default_allocation(instance)
    users_in_org = User.objects.filter(organization_id=instance.organization_id)
    if created:
        for user in users_in_org.iterator():
            LeaveBalance.objects.get_or_create(
                organization=instance.organization,
                user=user,
                leave_type=instance,
                year=current_year,
                defaults={"allocated_days": default_quota},
            )
    else:
        LeaveBalance.objects.filter(
            leave_type=instance,
            organization=instance.organization,
            year__gte=current_year,
        ).update(allocated_days=default_quota)


def _consume_request(request: LeaveRequest):
    for year, units in request.units_by_year().items():
        balance = _ensure_balance(
            request.employee,
            request.leave_type,
            year,
            organization=request.organization,
        )
        balance.consume(units)


def _release_request(request: LeaveRequest):
    for year, units in request.units_by_year().items():
        balance = _ensure_balance(
            request.employee,
            request.leave_type,
            year,
            organization=request.organization,
        )
        balance.release(units)


@receiver(pre_save, sender=LeaveRequest)
def capture_old_leave_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    old = LeaveRequest.objects.filter(pk=instance.pk).values("status").first()
    instance._old_status = old["status"] if old else None


@receiver(post_save, sender=LeaveRequest)
def maintain_balance_on_status_change(sender, instance, created, **kwargs):
    old_status = getattr(instance, "_old_status", None)
    if created:
        if instance.status == LeaveRequest.Status.APPROVED:
            _consume_request(instance)
        return

    if old_status == instance.status:
        return

    if old_status != LeaveRequest.Status.APPROVED and instance.status == LeaveRequest.Status.APPROVED:
        _consume_request(instance)
    elif old_status == LeaveRequest.Status.APPROVED and instance.status != LeaveRequest.Status.APPROVED:
        _release_request(instance)
