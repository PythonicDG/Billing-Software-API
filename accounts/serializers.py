from django.contrib.auth import authenticate
from rest_framework import serializers
from .models import User


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['username'], password=data['password'])
        if user is None:
            raise serializers.ValidationError("Invalid username or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        data['user'] = user
        return data


class CreateStaffSerializer(serializers.ModelSerializer):
    """
    Used by Owner to create a new Staff/Viewer account.
    Accepts: username, email, password, role (optional, defaults to STAFF).
    """
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role']
        extra_kwargs = {
            'role': {'required': False},
        }

    def validate_role(self, value):
        """Owner should only create STAFF or VIEWER accounts, not another OWNER."""
        if value == User.OWNER:
            raise serializers.ValidationError("Cannot create another Owner account.")
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class StaffListSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for listing staff accounts.
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'is_active']


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
