from django.contrib import admin
from .models import WeeklyTipAdmin, AdminLog


@admin.register(WeeklyTipAdmin)
class WeeklyTipAdminAdmin(admin.ModelAdmin):
    list_display = ['title', 'home_team', 'away_team', 'competition', 'match_date', 'confidence', 'is_published', 'result']
    list_filter = ['is_published', 'is_pro_only', 'result', 'competition']
    search_fields = ['title', 'home_team', 'away_team', 'tip']
    ordering = ['-match_date']


@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = ['admin', 'action', 'model_name', 'object_repr', 'ip_address', 'created_at']
    list_filter = ['action', 'model_name']
    search_fields = ['admin__email', 'object_repr', 'details']
    readonly_fields = ['admin', 'action', 'model_name', 'object_id', 'object_repr', 'details', 'ip_address', 'created_at']
    ordering = ['-created_at']
