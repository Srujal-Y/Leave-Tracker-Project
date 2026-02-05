from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [
        migrations.CreateModel(
            name="EmployeeProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("photo", models.ImageField(blank=True, null=True, upload_to="employee_photos/")),
                ("current_project", models.CharField(blank=True, default="", max_length=200)),
                ("current_tasks", models.TextField(blank=True, default="")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="employee_profile", to="auth.user")),
            ],
        ),
    ]
