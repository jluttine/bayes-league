# Generated by Django 4.2.7 on 2024-04-16 18:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0034_alter_rankingscore_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='league',
            name='slug',
            field=models.SlugField(max_length=100, unique=True),
        ),
    ]
