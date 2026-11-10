from rest_framework import serializers
from .models import Customer

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'name', 'phone', 'email', 'address', 'outstanding_balance', 'created_at', 'updated_at']

    def validate_phone(self, value):
        # Active duplicates are already rejected by the normal unique check;
        # this catches a soft-deleted customer that still owns the number.
        deleted = Customer.all_objects.filter(phone=value, is_deleted=True)
        if self.instance is not None:
            deleted = deleted.exclude(pk=self.instance.pk)
        if deleted.exists():
            raise serializers.ValidationError(
                'A deleted customer has this phone number. Restore it from the admin panel.')
        return value
