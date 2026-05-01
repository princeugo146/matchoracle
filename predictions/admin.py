from django.contrib import admin
from .models import Prediction, TeamRanking, WeeklyTip
admin.site.register(Prediction)
admin.site.register(TeamRanking)
admin.site.register(WeeklyTip)
