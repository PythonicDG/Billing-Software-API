from django.core.management.base import BaseCommand
from django.db.models import F

from billing.models import Invoice


class Command(BaseCommand):
    help = (
        "Clamp amount_paid to grand_total on overpaid invoices (change given back "
        "was stored as paid). Dry run by default; pass --apply to write."
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write the changes.')

    def handle(self, *args, **options):
        invoices = list(Invoice.objects.filter(amount_paid__gt=F('grand_total')))
        total = 0
        for inv in invoices:
            excess = inv.amount_paid - inv.grand_total
            total += excess
            self.stdout.write(f"{inv.invoice_number}: paid {inv.amount_paid} > total {inv.grand_total} (excess {excess})")
            if options['apply']:
                inv.save()  # Invoice.save() clamps amount_paid and refreshes payment_status
        verb = 'Fixed' if options['apply'] else 'Would fix'
        self.stdout.write(self.style.SUCCESS(f"{verb} {len(invoices)} invoice(s), excess total {total}"))
