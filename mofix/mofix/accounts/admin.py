from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db.models import Sum, Count, Avg, Q
from django.urls import reverse, path
from django.shortcuts import render
from django.utils import timezone
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


# ─── Custom Admin Site with Dashboard ─────────────────────────────────────────

class MatchOracleAdminSite(admin.AdminSite):
    """
    Custom admin site that injects a rich dashboard into the index page.
    Registered models are inherited from the default admin site so we don't
    need to re-register anything.
    """
    site_header = 'MatchOracle Admin'
    site_title = 'MatchOracle Admin'
    index_title = 'Dashboard'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('dashboard/', self.admin_view(self.dashboard_view), name='mo_dashboard'),
        ]
        return custom + urls

    def dashboard_view(self, request):
        """Render the rich admin dashboard template."""
        from predictions.models import Prediction, WeeklyTip

        users_qs = User.objects.all()
        payments_qs = Payment.objects.all()
        predictions_qs = Prediction.objects.all()

        success_qs = payments_qs.filter(status='success')
        total_revenue = float(success_qs.aggregate(t=Sum('amount'))['t'] or 0)
        transaction_count = success_qs.count()
        total_users = users_qs.count()
        paid_users = users_qs.exclude(plan='free').count()
        free_users = total_users - paid_users
        total_predictions = predictions_qs.count()
        total_tips = WeeklyTip.objects.count()
        pro_tips = WeeklyTip.objects.filter(is_pro_only=True).count()
        free_tips_count = total_tips - pro_tips

        # Accuracy
        correct = predictions_qs.filter(was_correct=True).count()
        incorrect = predictions_qs.filter(was_correct=False).count()
        overall_accuracy = round(correct / max(correct + incorrect, 1) * 100, 1)

        # Last 7 days
        seven_days_ago = timezone.now() - timedelta(days=7)
        new_users_week = users_qs.filter(date_joined__gte=seven_days_ago).count()
        new_payments_week = success_qs.filter(created_at__gte=seven_days_ago).count()
        revenue_week = float(
            success_qs.filter(created_at__gte=seven_days_ago)
            .aggregate(t=Sum('amount'))['t'] or 0
        )
        conversion_rate = round(paid_users / max(total_users, 1) * 100, 1)

        plan_breakdown = list(
            success_qs.values('plan')
            .annotate(revenue=Sum('amount'), count=Count('id'))
            .order_by('-revenue')
        )

        recent_payments = payments_qs.select_related('user').order_by('-created_at')[:10]
        recent_signups = users_qs.order_by('-date_joined')[:10]

        context = {
            **self.each_context(request),
            'title': 'MatchOracle Dashboard',
            'total_users': total_users,
            'paid_users': paid_users,
            'free_users': free_users,
            'total_revenue_display': f'NGN {total_revenue:,.0f}',
            'transaction_count': transaction_count,
            'total_predictions': total_predictions,
            'overall_accuracy': overall_accuracy,
            'total_tips': total_tips,
            'pro_tips': pro_tips,
            'free_tips': free_tips_count,
            'new_users_week': new_users_week,
            'new_payments_week': new_payments_week,
            'revenue_week_display': f'NGN {revenue_week:,.0f}',
            'conversion_rate': conversion_rate,
            'plan_breakdown': plan_breakdown,
            'recent_payments': recent_payments,
            'recent_signups': recent_signups,
        }
        return render(request, 'admin/admin_dashboard.html', context)

    def index(self, request, extra_context=None):
        """Override index to inject dashboard stats into the default admin index."""
        from predictions.models import Prediction, WeeklyTip

        extra_context = extra_context or {}
        users_qs = User.objects.all()
        success_qs = Payment.objects.filter(status='success')

        total_revenue = float(success_qs.aggregate(t=Sum('amount'))['t'] or 0)
        total_users = users_qs.count()
        paid_users = users_qs.exclude(plan='free').count()
        total_predictions = Prediction.objects.count()
        total_tips = WeeklyTip.objects.count()

        seven_days_ago = timezone.now() - timedelta(days=7)
        new_users_week = users_qs.filter(date_joined__gte=seven_days_ago).count()
        revenue_week = float(
            success_qs.filter(created_at__gte=seven_days_ago)
            .aggregate(t=Sum('amount'))['t'] or 0
        )

        extra_context.update({
            'mo_total_users': total_users,
            'mo_paid_users': paid_users,
            'mo_total_revenue': f'NGN {total_revenue:,.0f}',
            'mo_total_predictions': total_predictions,
            'mo_total_tips': total_tips,
            'mo_new_users_week': new_users_week,
            'mo_revenue_week': f'NGN {revenue_week:,.0f}',
            'mo_dashboard_url': '/admin/dashboard/',
        })
        return super().index(request, extra_context=extra_context)

