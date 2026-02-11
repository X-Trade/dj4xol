from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0038_add_account_social_links'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='serverrace',
            name='formal_name',
        ),
        migrations.RemoveField(
            model_name='player',
            name='formal_name',
        ),
    ]
