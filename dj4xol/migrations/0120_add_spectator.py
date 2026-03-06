from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0119_auto_20260305_1500'),
    ]

    operations = [
        migrations.CreateModel(
            name='Spectator',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('consented_at', models.DateTimeField(auto_now_add=True)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spectatorships', to='dj4xol.Account')),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spectators', to='dj4xol.Game')),
            ],
            options={
                'ordering': ['-consented_at'],
                'unique_together': {('game', 'account')},
            },
        ),
    ]
