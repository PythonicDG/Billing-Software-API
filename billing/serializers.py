from rest_framework import serializers
from django.db import transaction, IntegrityError
from django.db.models import F
from products.models import Product
from customers.models import Customer
from .models import Invoice, InvoiceItem, Payment
from .units import pieces_per_unit


def customer_for_phone(phone, name):
    """Find (or create) the customer for a phone number, same as update_or_create.

    A soft-deleted customer still owns the phone number (it is unique in the DB),
    so billing that number again brings the customer back instead of failing.
    """
    customer, _ = Customer.all_objects.update_or_create(phone=phone, defaults={'name': name})
    if customer.is_deleted:
        customer.restore()
    return customer

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'invoice', 'amount', 'mode', 'payment_date', 'notes']
        read_only_fields = ['id', 'payment_date']

class InvoiceItemSerializer(serializers.ModelSerializer):
    # all_objects so an old bill that contains a since-deleted product can still be
    # edited; InvoiceSerializer.validate stops deleted products being added to bills.
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.all_objects.all(), allow_null=True, required=False)

    class Meta:
        model = InvoiceItem
        fields = ['id', 'product', 'unit', 'quantity', 'unit_price', 'total_price', 'product_name_snapshot', 'sku_snapshot', 'pieces_per_case']
        read_only_fields = ['total_price', 'product_name_snapshot', 'sku_snapshot', 'pieces_per_case']

    def validate(self, attrs):
        if attrs.get('quantity', 1) < 1:
            raise serializers.ValidationError({'quantity': 'Quantity must be positive.'})
        if 'unit_price' in attrs and attrs['unit_price'] <= 0:
            raise serializers.ValidationError({'unit_price': 'Unit price must be greater than zero.'})
        pieces_per_unit(attrs.get('product'), attrs.get('unit', 'PIECE'))
        return attrs

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.product:
            from products.serializers import ProductSerializer
            representation['product'] = ProductSerializer(instance.product).data
        return representation

