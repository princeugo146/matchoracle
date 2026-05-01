from django.contrib import admin
from .models import WeeklyForecast, SiteAnalytics, Notification
admin.site.register(WeeklyForecast)
admin.site.register(SiteAnalytics)
admin.site.register(Notification)
