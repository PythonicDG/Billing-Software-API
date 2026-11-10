import uuid
from django.db import models
from core.softdelete import SoftDeleteModel

class Customer(SoftDeleteModel):
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
        from django.db.models import Sum, F, Case, When, Value, DecimalField
        # Per-invoice dues are floored at 0 so an overpaid invoice can never
        # reduce what the customer owes on other invoices.
        due = F('grand_total') - F('amount_paid')
        res = self.invoices.aggregate(
            total=Sum(Case(
                When(grand_total__gt=F('amount_paid'), then=due),
                default=Value(0),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ))
        )
        val = res.get('total')
        return float(val) if val is not None else 0.0
