from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LeaveType",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("name", models.CharField(max_length=60, unique=True)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="LeaveReasonPreset",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("label", models.CharField(max_length=80)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["label"],
            },
        ),
        migrations.CreateModel(
            name="LeaveRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                (
                    "leave_label",
                    models.CharField(blank=True, default="", max_length=80),
                ),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                (
                    "portion",
                    models.CharField(
                        choices=[
                            ("FULL", "Full day(s)"),
                            ("HALF", "Half day"),
                            ("QUARTER", "Quarter day"),
                        ],
                        default="FULL",
                        max_length=10,
                    ),
                ),
                (
                    "requested_units",
                    models.DecimalField(decimal_places=2, default=Decimal("1.00"), max_digits=9),
                ),
                ("reason_text", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "employee",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
                ),
                (
                    "leave_type",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="leave.leavetype"),
                ),
                (
                    "reason_preset",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="leave.leavereasonpreset"),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="leaverequest",
            index=models.Index(fields=["start_date", "end_date"], name="leave_leave_start_d5b5b7_idx"),
        ),
        migrations.AddIndex(
            model_name="leaverequest",
            index=models.Index(fields=["employee", "-created_at"], name="leave_leave_employee_1b3a56_idx"),
        ),
    ]
