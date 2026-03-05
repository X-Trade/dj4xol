from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('dj4xol', '0116_add_salvage_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='game',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='serverrace',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='technology',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='gameinvitation',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='star',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='fleet',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='salvage',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='anomaly',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='player',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='fleetorders',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='productionorder',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='gamemessage',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name='report',
            name='short_id',
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterUniqueTogether(
            name='game',
            unique_together={('short_id',)},
        ),
        migrations.AlterUniqueTogether(
            name='serverrace',
            unique_together={('short_id',)},
        ),
        migrations.AlterUniqueTogether(
            name='technology',
            unique_together={('category', 'level', 'name'), ('short_id',)},
        ),
        migrations.AlterUniqueTogether(
            name='gameinvitation',
            unique_together={('game', 'account'), ('game', 'email'), ('short_id',)},
        ),
        migrations.AlterUniqueTogether(
            name='star',
            unique_together={('game', 'short_id')},
        ),
        migrations.AlterUniqueTogether(
            name='fleet',
            unique_together={('game', 'short_id')},
        ),
        migrations.AlterUniqueTogether(
            name='salvage',
            unique_together={('game', 'x', 'y'), ('game', 'short_id')},
        ),
        migrations.AlterUniqueTogether(
            name='anomaly',
            unique_together={('game', 'short_id')},
        ),
        migrations.AlterUniqueTogether(
            name='player',
            unique_together={('game', 'short_id')},
        ),
        migrations.AlterUniqueTogether(
            name='fleetorders',
            unique_together={('game', 'short_id')},
        ),
        migrations.AlterUniqueTogether(
            name='productionorder',
            unique_together={('game', 'short_id')},
        ),
        migrations.AlterUniqueTogether(
            name='gamemessage',
            unique_together={('game', 'short_id')},
        ),
        migrations.AlterUniqueTogether(
            name='report',
            unique_together={('player', 'target_type', 'target_id'), ('game', 'short_id')},
        ),
    ]
