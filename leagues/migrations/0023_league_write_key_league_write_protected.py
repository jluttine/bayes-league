# Generated by Django 4.2.1 on 2023-08-04 15:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0022_alter_stage_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='league',
            name='write_key',
            field=models.CharField(default=None, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='league',
            name='write_protected',
            field=models.BooleanField(default=False),
        ),
    ]