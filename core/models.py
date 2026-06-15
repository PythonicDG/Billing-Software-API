import secrets
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from datetime import timedelta


class CompanySettings(models.Model):
    name = models.CharField(max_length=255, default="Vighnaharta Fataka")
    address = models.TextField(default="Shop No. 1, Main Road")
    phone = models.CharField(max_length=50, default="9876543210")
    logo = models.ImageField(upload_to='company/', null=True, blank=True)
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    receipt_message = models.TextField(default="Thank you for your business!")

    # Dashboard PIN protection (hashed, never plaintext)
    dashboard_pin_hash = models.CharField(
        max_length=256, blank=True, null=True,
        help_text="Hashed dashboard PIN. Never store raw PIN."
    )
    pin_failed_attempts = models.IntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)

    MAX_PIN_ATTEMPTS = 5
    PIN_LOCKOUT_MINUTES = 5

    class Meta:
        verbose_name = "Company Settings"
        verbose_name_plural = "Company Settings"

    def __str__(self):
        return self.name

    @classmethod
    def get_settings(cls):
        settings_obj, created = cls.objects.get_or_create(id=1)
        return settings_obj

    @property
    def has_pin(self):
        return bool(self.dashboard_pin_hash)

    @property
    def is_locked(self):
        if self.pin_locked_until and timezone.now() < self.pin_locked_until:
            return True
        return False

    @property
    def lockout_remaining_seconds(self):
        if self.is_locked:
            remaining = (self.pin_locked_until - timezone.now()).total_seconds()
            return max(0, int(remaining))
        return 0

    def set_pin(self, raw_pin):
        """Hash and store the PIN. Resets failed attempts."""
        self.dashboard_pin_hash = make_password(raw_pin)
        self.pin_failed_attempts = 0
        self.pin_locked_until = None
        self.save(update_fields=['dashboard_pin_hash', 'pin_failed_attempts', 'pin_locked_until'])

    def remove_pin(self):
        """Remove PIN protection entirely."""
        self.dashboard_pin_hash = None
        self.pin_failed_attempts = 0
        self.pin_locked_until = None
        self.save(update_fields=['dashboard_pin_hash', 'pin_failed_attempts', 'pin_locked_until'])

    def check_pin(self, raw_pin):
        """
        Verify PIN against stored hash.
        Returns (success: bool, error_message: str or None, attempts_remaining: int)
        """
        if not self.dashboard_pin_hash:
            return True, None, self.MAX_PIN_ATTEMPTS

        # Check lockout
        if self.is_locked:
            return False, f"Too many attempts. Try again in {self.lockout_remaining_seconds} seconds.", 0

        # Clear expired lockout
        if self.pin_locked_until and timezone.now() >= self.pin_locked_until:
            self.pin_failed_attempts = 0
            self.pin_locked_until = None
            self.save(update_fields=['pin_failed_attempts', 'pin_locked_until'])

        if check_password(raw_pin, self.dashboard_pin_hash):
            # Success — reset counters
            self.pin_failed_attempts = 0
            self.pin_locked_until = None
            self.save(update_fields=['pin_failed_attempts', 'pin_locked_until'])
            return True, None, self.MAX_PIN_ATTEMPTS
        else:
            # Failed — increment counter
            self.pin_failed_attempts += 1
            remaining = self.MAX_PIN_ATTEMPTS - self.pin_failed_attempts

            if self.pin_failed_attempts >= self.MAX_PIN_ATTEMPTS:
                self.pin_locked_until = timezone.now() + timedelta(minutes=self.PIN_LOCKOUT_MINUTES)
                self.save(update_fields=['pin_failed_attempts', 'pin_locked_until'])
                return False, f"Account locked for {self.PIN_LOCKOUT_MINUTES} minutes due to too many failed attempts.", 0

            self.save(update_fields=['pin_failed_attempts'])
            return False, "Incorrect PIN.", max(0, remaining)


class DashboardAccessToken(models.Model):
    """
    Temporary token issued after successful PIN verification.
    Required for all dashboard-related API calls.
    """
    TOKEN_EXPIRY_MINUTES = 15

    token = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dashboard_tokens'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Dashboard Access Token"
        verbose_name_plural = "Dashboard Access Tokens"

    def __str__(self):
        return f"DashboardToken({self.user.email}, expires={self.expires_at})"

    @property
    def is_valid(self):
        return self.is_active and timezone.now() < self.expires_at

    @classmethod
    def create_for_user(cls, user):
        """
        Create a new dashboard access token for the user.
        Invalidates any existing active tokens for this user.
        """
        # Deactivate old tokens
        cls.objects.filter(user=user, is_active=True).update(is_active=False)

        token = secrets.token_hex(32)
        expires_at = timezone.now() + timedelta(minutes=cls.TOKEN_EXPIRY_MINUTES)
        return cls.objects.create(
            token=token,
            user=user,
            expires_at=expires_at,
        )

    @classmethod
    def validate_token(cls, token_str):
        """
        Validate a dashboard access token.
        Returns (is_valid: bool, token_obj or None)
        """
        if not token_str:
            return False, None

        try:
            token_obj = cls.objects.get(token=token_str, is_active=True)
            if token_obj.is_valid:
                return True, token_obj
            else:
                # Token expired — deactivate it
                token_obj.is_active = False
                token_obj.save(update_fields=['is_active'])
                return False, None
        except cls.DoesNotExist:
            return False, None

    @classmethod
    def revoke_for_user(cls, user):
        """Revoke all active tokens for a user."""
        cls.objects.filter(user=user, is_active=True).update(is_active=False)

    @classmethod
    def cleanup_expired(cls):
        """Bulk cleanup of expired tokens (can be called via management command or cron)."""
        cls.objects.filter(expires_at__lt=timezone.now()).update(is_active=False)
