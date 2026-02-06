from __future__ import annotations

from decimal import Decimal

from django import forms

from .models import LeaveRequest


class LeaveRequestForm(forms.ModelForm):
    """Leave request form.

    Key behaviors:
    - Unlimited duration (no max-days constraint)
    - Portion (FULL/HALF/QUARTER) supported
    - Reason can be preset (dropdown) or custom text
    - requested_units is derived from dates + portion by default, but can be overridden
    """

    override_units = forms.DecimalField(
        required=False,
        min_value=Decimal("0.00"),
        decimal_places=2,
        max_digits=9,
        help_text="Optional: override auto-computed units (e.g., 0.25, 0.50, 3.00).",
    )

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

    def clean(self):
        cleaned = super().clean()

        # Require at least one reason input
        preset = cleaned.get("reason_preset")
        text = (cleaned.get("reason_text") or "").strip()
        if not preset and not text:
            self.add_error("reason_text", "Please select a reason or type a custom reason.")

        # If a preset is selected and no custom text, mirror it for convenience
        if preset and not text:
            cleaned["reason_text"] = preset.label

        # If label is empty, leave model.save() will fill a sensible default.
        return cleaned

    def save(self, commit=True):
        obj: LeaveRequest = super().save(commit=False)

        # Compute requested_units by default; allow optional override.
        override = self.cleaned_data.get("override_units")
        if override is not None and override != "":
            obj.requested_units = Decimal(str(override))
        else:
            obj.requested_units = obj.compute_requested_units()

        if commit:
            obj.save()
        return obj
