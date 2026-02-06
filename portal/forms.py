from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from employees.models import EmployeeProfile
from django.contrib.auth import get_user_model

class UsernameLoginForm(forms.Form):
    # We keep Django's default "username" field, but in this app we use the employee's
    # email address as the username for simplicity (login + password reset).
    username = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "Email"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Password"}))

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_cache = None

    def clean(self):
        cleaned = super().clean()
        username = (cleaned.get("username") or "").strip()
        password = cleaned.get("password")
        if username and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
        if self.user_cache is None:
            raise forms.ValidationError("Invalid email or password.")
        return cleaned

    def get_user(self):
        return self.user_cache

class ProfileForm(forms.ModelForm):
    class Meta:
        model = EmployeeProfile
        fields = ["phone_number", "current_project", "current_tasks"]
        widgets = {
            "phone_number": forms.TextInput(attrs={"placeholder": "Phone number"}),
            "current_project": forms.TextInput(attrs={"placeholder": "What project are you currently working on?"}),
            "current_tasks": forms.Textarea(attrs={"rows": 4, "placeholder": "What pending tasks/work items are you on?"}),
        }


class PasswordResetQuestionForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "Username"}))
    answer = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "What is 2+2?"}))
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "New password"}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm new password"}))

    def clean(self):
        cleaned = super().clean()
        answer = (cleaned.get("answer") or "").strip()
        password = cleaned.get("new_password")
        confirm = cleaned.get("confirm_password")
        if answer != "4":
            self.add_error("answer", "Incorrect answer. Please type 4.")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        if password:
            validate_password(password)
        return cleaned


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "you@company.com"}))


class PasswordResetVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={"placeholder": "6-digit OTP"}),
        help_text="Check your email for the 6-digit code.",
    )
    new_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "New password"}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm new password"}))

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get("code") or "").strip()
        password = cleaned.get("new_password")
        confirm = cleaned.get("confirm_password")

        if code and (len(code) != 6 or not code.isdigit()):
            self.add_error("code", "Enter the 6-digit code from your email.")

        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        if password:
            validate_password(password)
        return cleaned


class RegistrationForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "Username"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Password"}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Confirm password"}))

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        if password:
            validate_password(password)
        return cleaned


class AdminEmployeeCreateForm(forms.Form):
    """Staff-only: create an employee account.

    We use the employee's email as their Django username for simplicity.
    """

    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "employee@company.com"}))
    first_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"placeholder": "First name"}))
    last_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"placeholder": "Last name"}))

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        User = get_user_model()
        if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email
