from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeprofile",
            name="phone_number",
            field=models.CharField(default="", max_length=30),
        ),
    ]
