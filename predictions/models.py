from django.db import models
from accounts.models import User


class Prediction(models.Model):
    ENGINE_CHOICES = [
        ('A', 'Match Prediction'),
        ('B', 'Player Rating'),
        ('C', 'Team Ranking'),
        ('D', 'Match Simulation'),
        ('NL', 'Natural Language'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='predictions')
    engine = models.CharField(max_length=2, choices=ENGINE_CHOICES)
    input_data = models.JSONField()
    output_data = models.JSONField()
    confidence = models.IntegerField(default=0)
    home_team = models.CharField(max_length=100, blank=True)
    away_team = models.CharField(max_length=100, blank=True)
    predicted_result = models.CharField(max_length=50, blank=True)
    actual_result = models.CharField(max_length=50, blank=True)
    was_correct = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — Engine {self.engine} — {self.created_at.date()}"


class TeamRanking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rankings')
    name = models.CharField(max_length=100)
    power_elo = models.IntegerField(default=1000)
    wins = models.IntegerField(default=0)
    draws = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    goals_for = models.IntegerField(default=0)
    goals_against = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-power_elo']
        unique_together = ['user', 'name']

    @property
    def goal_diff(self):
        return self.goals_for - self.goals_against

    def __str__(self):
        return f"{self.user.email} — {self.name} ({self.power_elo})"


class WeeklyTip(models.Model):
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    competition = models.CharField(max_length=100)
    match_date = models.DateTimeField()
    tip = models.CharField(max_length=200)
    odds = models.CharField(max_length=20, blank=True)
    confidence = models.IntegerField(default=70)
    is_pro_only = models.BooleanField(default=False)
    result = models.CharField(max_length=50, blank=True)
    was_correct = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-match_date']

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} — {self.tip}"
