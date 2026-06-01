from django.contrib import admin
from django.db.models import Sum, Count, Avg
from django.utils.html import format_html
from .models import WeeklyForecast


@admin.register(WeeklyForecast)
class WeeklyForecastAdmin(admin.ModelAdmin):
    list_display = [
        'home_team', 'away_team', 'competition', 'match_date',
        'predicted_score', 'confidence', 'is_published', 'created_at',
    ]
    list_filter = ['is_published', 'competition']
    search_fields = ['home_team', 'away_team', 'competition']
    ordering = ['-match_date']
    list_editable = ['is_published']
    readonly_fields = ['created_at']
    fieldsets = (
        ('Match Info', {
            'fields': ('home_team', 'away_team', 'competition', 'match_date'),
        }),
        ('Prediction', {
            'fields': (
                'home_win_pct', 'draw_pct', 'away_win_pct',
                'predicted_score', 'confidence', 'ai_insight',
            ),
        }),
        ('Publishing', {
            'fields': ('is_published', 'created_at'),
        }),
    )

