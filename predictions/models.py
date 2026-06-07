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
    tactical_matchup_accuracy = models.JSONField(default=dict)

    # Home/away/draw breakdown
    home_accuracy = models.FloatField(default=0.0)
    away_accuracy = models.FloatField(default=0.0)
    draw_accuracy = models.FloatField(default=0.0)

    # Weight adjustment factor derived from accuracy (1.0 = no adjustment)
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


class WeightAdjustment(models.Model):
    """
    Audit log of every engine weight change made by the learning system.
    Lets you trace why a weight changed and whether it improved accuracy.
    Written by WeightAdjuster.apply() and readable via the admin or API.
    """
    ENGINE_CHOICES = [('A', 'Match'), ('B', 'Player'), ('D', 'Simulation'), ('NL', 'AI')]

    engine = models.CharField(max_length=2, choices=ENGINE_CHOICES, db_index=True)

    # Which internal parameter was adjusted (e.g. 'home_advantage', 'form_weight')
    parameter = models.CharField(max_length=100)

    old_weight = models.FloatField()
    new_weight = models.FloatField()

    # Human-readable explanation of why the change was made
    reason = models.TextField(blank=True)

    # Accuracy snapshot before and after the adjustment (filled in retrospectively)
    accuracy_before = models.FloatField(null=True, blank=True)
    accuracy_after = models.FloatField(null=True, blank=True)

    # Match type this adjustment applies to (mirrors EngineAccuracy.match_type)
    match_type = models.CharField(max_length=20, default='league')

    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-applied_at']
        indexes = [
            models.Index(fields=['engine', 'parameter'], name='pred_wa_eng_param_idx'),
        ]

    def __str__(self):
        delta = self.new_weight - self.old_weight
        sign = '+' if delta >= 0 else ''
        return (
            f"WeightAdjustment({self.engine}/{self.parameter}: "
            f"{self.old_weight:.3f} → {self.new_weight:.3f} [{sign}{delta:.3f}])"
        )

    @property
    def delta(self):
        return round(self.new_weight - self.old_weight, 6)

    @property
    def improved(self):
        """Returns True if accuracy_after > accuracy_before (when both are set)."""
        if self.accuracy_before is None or self.accuracy_after is None:
            return None
        return self.accuracy_after > self.accuracy_before


class PatternMemory(models.Model):
    """
    Stores recurring patterns extracted from verified predictions.
    The learning system writes here; the engine reads here to bias future
    predictions when a known pattern is detected.

    Examples:
      pattern_type='team',      pattern_key='Arsenal_home',
          pattern_value={'win_rate': 0.72, 'avg_goals': 2.1}
      pattern_type='matchup',   pattern_key='high_press_vs_possession',
          pattern_value={'home_advantage': 1.18, 'sample': 34}
      pattern_type='condition', pattern_key='rain_away_goals',
          pattern_value={'goal_reduction': 0.15}
    """
    PATTERN_TYPE_CHOICES = [
        ('team',      'Team Pattern'),
        ('player',    'Player Pattern'),
        ('matchup',   'Tactical Matchup'),
        ('condition', 'Match Condition'),
        ('h2h',       'Head-to-Head'),
    ]

    pattern_type = models.CharField(
        max_length=20, choices=PATTERN_TYPE_CHOICES, db_index=True
    )

    # Unique identifier for this pattern within its type
    pattern_key = models.CharField(max_length=200, db_index=True)

    # Arbitrary JSON payload — structure depends on pattern_type
    pattern_value = models.JSONField(default=dict)

    # How accurate predictions were when this pattern was applied (0–100)
    accuracy = models.FloatField(default=0.0)

    # How many times this pattern has been observed
    occurrences = models.IntegerField(default=1)

    # Confidence threshold: only apply this pattern when occurrences >= min_sample
    min_sample = models.IntegerField(default=5)

    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['pattern_type', 'pattern_key']
        ordering = ['-occurrences', '-accuracy']

    def __str__(self):
        return f"PatternMemory({self.pattern_type}/{self.pattern_key}, n={self.occurrences}, acc={self.accuracy:.1f}%)"

    def is_reliable(self):
        """Returns True when the pattern has enough observations to be trusted."""
        return self.occurrences >= self.min_sample

    def merge(self, new_accuracy, new_value=None):
        """
        Incrementally update this pattern with a new observation.
        Uses exponential moving average for accuracy (α=0.1).
        """
        alpha = 0.1
        self.accuracy = round(alpha * new_accuracy + (1 - alpha) * self.accuracy, 2)
        self.occurrences += 1
        if new_value:
            self.pattern_value.update(new_value)
        self.last_seen_at = timezone.now()
        self.save(update_fields=['accuracy', 'occurrences', 'pattern_value', 'last_seen_at', 'last_updated'])


