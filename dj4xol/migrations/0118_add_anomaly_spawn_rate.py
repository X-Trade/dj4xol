from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0117_update_short_id_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='anomaly_spawn_rate',
            field=models.CharField(
                choices=[('LOW', 'Low'), ('NORMAL', 'Normal'), ('HIGH', 'High')],
                default='NORMAL',
                max_length=10,
            ),
        ),
    ]
