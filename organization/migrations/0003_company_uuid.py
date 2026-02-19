import uuid
from django.db import migrations, models


def _populate_company_uuid(apps, schema_editor):
    Company = apps.get_model("organization", "Company")
    for company in Company.objects.filter(uuid__isnull=True):
        company.uuid = uuid.uuid4()
        company.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ('organization', '0002_organizationformfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='uuid',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(_populate_company_uuid, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='company',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
