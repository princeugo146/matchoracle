from django.db import models
from django.utils import timezone


class WeeklyForecast(models.Model):
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    match_date = models.DateTimeField()
    competition = models.CharField(max_length=100, default='Premier League')
    home_win_pct = models.FloatField(default=0)
    draw_pct = models.FloatField(default=0)
    away_win_pct = models.FloatField(default=0)
    predicted_score = models.CharField(max_length=10, default='1-1')
    confidence = models.IntegerField(default=70)
    ai_insight = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)
    result = models.CharField(max_length=20, blank=True, help_text='Actual result e.g. 2-1')
    was_correct = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-match_date']

    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"


class SiteAnalytics(models.Model):
    date = models.DateField(unique=True)
    total_predictions = models.IntegerField(default=0)
    total_users = models.IntegerField(default=0)
    active_subscriptions = models.IntegerField(default=0)
    revenue_ngn = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return str(self.date)


class Notification(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — {self.title}"
