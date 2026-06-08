import uuid
from django.db import models
from django.conf import settings
from products.models import Product
from customers.models import Customer
from django.utils import timezone

class Invoice(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partially Paid'),
        ('PAID', 'Paid'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('ONLINE', 'Online'),
        ('CREDIT', 'Credit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    
    # Pricing Summary
    sub_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Payment info
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    
    # Metadata
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Simple unique invoice number generation: INV-20231027-001
            today = timezone.now().strftime('%Y%m%d')
            count = Invoice.objects.filter(created_at__date=timezone.now().date()).count() + 1
            self.invoice_number = f"INV-{today}-{count:04d}"
        
        # Calculate payment status
        if self.paid_amount >= self.grand_total:
            self.payment_status = 'PAID'
        elif self.paid_amount > 0:
            self.payment_status = 'PARTIAL'
        else:
            self.payment_status = 'PENDING'

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name if self.customer else 'Guest'}"

    @property
    def due_amount(self):
        """Returns the remaining amount to be paid."""
        return max(0, self.grand_total - self.paid_amount)

class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    
    # Snapshot of product details at time of sale
    product_name_snapshot = models.CharField(max_length=255)
    sku_snapshot = models.CharField(max_length=50)
    
    UNIT_CHOICES = [
        ('PIECE', 'Piece'),
        ('CENT', 'Cent'),
    ]

    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='PIECE')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        if self.product:
            brand_str = f" ({self.product.brand})" if self.product.brand else ""
            self.product_name_snapshot = f"{self.product.name}{brand_str}"
            self.sku_snapshot = self.product.sku or ""
        
        # Calculate total price for this item
        # If 'CENT' is selected, 1 unit means 10 pieces.
        # But wait, usually the user provides the unit_price specifically for that unit.
        # If the user says "1 cent means 10 piece", we should decide if the unit_price
        # is always per piece or if it's per the unit the user picked.
        # Usually, in a POS, the price changes based on unit.
        # Let's assume the user provides the price for the SELECTED unit.
        
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name_snapshot} ({self.quantity} {self.get_unit_display()}) - {self.invoice.invoice_number}"
