from django.contrib import admin
from .models import Prediction, TeamRanking, WeeklyTip, MatchResult


admin.site.register(Prediction)
admin.site.register(TeamRanking)
admin.site.register(WeeklyTip)


@admin.register(MatchResult)
class MatchResultAdmin(admin.ModelAdmin):
    list_display = [
        'home_team', 'away_team', 'home_score', 'away_score',
        'match_date', 'competition', 'result', 'processed',
    ]
    list_filter = ['competition', 'match_type', 'processed', 'match_date']
    search_fields = ['home_team', 'away_team']
    fieldsets = (
        ('Match Info', {
            'fields': (
                'home_team', 'away_team', 'home_score', 'away_score',
                'match_date', 'competition', 'match_type',
            ),
        }),
        ('Team Statistics', {
            'fields': (
                'home_possession', 'away_possession',
                'home_shots', 'away_shots',
            ),
        }),
        ('Tactical Analysis', {
            'fields': (
                'home_tactical_style', 'away_tactical_style',
                'home_key_player', 'away_key_player',
            ),
        }),
        ('Match Analysis', {
            'fields': ('match_summary', 'what_decided_match'),
        }),
        ('Auto Fields', {
            'fields': ('result', 'processed'),
            'classes': ('collapse',),
        }),
    )
    readonly_fields = ['result', 'processed']
