from __future__ import annotations

from django import forms

from .models import Holiday, LeaveReasonPreset, LeaveRequest, LeaveType


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)]


class LeaveRequestForm(forms.ModelForm):
    documents = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"multiple": True}),
        help_text="You can upload one or more files. Maximum total upload size is 10 GB.",
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

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        leave_types = self.fields["leave_type"].queryset.filter(active=True)
        reason_presets = self.fields["reason_preset"].queryset.filter(active=True)
        if self.company:
            leave_types = leave_types.filter(organization=self.company)
            reason_presets = reason_presets.filter(organization=self.company)
        self.fields["leave_type"].queryset = leave_types
        self.fields["reason_preset"].queryset = reason_presets
        for field in self.fields.values():
            css = "form-control"
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            field.widget.attrs["class"] = css

    def clean_documents(self):
        documents = self.files.getlist("documents")
        if not documents:
            return []

        total_bytes = 0
        for document in documents:
            document_size = int(getattr(document, "size", 0) or 0)
            total_bytes += document_size
            if document_size > MAX_DOCUMENT_BYTES:
                raise forms.ValidationError(
                    f"'{document.name}' exceeds the 10 GB limit."
                )
        if total_bytes > MAX_DOCUMENT_BYTES:
            raise forms.ValidationError("Total document size cannot exceed 10 GB.")
        return documents

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        leave_type = cleaned.get("leave_type")
        preset = cleaned.get("reason_preset")
        text = (cleaned.get("reason_text") or "").strip()
        portion = cleaned.get("portion") or LeaveRequest.Portion.FULL

        if not preset and not text:
            self.add_error("reason_text", "Select a reason preset or enter custom reason.")
        if preset and not text:
            cleaned["reason_text"] = preset.label

        if start and end and leave_type:
            trial = LeaveRequest(
                organization=self.company,
                employee=self.user,
                leave_type=leave_type,
                start_date=start,
                end_date=end,
                portion=portion,
            )
            if trial.business_days_count() <= 0:
                self.add_error("start_date", "Selected dates contain no working day (Mon-Fri).")

            if self.user:
                overlap = (
                    LeaveRequest.overlapping(
                        start,
                        end,
                        organization_id=self.company.id if self.company else None,
                    )
                    .filter(
                        employee=self.user,
                        status__in=[LeaveRequest.Status.PENDING, LeaveRequest.Status.APPROVED],
                        is_deleted=False,
                    )
                    .exclude(pk=self.instance.pk)
                    .exists()
                )
                if overlap:
                    self.add_error("start_date", "You already have an overlapping leave request.")
        return cleaned

    def save(self, commit=True):
        leave_request: LeaveRequest = super().save(commit=False)
        if self.company and not leave_request.organization_id:
            leave_request.organization = self.company
        leave_request.requested_units = leave_request.compute_requested_units()
        if commit:
            leave_request.save()
        return leave_request


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = ["name", "max_days", "is_paid", "active"]

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-control"
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            if isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            field.widget.attrs["class"] = css

    def save(self, commit=True):
        leave_type: LeaveType = super().save(commit=False)
        if self.company and not leave_type.organization_id:
            leave_type.organization = self.company
        if commit:
            leave_type.save()
        return leave_type


class LeaveReasonPresetForm(forms.ModelForm):
    class Meta:
        model = LeaveReasonPreset
        fields = ["label", "active"]

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-control"
            if isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            field.widget.attrs["class"] = css

    def save(self, commit=True):
        preset: LeaveReasonPreset = super().save(commit=False)
        if self.company and not preset.organization_id:
            preset.organization = self.company
        if commit:
            preset.save()
        return preset


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ["date", "name"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "name": forms.TextInput(attrs={"placeholder": "Holiday name"}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def save(self, commit=True):
        holiday: Holiday = super().save(commit=False)
        if self.company and not holiday.organization_id:
            holiday.organization = self.company
        if commit:
            holiday.save()
        return holiday
