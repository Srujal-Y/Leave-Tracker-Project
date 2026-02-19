from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_passwordresetotp_organization_user_organization"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="portal_access",
            field=models.CharField(
                choices=[
                    ("MAIN", "Main Leave Tracker"),
                    ("ORGANIZATION", "Organization Server"),
                    ("BOTH", "Both Trackers"),
                ],
                default="BOTH",
                help_text="Controls whether user can login to Main tracker, Organization server, or both.",
                max_length=16,
            ),
        ),
    ]
