from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0035_auto_20260210_2231'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='salvage',
            unique_together={('game', 'x', 'y')},
        ),
    ]
