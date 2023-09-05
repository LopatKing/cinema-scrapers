# Generated by Django 4.2.5 on 2023-09-05 12:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cinemas', '0003_cinema_movie_showtimeseats'),
    ]

    operations = [
        migrations.AddField(
            model_name='showtimeseats',
            name='price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
            preserve_default=False,
        ),
    ]