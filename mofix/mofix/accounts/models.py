import secrets
import string
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def gen_api_key():
    return 'mo_' + secrets.token_urlsafe(32)


def gen_ref_code():
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


class User(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    plan = models.CharField(max_length=20, default='free')
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    api_key = models.CharField(max_length=64, unique=True, blank=True, default='')
    predictions_today = models.IntegerField(default=0)
    predictions_date = models.DateField(null=True, blank=True)
    referral_code = models.CharField(max_length=10, blank=True, default='')
    total_predictions = models.IntegerField(default=0)
    correct_predictions = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        if not self.api_key:
            self.api_key = gen_api_key()
        if not self.referral_code:
            self.referral_code = gen_ref_code()
        super().save(*args, **kwargs)

    @property
    def is_subscription_active(self):
        if self.plan == 'free':
            return True
        if self.subscription_end:
            return timezone.now() < self.subscription_end
        return False

    @property
    def can_predict(self):
        from django.conf import settings
        today = timezone.now().date()
        # Reset counter if new day
        if self.predictions_date != today:
            return True
        limit = settings.MATCHORACLE['PLANS'].get(self.plan, {}).get('predictions_per_day', 3)
        return self.predictions_today < limit

    @property
    def predictions_left_today(self):
        from django.conf import settings
        today = timezone.now().date()
        limit = settings.MATCHORACLE['PLANS'].get(self.plan, {}).get('predictions_per_day', 3)
        if self.predictions_date != today:
            return limit
        return max(0, limit - self.predictions_today)

    @property
    def days_remaining(self):
        if self.plan == 'free':
            return 999
        if self.subscription_end:
            return max(0, (self.subscription_end - timezone.now()).days)
        return 0

    @property
    def accuracy_rate(self):
        if not self.total_predictions:
            return 0
        return round(self.correct_predictions / self.total_predictions * 100, 1)

    def __str__(self):
        return self.email


class Payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    plan = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=5, default='NGN')
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} - {self.plan} - {self.status}"


class RevenueDashboard(Payment):
    """
    Proxy model that surfaces a read-only revenue dashboard in the Django admin.
    No extra database table is created — it reuses the Payment table.
    """
    class Meta:
        proxy = True
        verbose_name = 'Revenue Dashboard'
        verbose_name_plural = 'Revenue Dashboard'
