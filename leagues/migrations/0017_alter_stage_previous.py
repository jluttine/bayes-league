# Generated by Django 3.2.19 on 2023-07-26 10:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0016_alter_stage_previous'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stage',
            name='previous',
            field=models.ManyToManyField(blank=True, to='leagues.Stage'),
        ),
    ]