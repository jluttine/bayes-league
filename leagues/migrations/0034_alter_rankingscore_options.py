# Generated by Django 4.2.7 on 2024-04-15 16:27

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0033_alter_rankingscore_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='rankingscore',
            options={'ordering': ['stage', '-score', 'player__name']},
        ),
    ]
