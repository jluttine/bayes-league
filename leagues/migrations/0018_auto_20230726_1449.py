# Generated by Django 3.2.19 on 2023-07-26 14:49

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0017_alter_stage_previous'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='league',
            name='bonus',
        ),
        migrations.RemoveField(
            model_name='stage',
            name='bonus',
        ),
    ]
