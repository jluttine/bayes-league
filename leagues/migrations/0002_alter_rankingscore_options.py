# Generated by Django 3.2.18 on 2023-05-11 07:09

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='rankingscore',
            options={'ordering': ['score']},
        ),
    ]