class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True)
    customer_phone = serializers.CharField(write_only=True, required=False)
    customer_name = serializers.CharField(write_only=True, required=False)
    paid_amount = serializers.DecimalField(source='amount_paid', max_digits=12, decimal_places=2, required=False)

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'customer', 'customer_phone', 'customer_name',
            'sub_total', 'grand_total',
            'paid_amount', 'amount_paid', 'total_amount', 'due_amount', 'outstanding_balance',
            'payment_status', 'payment_method', 'items', 'created_by', 'created_at'
        ]
        read_only_fields = ['invoice_number', 'due_amount', 'outstanding_balance', 'payment_status', 'created_by', 'created_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Deleted products can't be sold, except ones already on the bill being edited.
        already_on_bill = set()
        if self.instance is not None:
            already_on_bill = {i.product_id for i in self.instance.items.all() if i.product_id}
        for item in attrs.get('items') or []:
            product = item.get('product')
            if product is not None and product.is_deleted and product.id not in already_on_bill:
                raise serializers.ValidationError(
                    {'items': [f"Product '{product.name}' has been deleted."]})
        return attrs

    def validate_paid_amount(self, value):
        if value < 0:
            raise serializers.ValidationError('Paid amount cannot be negative.')
        return value

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        customer_phone = validated_data.pop('customer_phone', None)
        customer_name = validated_data.pop('customer_name', "New Customer")
        customer = validated_data.get('customer')

        # Logic for creating/finding customer by phone
        if not customer and customer_phone:
            customer = customer_for_phone(customer_phone, customer_name)
            validated_data['customer'] = customer

        with transaction.atomic():
            # 1. First, validate stock for all products
            for item_data in items_data:
                product = item_data.get('product')
                quantity = item_data.get('quantity', 1)
                unit = item_data.get('unit', 'PIECE')
                
                # Calculate effective quantity in pieces
                effective_quantity = quantity * pieces_per_unit(product, unit)
                
                if product and product.stock_quantity < effective_quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for product '{product.name}'. Available: {product.stock_quantity}, Requested: {effective_quantity} pieces"
                    )

            # 2. Create the Invoice with retry logic for invoice_number collisions
            invoice = None
            for attempt in range(5):
                try:
                    with transaction.atomic(savepoint=True):
                        invoice = Invoice.objects.create(**validated_data)
                        break
                except IntegrityError as e:
                    if 'invoice_number' in str(e) and attempt < 4:
                        continue
                    raise e

            # 3. Create items and update stock
            for item_data in items_data:
                product = item_data.get('product')
                quantity = item_data.get('quantity', 1)
                unit = item_data.get('unit', 'PIECE')
                
                # Fetch unit price
                unit_price = item_data.get('unit_price')
                
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    unit=unit,
                    quantity=quantity,
                    unit_price=unit_price
                )

                # Deduct stock from Product
                if product:
                    effective_quantity = quantity * pieces_per_unit(product, unit)
                    Product.all_objects.filter(id=product.id).update(
                        stock_quantity=F('stock_quantity') - effective_quantity
                    )

            return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        customer_phone = validated_data.pop('customer_phone', None)
        customer_name = validated_data.pop('customer_name', None)
        
        # Logic for creating/finding customer by phone if updated
        if customer_phone:
            customer = customer_for_phone(customer_phone, customer_name or "Updated Customer")
            validated_data['customer'] = customer

        with transaction.atomic():
            # 1. Temporarily restore stock for ALL existing items to validate new state correctly
            old_items = list(instance.items.all())
            for item in old_items:
                if item.product:
                    effective_quantity = item.stock_quantity
                    Product.all_objects.filter(id=item.product.id).update(
                        stock_quantity=F('stock_quantity') + effective_quantity
                    )

            # 2. Validate stock for new items (after restoration)
            if items_data is not None:
                for item_data in items_data:
                    product = item_data.get('product')
                    quantity = item_data.get('quantity', 1)
                    unit = item_data.get('unit', 'PIECE')
                    
                    # Re-fetch product to get updated stock after restoration
                    if product:
                        product.refresh_from_db()
                        effective_quantity = quantity * pieces_per_unit(product, unit)
                        if product.stock_quantity < effective_quantity:
                             # ROLLBACK stock changes if validation fails
                             for item in old_items:
                                 if item.product:
                                     eff = item.stock_quantity
                                     Product.all_objects.filter(id=item.product.id).update(
                                         stock_quantity=F('stock_quantity') - eff
                                     )
                             raise serializers.ValidationError(
                                f"Insufficient stock for product '{product.name}'. Available: {product.stock_quantity}, Requested: {effective_quantity} pieces"
                             )

            # 3. Editing the paid amount replaces it, so earlier payment history
            # would no longer add up. Clear it to keep records consistent.
            if 'amount_paid' in validated_data:
                instance.payments.all().delete()

            # 3b. Update Invoice basic fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            # 4. If items were provided, replace them
            if items_data is not None:
                instance.items.all().delete()
                for item_data in items_data:
                    product = item_data.get('product')
                    quantity = item_data.get('quantity', 1)
                    unit = item_data.get('unit', 'PIECE')
                    unit_price = item_data.get('unit_price')
                    
                    InvoiceItem.objects.create(
                        invoice=instance,
                        product=product,
                        unit=unit,
                        quantity=quantity,
                        unit_price=unit_price
                    )

                    # Deduct stock for new items
                    if product:
                        effective_quantity = quantity * pieces_per_unit(product, unit)
                        Product.all_objects.filter(id=product.id).update(
                            stock_quantity=F('stock_quantity') - effective_quantity
                        )
            else:
                # If items weren't provided, we MUST re-deduct the original stock 
                # because we restored it at step 1 for validation purposes.
                for item in old_items:
                    if item.product:
                        eff = item.stock_quantity
                        Product.all_objects.filter(id=item.product.id).update(
                            stock_quantity=F('stock_quantity') - eff
                        )

            return instance

    def to_representation(self, instance):
        """Include the customer details in the output."""
        representation = super().to_representation(instance)
        if instance.customer:
            from customers.serializers import CustomerSerializer
            representation['customer_details'] = CustomerSerializer(instance.customer).data
        return representation
