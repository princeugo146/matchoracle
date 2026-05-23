from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Payment

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'plan', 'total_predictions', 'created_at']
    list_filter = ['plan']
    search_fields = ['email', 'first_name']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('MatchOracle', {'fields': ('plan', 'subscription_end', 'api_key', 'referral_code', 'total_predictions', 'predictions_today', 'predictions_date')}),
    )

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'amount', 'status', 'created_at']
