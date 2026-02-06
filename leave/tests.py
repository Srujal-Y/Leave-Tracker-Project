from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import LeaveRequest, LeaveType


class LeaveFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="u@example.com", email="u@example.com", password="pass12345")
        self.type = LeaveType.objects.create(name="Annual", annual_quota=Decimal("10.00"), active=True)

    def test_overlap_blocked(self):
        LeaveRequest.objects.create(
            employee=self.user,
            leave_type=self.type,
            start_date=date(2026, 2, 10),
            end_date=date(2026, 2, 12),
            requested_units=Decimal("3.00"),
            status=LeaveRequest.Status.AUTHENTICATED,
            reason_text="Trip",
        )
        self.client.login(username="u@example.com", password="pass12345")
        res = self.client.post(reverse("leave:apply_leave"), {
            "leave_type": self.type.id,
            "leave_label": "Annual",
            "start_date": "2026-02-11",
            "end_date": "2026-02-13",
            "portion": LeaveRequest.Portion.FULL,
            "reason_text": "Overlap",
        })
        self.assertContains(res, "overlapping leave dates")

    def test_quota_blocked(self):
        LeaveRequest.objects.create(
            employee=self.user,
            leave_type=self.type,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 8),
            requested_units=Decimal("8.00"),
            status=LeaveRequest.Status.AUTHENTICATED,
            reason_text="Used",
        )
        self.client.login(username="u@example.com", password="pass12345")
        res = self.client.post(reverse("leave:apply_leave"), {
            "leave_type": self.type.id,
            "leave_label": "Annual",
            "start_date": "2026-03-01",
            "end_date": "2026-03-05",
            "portion": LeaveRequest.Portion.FULL,
            "reason_text": "Need more",
        })
        self.assertContains(res, "Insufficient balance")
