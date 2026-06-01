from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db.models import Sum, Count, Avg
from django.urls import reverse
from .models import User, Payment, RevenueDashboard


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'email', 'username', 'first_name', 'plan', 'is_active',
        'total_predictions', 'total_spent_display', 'date_joined',
    ]
    list_filter = ['plan', 'is_active', 'is_staff']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering = ['-date_joined']
    readonly_fields = ['date_joined', 'created_at', 'api_key', 'referral_code', 'total_spent_display']
    actions = ['deactivate_users', 'activate_users', 'reset_to_free_plan']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('MatchOracle Subscription', {
            'fields': (
                'plan', 'subscription_start', 'subscription_end',
                'api_key', 'referral_code',
            ),
        }),
        ('Usage Stats', {
            'fields': (
                'total_predictions', 'correct_predictions',
                'predictions_today', 'predictions_date',
                'total_spent_display',
            ),
        }),
        ('Contact', {
            'fields': ('phone',),
        }),
    )

    def total_spent_display(self, obj):
        total = obj.payments.filter(status='success').aggregate(t=Sum('amount'))['t'] or 0
        return f'NGN {total:,.0f}'
    total_spent_display.short_description = 'Total Spent'

    @admin.action(description='Deactivate selected users')
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} user(s) deactivated.')

    @admin.action(description='Activate selected users')
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} user(s) activated.')

    @admin.action(description='Reset selected users to Free plan')
    def reset_to_free_plan(self, request, queryset):
        updated = queryset.update(plan='free', subscription_start=None, subscription_end=None)
        self.message_user(request, f'{updated} user(s) reset to Free plan.')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'amount_display', 'currency', 'status', 'created_at', 'verified_at']
    list_filter = ['status', 'plan', 'currency']
    search_fields = ['user__email', 'reference']
    ordering = ['-created_at']
    readonly_fields = ['reference', 'created_at', 'verified_at']

    def amount_display(self, obj):
        return f'{obj.currency} {obj.amount:,.0f}'
    amount_display.short_description = 'Amount'


@admin.register(RevenueDashboard)
class RevenueDashboardAdmin(admin.ModelAdmin):
    """
    Read-only admin view that shows aggregated revenue stats at the top
    of the change list, followed by the full transaction log.
    """
    change_list_template = 'admin/revenue_dashboard.html'
    list_display = ['user', 'plan', 'amount_display', 'status', 'created_at']
    list_filter = ['status', 'plan']
    search_fields = ['user__email']
    ordering = ['-created_at']
    readonly_fields = ['user', 'plan', 'amount', 'currency', 'reference', 'status', 'created_at', 'verified_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def amount_display(self, obj):
        return f'{obj.currency} {obj.amount:,.0f}'
    amount_display.short_description = 'Amount'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = Payment.objects.filter(status='success')
        stats = qs.aggregate(
            total_revenue=Sum('amount'),
            transaction_count=Count('id'),
        )
        total_revenue = stats['total_revenue'] or 0
        transaction_count = stats['transaction_count'] or 0
        total_users = User.objects.count()
        avg_user_value = round(total_revenue / total_users, 2) if total_users else 0

        plan_breakdown = (
            qs.values('plan')
            .annotate(revenue=Sum('amount'), count=Count('id'))
            .order_by('-revenue')
        )

        extra_context.update({
            'total_revenue': f'NGN {total_revenue:,.0f}',
            'transaction_count': transaction_count,
            'total_users': total_users,
            'avg_user_value': f'NGN {avg_user_value:,.2f}',
            'plan_breakdown': plan_breakdown,
        })
        return super().changelist_view(request, extra_context=extra_context)

