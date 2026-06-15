from django.db import models

class CompanySettings(models.Model):
    name = models.CharField(max_length=255, default="Vighnaharta Fataka")
    address = models.TextField(default="Shop No. 1, Main Road")
    phone = models.CharField(max_length=50, default="9876543210")
    logo = models.ImageField(upload_to='company/', null=True, blank=True)
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    receipt_message = models.TextField(default="Thank you for your business!")
    dashboard_password = models.CharField(max_length=50, blank=True, null=True, help_text="Password to access the dashboard tab in the app")

    class Meta:
        verbose_name = "Company Settings"
        verbose_name_plural = "Company Settings"

    def __str__(self):
        return self.name

    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(id=1)
        return settings
