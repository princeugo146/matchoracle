from django.db import models
from accounts.models import User

class Prediction(models.Model):
    ENGINE_CHOICES = [('A','Match Prediction'),('B','Player Rating'),('C','Team Ranking'),('D','Match Simulation')]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='predictions')
    engine = models.CharField(max_length=1, choices=ENGINE_CHOICES)
    input_data = models.JSONField()
    output_data = models.JSONField()
    confidence = models.IntegerField(default=0)
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
