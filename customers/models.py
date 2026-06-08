import uuid
from django.db import models

class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15, unique=True, db_index=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @property
    def outstanding_balance(self):
        from django.db.models import Sum, F
        res = self.invoices.aggregate(
            total=Sum(F('grand_total') - F('amount_paid'))
        )
        val = res.get('total')
        return float(val) if val is not None else 0.0
