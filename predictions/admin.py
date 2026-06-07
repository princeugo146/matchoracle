from django.contrib import admin
from .models import Prediction, TeamRanking, WeeklyTip, LiveMatch


admin.site.register(Prediction)
admin.site.register(TeamRanking)
admin.site.register(WeeklyTip)


@admin.register(LiveMatch)
class LiveMatchAdmin(admin.ModelAdmin):
    list_display = ('home_team', 'away_team', 'home_score', 'away_score',
                    'status', 'minute', 'competition', 'start_time')
    list_filter = ('status', 'competition')
    search_fields = ('home_team', 'away_team', 'competition')
    ordering = ('-start_time',)
