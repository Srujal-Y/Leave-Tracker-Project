from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import EmployeeProfile
from .permissions import is_admin as user_is_admin

User = get_user_model()


class EmailLoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"placeholder": "Email or username"})
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Password"}))

    def __init__(self, request=None, company=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.company = company
        self._user = None
        for name, field in self.fields.items():
            css = "form-control"
            field.widget.attrs["class"] = css

    def clean(self):
        cleaned = super().clean()
        username_or_email = (cleaned.get("username") or "").strip()
        password = cleaned.get("password")
        if username_or_email and password:
            user = User.objects.filter(email__iexact=username_or_email).first()
            if not user:
                user = User.objects.filter(username__iexact=username_or_email).first()
            auth_username = user.username if user else username_or_email
            self._user = authenticate(self.request, username=auth_username, password=password)
        if self._user is None:
            raise forms.ValidationError("Invalid email/username or password.")
        actor_is_admin = user_is_admin(self._user)
        access = getattr(self._user, "portal_access", User.PortalAccess.BOTH)
        if self.company:
            if not actor_is_admin:
                if access not in {User.PortalAccess.ORGANIZATION, User.PortalAccess.BOTH}:
                    raise forms.ValidationError("This account is not allowed to access the Organization Server.")
        else:
            if not actor_is_admin:
                if access not in {User.PortalAccess.MAIN, User.PortalAccess.BOTH}:
                    raise forms.ValidationError("This account is not allowed to access the Main Leave Tracker.")
        if self.company:
            if not actor_is_admin:
                if self._user.role != User.Role.HR:
                    raise forms.ValidationError("Only HR users can login to an organization server.")
                if not self._user.organization_id or self._user.organization_id != self.company.id:
                    raise forms.ValidationError("This HR user is not assigned to the selected organization.")
        return cleaned

    def get_user(self):
        return self._user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = EmployeeProfile
        fields = ["photo", "phone_number", "current_project", "project_status", "initiatives_to_take"]
        widgets = {
            "phone_number": forms.TextInput(attrs={"placeholder": "Phone number"}),
            "current_project": forms.TextInput(attrs={"placeholder": "Project name"}),
            "project_status": forms.TextInput(attrs={"placeholder": "Current project status"}),
            "initiatives_to_take": forms.Textarea(attrs={"rows": 3, "placeholder": "Upcoming initiatives"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-control"
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            field.widget.attrs["class"] = css


class AdminCreateUserForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "employee@company.com"}))
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    role = forms.ChoiceField(choices=User.Role.choices, initial=User.Role.EMPLOYEE)
    portal_access = forms.ChoiceField(choices=User.PortalAccess.choices, initial=User.PortalAccess.BOTH)
    manager = forms.ModelChoiceField(
        queryset=User.objects.filter(role=User.Role.MANAGER).order_by("first_name", "last_name", "username"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop("organization", None)
        self.organization_server_mode = kwargs.pop("organization_server_mode", False)
        super().__init__(*args, **kwargs)
        if self.organization:
            self.fields["manager"].queryset = self.fields["manager"].queryset.filter(organization=self.organization)
        if self.organization_server_mode:
            self.fields["role"].initial = User.Role.EMPLOYEE
            self.fields["role"].widget = forms.HiddenInput()
        for field in self.fields.values():
            css = "form-control"
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            field.widget.attrs["class"] = css

    def clean_email(self):
        email = (self.cleaned_data["email"] or "").strip().lower()
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_manager(self):
        manager = self.cleaned_data.get("manager")
        if manager and self.organization and manager.organization_id != self.organization.id:
            raise forms.ValidationError("Manager must belong to the same organization.")
        return manager


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "you@company.com"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs["class"] = "form-control"


class PasswordResetVerifyForm(forms.Form):
    code = forms.CharField(max_length=6, widget=forms.TextInput(attrs={"placeholder": "6-digit OTP"}))
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "New password"}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm new password"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get("code") or "").strip()
        new_password = cleaned.get("new_password")
        confirm_password = cleaned.get("confirm_password")
        if len(code) != 6 or not code.isdigit():
            self.add_error("code", "Enter a valid 6-digit OTP.")
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")
        if new_password:
            validate_password(new_password)
        return cleaned
