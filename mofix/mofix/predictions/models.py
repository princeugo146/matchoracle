from django.db import models
from django.utils import timezone
from datetime import timedelta
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


# ─── Self-Learning Models ─────────────────────────────────────────────────────

class TeamProfile(models.Model):
    """
    Stores accumulated knowledge about a team that grows over time.
    Updated automatically every 24 hours by the background learning tasks.
    """
    team_name = models.CharField(max_length=100, unique=True, db_index=True)

    # Recent form — last 20 results stored as a JSON list of dicts
    # e.g. [{"opponent": "Chelsea", "result": "W", "score": "2-1", "date": "2024-01-15"}, ...]
    last_20_results = models.JSONField(default=list)

    # Scoring averages (rolling, updated from last_20_results)
    avg_goals_scored = models.FloatField(default=0.0)
    avg_goals_conceded = models.FloatField(default=0.0)

    # Detected tactical style (high_press / counter_attack / possession / etc.)
    tactical_style = models.CharField(max_length=50, default='balanced')

    # Key player names (JSON list of strings)
    key_players = models.JSONField(default=list)

    # Injury history — JSON list of {"player": ..., "type": ..., "date": ...}
    injury_history = models.JSONField(default=list)

    # Accuracy stats for predictions involving this team
    home_accuracy = models.FloatField(default=0.0)   # % correct when home
    away_accuracy = models.FloatField(default=0.0)   # % correct when away
    # JSON dict: {"high_press": 0.72, "possession": 0.65, ...}
    vs_style_accuracy = models.JSONField(default=dict)

    # Metadata
    sample_size = models.IntegerField(default=0)      # total predictions tracked
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['team_name']

    def __str__(self):
        return f"TeamProfile({self.team_name})"

    def needs_update(self):
        """Returns True if the profile hasn't been refreshed in the last 24 hours."""
        return (timezone.now() - self.updated_at) > timedelta(hours=24)

    def to_engine_dict(self):
        """Return a dict that can be merged into engine_a / engine_d input data."""
        return {
            'goals_scored': self.avg_goals_scored,
            'goals_conceded': self.avg_goals_conceded,
            'tactical_style': self.tactical_style,
            'form': ''.join(r.get('result', '') for r in self.last_20_results[:5]),
        }


class EngineAccuracy(models.Model):
    """
    Tracks prediction accuracy per engine, match type, and tactical matchup.
    Only updated when sample_size > 10 to avoid noise.
    """
    ENGINE_CHOICES = [('A', 'Match'), ('B', 'Player'), ('D', 'Simulation'), ('NL', 'AI')]
    MATCH_TYPE_CHOICES = [
        ('league', 'League'), ('cup', 'Cup'), ('champions', 'Champions League'),
        ('friendly', 'Friendly'), ('knockout', 'Knockout'), ('final', 'Final'),
    ]

    engine = models.CharField(max_length=2, choices=ENGINE_CHOICES, db_index=True)
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, default='league')

    # Overall accuracy for this engine + match_type combination
    accuracy_pct = models.FloatField(default=0.0)

    # Tactical matchup accuracy — JSON dict keyed by "style_vs_style"
    # e.g. {"high_press_vs_possession": 0.68, "counter_attack_vs_possession": 0.72}
    tactical_matchup_accuracy = models.JSONField(default=dict)

    # Home/away/draw breakdown
    home_accuracy = models.FloatField(default=0.0)
    away_accuracy = models.FloatField(default=0.0)
    draw_accuracy = models.FloatField(default=0.0)

    # Weight adjustment factor derived from accuracy (1.0 = no adjustment)
    # Applied as a multiplier in future predictions when LEARNING_ENABLED=True
    weight_adjustment = models.FloatField(default=1.0)

    # Only update stats when we have enough data
    sample_size = models.IntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['engine', 'match_type']
        ordering = ['engine', 'match_type']

    def __str__(self):
        return f"EngineAccuracy({self.engine}, {self.match_type}, {self.accuracy_pct:.1f}%)"

    def get_weight_adjustment(self):
        """
        Returns the confidence multiplier for this engine.
        Only meaningful when sample_size > 10.
        """
        if self.sample_size < 10:
            return 1.0
        return self.weight_adjustment


