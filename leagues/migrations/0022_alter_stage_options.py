# Generated by Django 4.2.1 on 2023-08-02 12:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0021_rename_previous_stage_included'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='stage',
            options={'ordering': [models.OrderBy(models.F('order'), descending=True, nulls_first=True)]},
        ),
    ]
