from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('billing', '0004_alter_invoice_payment_method')]

    operations = [
        migrations.AlterField(
            model_name='invoiceitem', name='unit',
            field=models.CharField(max_length=10, default='PIECE',
                choices=[('PIECE', 'Piece'), ('CENT', 'Cent'), ('CASE', 'Case')]),
        ),
        migrations.AddField(
            model_name='invoiceitem', name='pieces_per_case',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
