# Generated by Django 4.0.4 on 2022-05-18 23:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_ledger', '0012_billmodel_django_ledg_terms_752251_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaseordermodel',
            name='po_status',
            field=models.CharField(choices=[('draft', 'Draft'), ('in_review', 'In Review'), ('approved', 'Approved'), ('canceled', 'Canceled'), ('void', 'Void'), ('fulfilled', 'Fulfilled')], default='draft', max_length=10),
        ),
    ]