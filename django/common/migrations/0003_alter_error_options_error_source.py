# Generated by Django 4.2.5 on 2023-09-07 09:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0002_error'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='error',
            options={'ordering': ['-created_on']},
        ),
        migrations.AddField(
            model_name='error',
            name='source',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
