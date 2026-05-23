from django.db import models

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
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-match_date']
    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"
