from django.db import migrations, models


def rename_existing_retro_theme(apps, schema_editor):
    Account = apps.get_model('dj4xol', 'Account')
    Account.objects.filter(theme='retro').update(theme='haxxor')


def reverse_rename_existing_retro_theme(apps, schema_editor):
    Account = apps.get_model('dj4xol', 'Account')
    Account.objects.filter(theme='haxxor').update(theme='retro')


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0184_add_retro_theme_choice'),
    ]

    operations = [
        migrations.RunPython(rename_existing_retro_theme, reverse_rename_existing_retro_theme),
        migrations.AlterField(
            model_name='account',
            name='theme',
            field=models.CharField(
                choices=[
                    ('classic', 'Classic'),
                    ('lcars', 'LCARS'),
                    ('win95', 'Windows 95'),
                    ('haxxor', 'Haxxor'),
                    ('retro', 'Retro Arcade'),
                ],
                default='classic',
                max_length=20,
            ),
        ),
    ]
