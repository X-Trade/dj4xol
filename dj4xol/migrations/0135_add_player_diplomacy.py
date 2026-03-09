from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0134_add_fleet_travel_warp'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='default_diplomatic_stance',
            field=models.CharField(choices=[('HOSTILE', 'Hostile'), ('COLD', 'Cold'), ('NEUTRAL', 'Neutral'), ('WARM', 'Warm'), ('ALLIED', 'Allied')], default='NEUTRAL', max_length=8),
        ),
        migrations.CreateModel(
            name='PlayerDiplomaticStance',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stance', models.CharField(choices=[('HOSTILE', 'Hostile'), ('COLD', 'Cold'), ('NEUTRAL', 'Neutral'), ('WARM', 'Warm'), ('ALLIED', 'Allied')], default='NEUTRAL', max_length=8)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='diplomatic_stances', to='dj4xol.Player')),
                ('target_player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='diplomatic_stances_targeted_by', to='dj4xol.Player')),
            ],
            options={
                'unique_together': {('player', 'target_player')},
            },
        ),
    ]
