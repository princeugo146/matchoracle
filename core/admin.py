from django.contrib import admin
from .models import WeeklyForecast, SiteAnalytics
admin.site.register(WeeklyForecast)
admin.site.register(SiteAnalytics)
