# Generated by Django 4.2.1 on 2023-09-12 07:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='delivered_on',
            field=models.DateField(blank=True, help_text='Date when the order was delivered.', null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_partner',
            field=models.CharField(blank=True, help_text="Delivery partner's name.", max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='invoice_number',
            field=models.CharField(help_text="Invoice number starting with 'M' and 8 digits.", max_length=8, null=True, unique=True),
        ),
    ]
