from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_alter_invoice_payment_method_cash_upi_only'),
    ]

    operations = [
        migrations.RemoveField(model_name='invoice', name='tax_amount'),
        migrations.RemoveField(model_name='invoice', name='discount_amount'),
    ]
