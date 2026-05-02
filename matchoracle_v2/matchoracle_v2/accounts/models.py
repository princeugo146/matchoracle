import secrets
import string
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def generate_api_key():
    return 'mo_' + secrets.token_urlsafe(40)


def generate_referral_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))


class User(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.CharField(max_length=10, default='⚽')
    plan = models.CharField(max_length=20, default='free',
        choices=[('free', 'Free'), ('basic', 'Basic'), ('pro', 'Pro')])
    trial_count = models.IntegerField(default=0)
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    api_key = models.CharField(max_length=64, unique=True, blank=True, default='')
    predictions_today = models.IntegerField(default=0)
    predictions_date = models.DateField(null=True, blank=True)
    favourite_teams = models.JSONField(default=list, blank=True)
    referral_code = models.CharField(max_length=10, blank=True, default='')
    referred_by = models.ForeignKey('self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='referrals')
    referral_bonus_days = models.IntegerField(default=0)
    total_predictions = models.IntegerField(default=0)
    correct_predictions = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = generate_api_key()
        if not self.referral_code:
            self.referral_code = generate_referral_code()
        if not self.username:
            self.username = self.email
        # Ensure referral_code is unique
        if self.referral_code:
            while User.objects.filter(
                referral_code=self.referral_code
            ).exclude(pk=self.pk).exists():
                self.referral_code = generate_referral_code()
        super().save(*args, **kwargs)

    @property
    def is_subscription_active(self):
        if self.plan == 'free':
            return self.trial_count < 6
        if self.subscription_end:
            return timezone.now() < self.subscription_end
        return False

    @property
    def can_predict(self):
        from django.conf import settings
        today = timezone.now().date()
        if self.predictions_date != today:
            return True
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

    @property
    def accuracy_rate(self):
        if self.total_predictions == 0:
            return 0
        return round((self.correct_predictions / self.total_predictions) * 100, 1)

    @property
    def referral_count(self):
        return self.referrals.count()

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
