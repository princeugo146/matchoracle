from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Payment


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ['email', 'plan', 'is_active', 'is_staff', 'total_predictions', 'created_at']
    list_filter   = ['plan', 'is_active', 'is_staff', 'date_joined']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering      = ['-date_joined']
    fieldsets     = BaseUserAdmin.fieldsets + (
        ('MatchOracle', {
            'fields': (
                'plan', 'subscription_start', 'subscription_end',
                'api_key', 'referral_code',
                'total_predictions', 'correct_predictions',
                'predictions_today', 'predictions_date',
                'phone',
            )
        }),
    )
    readonly_fields = ['created_at', 'api_key', 'referral_code']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ['user', 'plan', 'amount', 'currency', 'status', 'created_at', 'verified_at']
    list_filter   = ['plan', 'status', 'currency']
    search_fields = ['user__email', 'reference']
    readonly_fields = ['created_at', 'verified_at']
    ordering      = ['-created_at']
