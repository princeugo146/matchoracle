from django.db import models
from accounts.models import User

class Prediction(models.Model):
    ENGINE_CHOICES = [('A','Match'),('B','Player'),('C','Ranking'),('D','Simulation'),('NL','AI')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='predictions')
    engine = models.CharField(max_length=2, choices=ENGINE_CHOICES)
    input_data = models.JSONField(default=dict)
    output_data = models.JSONField(default=dict)
    confidence = models.IntegerField(default=0)
    home_team = models.CharField(max_length=100, blank=True)
    away_team = models.CharField(max_length=100, blank=True)
    predicted_result = models.CharField(max_length=50, blank=True)
    was_correct = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']

class TeamRanking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rankings')
    name = models.CharField(max_length=100)
    power_elo = models.IntegerField(default=1000)
    wins = models.IntegerField(default=0)
    draws = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    goals_for = models.IntegerField(default=0)
    goals_against = models.IntegerField(default=0)
    class Meta:
        ordering = ['-power_elo']
        unique_together = ['user', 'name']

class WeeklyTip(models.Model):
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    competition = models.CharField(max_length=100)
    match_date = models.DateTimeField()
    tip = models.CharField(max_length=200)
    confidence = models.IntegerField(default=70)
    is_pro_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-match_date']


class PredictionResult(models.Model):
    """
    Tracks the outcome of a prediction for analytics and accuracy metrics.
    Can be linked to a Prediction or stored independently for aggregate stats.
    """
    # Match details
    home_team = models.CharField(max_length=100, blank=True, db_index=True)
    away_team = models.CharField(max_length=100, blank=True, db_index=True)
    match_date = models.DateField(null=True, blank=True)

    # What was predicted
    predicted_verdict = models.CharField(max_length=100, blank=True)
    predicted_score = models.CharField(max_length=20, blank=True)
    confidence_level = models.IntegerField(default=0)

    # Per-engine verdicts for comparison
    engine_a_verdict = models.CharField(max_length=100, blank=True)
    engine_d_verdict = models.CharField(max_length=100, blank=True)
    smart_ai_verdict = models.CharField(max_length=100, blank=True)

    # Actual outcome (filled in after the match)
    actual_result = models.CharField(max_length=100, blank=True)
    actual_score = models.CharField(max_length=20, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)

    # Optional link back to the originating Prediction row
    prediction = models.OneToOneField(
        Prediction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='analytics_result',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['home_team', 'away_team']),
        ]

    def __str__(self):
        status = 'correct' if self.is_correct else ('wrong' if self.is_correct is False else 'pending')
        return f"PredictionResult({self.home_team} vs {self.away_team}, {status})"
