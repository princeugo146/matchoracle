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
    result_label = models.CharField(max_length=20, blank=True, default='')  # 'correct', 'close', 'wrong'
    result_checked = models.BooleanField(default=False)
    actual_result = models.CharField(max_length=100, blank=True)
    actual_score = models.CharField(max_length=20, blank=True)
    result_check_attempts = models.IntegerField(default=0)
    last_result_check_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def increment_check_attempt(self):
        """Record that a result-check attempt was made for this prediction."""
        self.result_check_attempts += 1
        self.last_result_check_at = timezone.now()
        self.save(update_fields=['result_check_attempts', 'last_result_check_at'])

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


# ─── Match Result Admin Panel ─────────────────────────────────────────────────

class MatchResult(models.Model):
    """
    Stores real match results entered manually via the admin panel.
    Automatically marks related Predictions as correct / close / wrong
    and updates TeamProfile stats when saved.
    """
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    home_score = models.IntegerField()
    away_score = models.IntegerField()
    match_date = models.DateField()
    competition = models.CharField(max_length=100, default='Unknown')
    match_type = models.CharField(max_length=50, default='league')

    # Team stats entered manually
    home_possession = models.FloatField(default=50)
    away_possession = models.FloatField(default=50)
    home_shots = models.IntegerField(default=0)
    away_shots = models.IntegerField(default=0)
    home_tactical_style = models.CharField(max_length=50, default='balanced')
    away_tactical_style = models.CharField(max_length=50, default='balanced')
    home_key_player = models.CharField(max_length=100, blank=True)
    away_key_player = models.CharField(max_length=100, blank=True)
    match_summary = models.TextField(blank=True)
    what_decided_match = models.TextField(blank=True)

    # Auto-populated fields
    result = models.CharField(max_length=10, blank=True)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Auto-calculate result from scores
        if self.home_score > self.away_score:
            self.result = 'home'
        elif self.away_score > self.home_score:
            self.result = 'away'
        else:
            self.result = 'draw'
        super().save(*args, **kwargs)

        # Process predictions only once
        if not self.processed:
            self.process_predictions()

    def process_predictions(self):
        """Mark predictions correct/wrong/close and update team profiles."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Find all unverified predictions for this match
            preds = Prediction.objects.filter(
                home_team__icontains=self.home_team,
                away_team__icontains=self.away_team,
                result_checked=False,
            )

            for pred in preds:
                predicted = pred.predicted_result.lower() if pred.predicted_result else ''
                actual = self.result

                # Determine correct / close / wrong
                if actual == 'home' and self.home_team.lower() in predicted:
                    pred.was_correct = True
                    pred.result_label = 'correct'
                elif actual == 'away' and self.away_team.lower() in predicted:
                    pred.was_correct = True
                    pred.result_label = 'correct'
                elif actual == 'draw' and 'draw' in predicted:
                    pred.was_correct = True
                    pred.result_label = 'correct'
                else:
                    # Close = the actual outcome had ≥35 % predicted probability
                    output = pred.output_data or {}
                    if actual == 'home':
                        pct = output.get('home_win', 0)
                    elif actual == 'away':
                        pct = output.get('away_win', 0)
                    else:
                        pct = output.get('draw', 0)

                    if pct >= 35:
                        pred.was_correct = False
                        pred.result_label = 'close'
                    else:
                        pred.was_correct = False
                        pred.result_label = 'wrong'

                pred.actual_result = self.result
                pred.actual_score = f"{self.home_score}-{self.away_score}"
                pred.result_checked = True
                pred.save()

                # Refresh user accuracy counters
                user = pred.user
                user.total_predictions = Prediction.objects.filter(user=user).count()
                user.correct_predictions = Prediction.objects.filter(
                    user=user, was_correct=True
                ).count()
                user.save(update_fields=['total_predictions', 'correct_predictions'])

            # Update both team profiles with real stats
            self._update_team_profile(
                self.home_team,
                won=(self.result == 'home'),
                drew=(self.result == 'draw'),
                goals_scored=self.home_score,
                goals_conceded=self.away_score,
                possession=self.home_possession,
                tactical_style=self.home_tactical_style,
                key_player=self.home_key_player,
                is_home=True,
            )
            self._update_team_profile(
                self.away_team,
                won=(self.result == 'away'),
                drew=(self.result == 'draw'),
                goals_scored=self.away_score,
                goals_conceded=self.home_score,
                possession=self.away_possession,
                tactical_style=self.away_tactical_style,
                key_player=self.away_key_player,
                is_home=False,
            )

            # Mark this record as processed so it won't run again
            MatchResult.objects.filter(pk=self.pk).update(processed=True)

        except Exception as e:
            logger.error(
                f"Error processing predictions for match {self}: {e}", exc_info=True
            )

    def _update_team_profile(
        self, team_name, won, drew, goals_scored, goals_conceded,
        possession, tactical_style, key_player, is_home,
    ):
        """Update a TeamProfile with stats from this match result."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            profile, _ = TeamProfile.objects.get_or_create(team_name=team_name)

            # Prepend this result to last_20_results (capped at 20)
            recent = profile.last_20_results or []
            recent.insert(0, {
                'date': str(self.match_date),
                'score': f"{goals_scored}-{goals_conceded}",
                'location': 'home' if is_home else 'away',
                'outcome': 'W' if won else ('D' if drew else 'L'),
                'possession': possession,
                'tactical_style': tactical_style,
            })
            profile.last_20_results = recent[:20]

            # Update tactical style when a non-default style is consistently used
            if tactical_style and tactical_style != 'balanced':
                profile.tactical_style = tactical_style

            # Update key players list (unique, most recent first, capped at 10)
            if key_player and key_player not in (profile.key_players or []):
                kp = profile.key_players or []
                kp.insert(0, key_player)
                profile.key_players = kp[:10]

            # Recalculate rolling goal averages from the last 10 results
            recent_10 = profile.last_20_results[:10]
            if recent_10:
                profile.avg_goals_scored = sum(
                    int(r['score'].split('-')[0]) for r in recent_10
                ) / len(recent_10)
                profile.avg_goals_conceded = sum(
                    int(r['score'].split('-')[1]) for r in recent_10
                ) / len(recent_10)

            profile.save()
        except Exception as e:
            logger.error(f"Team profile update error for {team_name}: {e}", exc_info=True)

    def __str__(self):
        return (
            f"{self.home_team} {self.home_score}-{self.away_score} "
            f"{self.away_team} ({self.match_date})"
        )

    class Meta:
        ordering = ['-match_date']
