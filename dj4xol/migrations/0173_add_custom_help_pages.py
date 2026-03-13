from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0172_add_account_onboarding_step'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomHelpPage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True,
                                        serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=60, unique=True)),
                ('title', models.CharField(max_length=120)),
                ('tagline', models.CharField(blank=True, default='',
                                             max_length=120)),
                ('summary', models.CharField(blank=True, default='',
                                             max_length=255)),
                ('nav_order', models.IntegerField(default=100)),
                ('published', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['nav_order', 'title', 'id'],
            },
        ),
        migrations.CreateModel(
            name='CustomHelpPageBlock',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True,
                                        serialize=False, verbose_name='ID')),
                ('display_order', models.IntegerField(default=10)),
                ('heading', models.CharField(blank=True, default='',
                                             max_length=120)),
                ('body', models.TextField(blank=True, default='')),
                ('page', models.ForeignKey(
                    on_delete=models.CASCADE,
                    related_name='blocks',
                    to='dj4xol.CustomHelpPage',
                )),
            ],
            options={
                'ordering': ['display_order', 'id'],
            },
        ),
    ]
