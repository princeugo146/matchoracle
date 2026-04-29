from django.db import models
from django.utils import timezone

class WeeklyForecast(models.Model):
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    match_date = models.DateTimeField()
    competition = models.CharField(max_length=100)
    home_win_pct = models.FloatField()
    draw_pct = models.FloatField()
    away_win_pct = models.FloatField()
    predicted_score = models.CharField(max_length=10)
    confidence = models.IntegerField()
    ai_insight = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ['match_date']

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} — {self.match_date.date()}"


class SiteAnalytics(models.Model):
    date = models.DateField(unique=True)
    total_predictions = models.IntegerField(default=0)
    total_users = models.IntegerField(default=0)
    active_subscriptions = models.IntegerField(default=0)
    revenue_ngn = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['-date']
