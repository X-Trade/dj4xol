from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dj4xol', '0148_add_diplomatic_contract_offer_condition_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='diplomaticcontract',
            name='offer_star',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='+', to='dj4xol.Star'),
        ),
        migrations.AddField(
            model_name='diplomaticcontract',
            name='request_star',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='+', to='dj4xol.Star'),
        ),
    ]
