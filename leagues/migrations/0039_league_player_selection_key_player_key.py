# Generated by Django 4.2.12 on 2024-08-06 12:25

from django.db import migrations, models
import leagues.models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0038_league_dashboard_update_interval'),
    ]

    operations = [
        migrations.AddField(
            model_name='league',
            name='player_selection_key',
            field=models.CharField(default=leagues.models.create_key, max_length=50),
        ),
        migrations.AddField(
            model_name='player',
            name='key',
            field=models.CharField(default=leagues.models.create_key, max_length=50),
        ),
    ]
