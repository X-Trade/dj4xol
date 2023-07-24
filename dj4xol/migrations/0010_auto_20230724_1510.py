# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2023-07-24 15:10
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0009_auto_20230710_2155'),
    ]

    operations = [
        migrations.CreateModel(
            name='GameMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField()),
                ('year', models.IntegerField()),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gamemessages', to='dj4xol.Game')),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='dj4xol.Player')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ServerRace',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=16)),
                ('plural_name', models.CharField(max_length=16)),
                ('formal_name', models.CharField(max_length=32)),
                ('public', models.BooleanField(default=False)),
                ('description', models.TextField(default=None, null=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='serverraces', to='dj4xol.Game')),
                ('owner', models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='public_races', to='dj4xol.Player')),
                ('race_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dj4xol.ServerRaceType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RemoveField(
            model_name='playerrace',
            name='owner',
        ),
        migrations.RemoveField(
            model_name='playerrace',
            name='public',
        ),
        migrations.AddField(
            model_name='playerrace',
            name='formal_name',
            field=models.CharField(default=None, max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name='playerrace',
            name='plural_name',
            field=models.CharField(default=None, max_length=16, null=True),
        ),
    ]