class PlayerProfile(models.Model):
    """
    Stores accumulated knowledge about a player that grows over time.
    Populated by the PatternLearner and updated by the background tasks.
    """
    POSITION_CHOICES = [
        ('GK', 'Goalkeeper'), ('CB', 'Centre-Back'), ('LB', 'Left-Back'),
        ('RB', 'Right-Back'), ('CDM', 'Defensive Mid'), ('CM', 'Central Mid'),
        ('CAM', 'Attacking Mid'), ('LW', 'Left Wing'), ('RW', 'Right Wing'),
        ('ST', 'Striker'),
    ]

    name = models.CharField(max_length=100, unique=True, db_index=True)
    team = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=5, choices=POSITION_CHOICES, blank=True)

    # Current season stats
    goals_this_season = models.IntegerField(default=0)
    assists_this_season = models.IntegerField(default=0)
    appearances_this_season = models.IntegerField(default=0)

    # Derived performance metrics (0–100 scale)
    attack_rating = models.FloatField(default=0.0)
    defense_rating = models.FloatField(default=0.0)
    overall_rating = models.FloatField(default=0.0)

    # Injury tracking
    injury_status = models.CharField(
        max_length=20,
        choices=[('fit', 'Fit'), ('doubt', 'Doubt'), ('out', 'Out'), ('unknown', 'Unknown')],
        default='unknown',
    )
    injury_history = models.JSONField(default=list)   # list of {type, date, duration_days}

    # Form — last 5 match ratings (0–10 each)
    recent_ratings = models.JSONField(default=list)

    # Impact on team prediction accuracy when this player is listed
    prediction_impact = models.FloatField(default=0.0)

    # Raw data from last web search (for debugging)
    raw_data = models.JSONField(default=dict)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-overall_rating', 'name']

    def __str__(self):
        return f"PlayerProfile({self.name}, {self.team}, {self.position}, {self.overall_rating:.0f})"

    def needs_update(self):
        """Returns True if the profile hasn't been refreshed in the last 48 hours."""
        return (timezone.now() - self.updated_at) > timedelta(hours=48)

    def form_average(self):
        """Return the mean of recent_ratings, or 0 if empty."""
        if not self.recent_ratings:
            return 0.0
        return round(sum(self.recent_ratings) / len(self.recent_ratings), 2)


class LiveMatch(models.Model):
    """
    Cached live / scheduled match data fetched from Sportmonks.
    Refreshed every 60 seconds by get_live_matches_cached().
    """
    STATUS_CHOICES = [
        ('LIVE', 'Live'),
        ('SCHEDULED', 'Scheduled'),
        ('FINISHED', 'Finished'),
        ('POSTPONED', 'Postponed'),
        ('CANCELLED', 'Cancelled'),
    ]

    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='SCHEDULED')
    minute = models.IntegerField(null=True, blank=True)
    competition = models.CharField(max_length=100, blank=True)
    start_time = models.DateTimeField()
    sportmonks_id = models.IntegerField(null=True, blank=True, unique=True)
    home_logo = models.URLField(blank=True, default='')
    away_logo = models.URLField(blank=True, default='')

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        score = (
            f"{self.home_score}-{self.away_score}"
            if self.home_score is not None
            else "vs"
        )
        return f"LiveMatch({self.home_team} {score} {self.away_team}, {self.status})"

    def to_dict(self):
        return {
            'id': self.pk,
            'home_team': self.home_team,
            'away_team': self.away_team,
            'home_score': self.home_score,
            'away_score': self.away_score,
            'status': self.status,
            'minute': self.minute,
            'competition': self.competition,
            'start_time': self.start_time.isoformat(),
            'sportmonks_id': self.sportmonks_id,
            'home_logo': self.home_logo,
            'away_logo': self.away_logo,
        }


class ConversationMemory(models.Model):
    """
    Session-scoped memory for the natural language interface.
    Stores the teams, players, and tactics discussed so follow-up
    questions can be answered in context.  Expires after 24 hours.
    """
    user_id = models.IntegerField(db_index=True)   # FK-free so anonymous sessions work too
    session_id = models.CharField(max_length=64, db_index=True)

    # Structured context extracted from the conversation
    context = models.JSONField(default=dict)

    # Ordered list of Q&A pairs
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
