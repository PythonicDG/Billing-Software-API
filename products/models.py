import uuid
import random
import string
from django.db import models


def generate_unique_sku():
    """Generates a professional 6-character SKU code."""
    length = 6
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        sku = f"FTK-{code}"
        if not Product.objects.filter(sku=sku).exists():
            return sku


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='products'
    )
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Standard, Kaliswari")
    
    sku = models.CharField(
        max_length=50, 
        unique=True, 
        blank=True, 
        null=True,
        help_text="Unique Product Code (leave blank to auto-generate)"
    )
    
    # Pricing
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Current Sales Price")
    mrp = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, help_text="Maximum Retail Price")
    
    # Inventory
    stock_quantity = models.IntegerField(default=0)
    min_stock_level = models.IntegerField(default=5, help_text="Alert when stock falls below this number")
    
    # Status
    image = models.ImageField(upload_to='products/', blank=True, null=True, help_text="Product photo (optional)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Auto-generate SKU if it's not provided."""
        if not self.sku:
            self.sku = generate_unique_sku()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.brand or 'No Brand'})"

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.min_stock_level
