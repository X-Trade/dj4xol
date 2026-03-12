from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0157_sync_mechanical_growth_multiplier_from_defaults'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlayerStarMarker',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('marker_type', models.CharField(choices=[('CIRCLE', 'Circle'), ('X', 'X')], max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='star_markers', to='dj4xol.Player')),
                ('star', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='player_markers', to='dj4xol.Star')),
            ],
            options={
                'unique_together': {('player', 'star')},
            },
        ),
    ]
