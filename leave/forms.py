from __future__ import annotations

from decimal import Decimal

from django import forms
from django.db.models import Sum

from .models import Holiday, LeaveReasonPreset, LeaveRequest, LeaveType


class LeaveRequestForm(forms.ModelForm):
    override_units = forms.DecimalField(required=False, min_value=Decimal("0.00"), decimal_places=2, max_digits=9)

    class Meta:
        model = LeaveRequest
        fields = [
            "leave_type",
            "leave_label",
            "start_date",
            "end_date",
            "portion",
            "reason_preset",
            "reason_text",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.instance_to_edit = kwargs.get("instance")
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        preset = cleaned.get("reason_preset")
        text = (cleaned.get("reason_text") or "").strip()
        if not preset and not text:
            self.add_error("reason_text", "Please select a reason or type a custom reason.")
        if preset and not text:
            cleaned["reason_text"] = preset.label

        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        leave_type = cleaned.get("leave_type")
        if self.user and start and end:
            overlap = LeaveRequest.overlapping(start, end).filter(employee=self.user).exclude(status=LeaveRequest.Status.CANCELLED)
            if self.instance_to_edit and self.instance_to_edit.pk:
                overlap = overlap.exclude(pk=self.instance_to_edit.pk)
            if overlap.exists():
                self.add_error("start_date", "You already have overlapping leave dates.")

        if self.user and leave_type and start and end:
            req_units = LeaveRequest(
                employee=self.user,
                start_date=start,
                end_date=end,
                portion=cleaned.get("portion") or LeaveRequest.Portion.FULL,
            ).compute_requested_units()
            used = (
                LeaveRequest.objects.filter(
                    employee=self.user,
                    leave_type=leave_type,
                    status=LeaveRequest.Status.AUTHENTICATED,
                    deleted_at__isnull=True,
                )
                .exclude(pk=getattr(self.instance_to_edit, "pk", None))
                .aggregate(s=Sum("requested_units"))
                .get("s")
                or Decimal("0")
            )
            if used + req_units > leave_type.annual_quota:
                self.add_error("leave_type", f"Insufficient balance. Remaining: {leave_type.annual_quota - used} day(s).")

        return cleaned

    def save(self, commit=True):
        obj: LeaveRequest = super().save(commit=False)
        override = self.cleaned_data.get("override_units")
        obj.requested_units = Decimal(str(override)) if override not in (None, "") else obj.compute_requested_units()
        if commit:
            obj.save()
        return obj


class LeaveBoardFilterForm(forms.Form):
    q = forms.CharField(required=False)
    employee = forms.CharField(required=False)
    leave_type = forms.ModelChoiceField(queryset=LeaveType.objects.filter(active=True), required=False)
    month = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"), input_formats=["%Y-%m"])
    portion = forms.ChoiceField(required=False, choices=[("", "All")] + list(LeaveRequest.Portion.choices))
    status = forms.ChoiceField(required=False, choices=[("", "All")] + list(LeaveRequest.Status.choices))


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = ["name", "annual_quota", "active"]


class LeaveReasonPresetForm(forms.ModelForm):
    class Meta:
        model = LeaveReasonPreset
        fields = ["label", "active"]


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ["title", "day", "active"]
        widgets = {"day": forms.DateInput(attrs={"type": "date"})}
