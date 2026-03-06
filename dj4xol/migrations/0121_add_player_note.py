from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0120_add_spectator'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlayerNote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note_id', models.IntegerField()),
                ('text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notes', to='dj4xol.Player')),
            ],
            options={
                'ordering': ['note_id'],
                'unique_together': {('player', 'note_id')},
            },
        ),
    ]
