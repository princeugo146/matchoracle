import uuid
import secrets
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta

class User(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    plan = models.CharField(max_length=20, default='free',
        choices=[('free','Free'),('basic','Basic'),('pro','Pro')])
    trial_count = models.IntegerField(default=0)
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    api_key = models.CharField(max_length=64, unique=True, blank=True)
    predictions_today = models.IntegerField(default=0)
    predictions_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = self.generate_api_key()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_api_key():
        return 'mo_' + secrets.token_urlsafe(40)

    @property
    def is_subscription_active(self):
        if self.plan == 'free':
            return self.trial_count < 6
        if self.subscription_end:
            return timezone.now() < self.subscription_end
        return False

    @property
    def can_predict(self):
        today = timezone.now().date()
        if self.predictions_date != today:
            return True
        from django.conf import settings
        limit = settings.MATCHORACLE['PLANS'][self.plan]['predictions_per_day']
        return self.predictions_today < limit

    @property
    def days_remaining(self):
        if self.plan == 'free':
            return max(0, 6 - self.trial_count)
        if self.subscription_end:
            delta = self.subscription_end - timezone.now()
            return max(0, delta.days)
        return 0

    def __str__(self):
        return self.email


class Payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    plan = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=5, default='NGN')
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, default='pending',
        choices=[('pending','Pending'),('success','Success'),('failed','Failed')])
    paystack_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} — {self.plan} — {self.status}"
