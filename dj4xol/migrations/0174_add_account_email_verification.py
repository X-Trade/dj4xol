from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0173_add_custom_help_pages'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='email_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='account',
            name='email_verification_key',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
