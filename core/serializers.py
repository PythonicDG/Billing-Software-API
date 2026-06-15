from rest_framework import serializers
from .models import CompanySettings


class CompanySettingsSerializer(serializers.ModelSerializer):
    has_dashboard_pin = serializers.SerializerMethodField()

    class Meta:
        model = CompanySettings
        fields = [
            'id', 'name', 'address', 'phone', 'logo',
            'gst_number', 'receipt_message', 'has_dashboard_pin',
        ]
        # Explicitly exclude sensitive PIN fields
        read_only_fields = ['id', 'has_dashboard_pin']

    def get_has_dashboard_pin(self, obj):
        return obj.has_pin


class DashboardPinSetSerializer(serializers.Serializer):
    """Validates a 4–6 digit PIN for setting/updating."""
    pin = serializers.CharField(min_length=4, max_length=6)

    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits (0–9).")
        if len(value) < 4 or len(value) > 6:
            raise serializers.ValidationError("PIN must be 4–6 digits.")
        return value


class DashboardPinVerifySerializer(serializers.Serializer):
    """Validates a PIN input for verification."""
    pin = serializers.CharField(min_length=4, max_length=6)

    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits.")
        return value
