# Generated by Django 4.2.7 on 2024-03-24 19:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0031_alter_league_regularisation'),
    ]

    operations = [
        migrations.AddField(
            model_name='league',
            name='points_to_win',
            field=models.PositiveIntegerField(default=21),
        ),
        migrations.AddField(
            model_name='stage',
            name='points_to_win',
            field=models.PositiveIntegerField(blank=True, default=None, null=True),
        ),
    ]