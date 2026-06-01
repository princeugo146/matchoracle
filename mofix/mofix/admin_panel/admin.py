from django.contrib import admin
from predictions.models import WeeklyTip
from .models import AdminLog


# ─── WeeklyTip ────────────────────────────────────────────────────────────────
# WeeklyTip is registered here (predictions/admin.py uses plain admin.site.register
# without a custom class, so we unregister it first and re-register with richer config).

try:
    admin.site.unregister(WeeklyTip)
except admin.sites.NotRegistered:
    pass


@admin.register(WeeklyTip)
class WeeklyTipAdmin(admin.ModelAdmin):
    list_display  = ['home_team', 'away_team', 'competition', 'tip', 'confidence', 'is_pro_only', 'match_date', 'created_at']
    list_filter   = ['is_pro_only', 'competition', 'match_date']
    search_fields = ['home_team', 'away_team', 'tip', 'competition']
    ordering      = ['-match_date']
    list_editable = ['confidence', 'is_pro_only']


# ─── AdminLog ─────────────────────────────────────────────────────────────────

@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display  = ['created_at', 'admin_user', 'action', 'object_type', 'description']
    list_filter   = ['action', 'object_type', 'created_at']
    search_fields = ['admin_user__email', 'description', 'object_type']
    readonly_fields = [
        'admin_user', 'action', 'description',
        'object_type', 'object_id', 'ip_address', 'created_at',
    ]
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
