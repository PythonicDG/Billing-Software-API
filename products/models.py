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
    no_of_case = models.IntegerField(default=0)
    cent_in_per_cs = models.IntegerField(default=0)
    
    # Status
    image = models.ImageField(upload_to='products/', blank=True, null=True, help_text="Product photo (optional)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Auto-generate SKU if it's not provided. Only recalculate stock when case/cent fields change."""
        if not self.sku:
            self.sku = generate_unique_sku()
        
        # Only recalculate stock_quantity for brand new products (no PK yet).
        # For updates, preserve the current stock_quantity (which may have been 
        # reduced by invoice sales) UNLESS no_of_case or cent_in_per_cs changed.
        if not self.pk:
            # New product: calculate initial stock
            self.stock_quantity = (self.no_of_case or 0) * (self.cent_in_per_cs or 0) * 10
        else:
            # Existing product: recalculate if stock-related fields changed
            # OR if it's currently out of stock (enables "Update" to act as a restock)
            try:
                old = Product.objects.get(pk=self.pk)
                if (old.no_of_case != self.no_of_case or 
                    old.cent_in_per_cs != self.cent_in_per_cs or 
                    (old.stock_quantity <= 0 and self.no_of_case > 0)):
                    self.stock_quantity = (self.no_of_case or 0) * (self.cent_in_per_cs or 0) * 10
                # else: preserve the current stock_quantity as-is
            except Product.DoesNotExist:
                self.stock_quantity = (self.no_of_case or 0) * (self.cent_in_per_cs or 0) * 10
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.brand or 'No Brand'})"

    @property
    def is_low_stock(self):
        return self.total_stock_in_cent <= self.min_stock_level

    @property
    def total_stock_in_cent(self):
        return self.stock_quantity / 10