class PredictionResult(models.Model):
    """
    Links a saved Prediction to its real-world outcome.
    Populated by the check_match_results Celery task.
    """
    RESULT_SOURCE_CHOICES = [
        ('sportmonks', 'Sportmonks API'),
        ('web_search', 'Web Search'),
        ('manual', 'Manual Entry'),
    ]

    prediction = models.OneToOneField(
        Prediction, on_delete=models.CASCADE, related_name='result_record'
    )

    # The actual match result, e.g. "Arsenal" / "Draw" / "Chelsea"
    actual_result = models.CharField(max_length=100, blank=True)

    # Full score string, e.g. "2-1"
    actual_score = models.CharField(max_length=20, blank=True)

    # Whether the prediction verdict matched the actual result
    was_correct = models.BooleanField(null=True, blank=True)

    # How far off the predicted score was (absolute goal difference)
    margin_of_error = models.FloatField(null=True, blank=True)

    # When the result was fetched and from where
    result_checked_at = models.DateTimeField(null=True, blank=True)
    result_source = models.CharField(
        max_length=20, choices=RESULT_SOURCE_CHOICES, default='web_search'
    )

    # Raw data returned by the source (for debugging)
    raw_data = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        status = 'correct' if self.was_correct else ('wrong' if self.was_correct is False else 'pending')
        return f"PredictionResult(pred={self.prediction_id}, {status})"


class ConversationMemory(models.Model):
    """
    Session-scoped memory for the natural language interface.
    Stores the teams, players, and tactics discussed so follow-up
    questions can be answered in context.  Expires after 24 hours.
    """
    user_id = models.IntegerField(db_index=True)   # FK-free so anonymous sessions work too
    session_id = models.CharField(max_length=64, db_index=True)

    # Structured context extracted from the conversation
    # e.g. {"teams": ["Arsenal", "Chelsea"], "competition": "Premier League", "tactics": [...]}
    context = models.JSONField(default=dict)

    # Ordered list of Q&A pairs
    # e.g. [{"question": "...", "answer": "...", "intent": "match_prediction", "ts": "..."}]
    messages = models.JSONField(default=list)

    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user_id', 'session_id']
        ordering = ['-updated_at']

    def __str__(self):
        return f"ConversationMemory(user={self.user_id}, session={self.session_id})"

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def add_message(self, question, answer, intent='general'):
        """Append a Q&A pair and refresh the expiry window."""
        self.messages.append({
            'question': question,
            'answer': answer,
            'intent': intent,
            'ts': timezone.now().isoformat(),
        })
        # Keep only the last 20 messages to avoid unbounded growth
        self.messages = self.messages[-20:]
        self.expires_at = timezone.now() + timedelta(hours=24)
        self.save(update_fields=['messages', 'expires_at', 'updated_at'])

    def update_context(self, new_context: dict):
        """Merge new context keys into the existing context dict."""
        self.context.update(new_context)
        self.save(update_fields=['context', 'updated_at'])

    @classmethod
    def get_or_create_session(cls, user_id, session_id):
        """Return an active session or create a fresh one."""
        try:
            mem = cls.objects.get(user_id=user_id, session_id=session_id)
            if mem.is_expired():
                mem.messages = []
                mem.context = {}
                mem.expires_at = timezone.now() + timedelta(hours=24)
                mem.save(update_fields=['messages', 'context', 'expires_at', 'updated_at'])
            return mem
        except cls.DoesNotExist:
            return cls.objects.create(
                user_id=user_id,
                session_id=session_id,
                context={},
                messages=[],
                expires_at=timezone.now() + timedelta(hours=24),
            )
