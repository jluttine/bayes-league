# Generated by Django 4.2.7 on 2024-03-23 19:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0028_match_away_team_match_home_team'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='rankingscore',
            options={'ordering': ['-score', 'player__name']},
        ),
        migrations.AddField(
            model_name='league',
            name='regularisation',
            field=models.FloatField(default=0),
        ),
        migrations.AddConstraint(
            model_name='league',
            constraint=models.CheckConstraint(check=models.Q(('regularisation__gte', 0)), name='regularisation_gte_0'),
        ),
    ]
