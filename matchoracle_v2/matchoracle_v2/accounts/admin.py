from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Payment

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['email', 'plan', 'trial_count', 'subscription_end', 'total_predictions', 'created_at']
    list_filter = ['plan']
    search_fields = ['email', 'first_name']
    fieldsets = UserAdmin.fieldsets + (
        ('MatchOracle', {'fields': ('plan', 'trial_count', 'subscription_start', 'subscription_end', 'api_key', 'phone', 'referral_code', 'referral_bonus_days', 'total_predictions', 'correct_predictions')}),
    )

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'amount', 'status', 'created_at']
    list_filter = ['status', 'plan']
