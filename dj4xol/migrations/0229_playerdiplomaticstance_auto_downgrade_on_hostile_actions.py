from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0228_remove_pending_default_diplomatic_stance'),
    ]

    operations = [
        migrations.AddField(
            model_name='playerdiplomaticstance',
            name='auto_downgrade_on_hostile_actions',
            field=models.BooleanField(default=True),
        ),
    ]
