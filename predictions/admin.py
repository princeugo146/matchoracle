from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Avg, Count
from .models import (
    Prediction, TeamRanking, WeeklyTip,
    TeamProfile, EngineAccuracy, PredictionResult,
    WeightAdjustment, PatternMemory, PlayerProfile,
    ConversationMemory,
)


# ─── Prediction ───────────────────────────────────────────────────────────────

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user_email', 'engine', 'home_team', 'away_team',
        'predicted_result', 'confidence_bar', 'correctness_badge', 'created_at',
    ]
    list_filter = ['engine', 'was_correct', 'created_at']
    search_fields = ['user__email', 'home_team', 'away_team', 'predicted_result']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'input_data', 'output_data']
    ordering = ['-created_at']
    list_per_page = 50

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'

    def confidence_bar(self, obj):
        color = '#10b981' if obj.confidence >= 70 else '#f59e0b' if obj.confidence >= 50 else '#ef4444'
        return format_html(
            '<div style="width:80px;background:#1a2332;border-radius:4px;height:14px;">'
            '<div style="width:{}%;background:{};height:100%;border-radius:4px;"></div>'
            '</div> <small>{}</small>',
            min(obj.confidence, 100), color, obj.confidence,
        )
    confidence_bar.short_description = 'Confidence'

    def correctness_badge(self, obj):
        if obj.was_correct is True:
            return format_html('<span style="color:#10b981;font-weight:700">✓ Correct</span>')
        elif obj.was_correct is False:
            return format_html('<span style="color:#ef4444;font-weight:700">✗ Wrong</span>')
        return format_html('<span style="color:#94a3b8">— Pending</span>')
    correctness_badge.short_description = 'Result'


# ─── TeamRanking ──────────────────────────────────────────────────────────────

@admin.register(TeamRanking)
class TeamRankingAdmin(admin.ModelAdmin):
    list_display = ['name', 'user_email', 'power_elo', 'wins', 'draws', 'losses', 'goal_diff']
    list_filter = ['user__plan']
    search_fields = ['name', 'user__email']
    ordering = ['-power_elo']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def goal_diff(self, obj):
        diff = obj.goals_for - obj.goals_against
        color = '#10b981' if diff > 0 else '#ef4444' if diff < 0 else '#94a3b8'
        return format_html('<span style="color:{}">{:+d}</span>', color, diff)
    goal_diff.short_description = 'GD'


# ─── WeeklyTip ────────────────────────────────────────────────────────────────

@admin.register(WeeklyTip)
class WeeklyTipAdmin(admin.ModelAdmin):
    list_display = ['home_team', 'away_team', 'competition', 'tip', 'confidence', 'is_pro_only', 'match_date']
    list_filter = ['is_pro_only', 'competition']
    search_fields = ['home_team', 'away_team', 'tip']
    date_hierarchy = 'match_date'


# ─── EngineAccuracy ───────────────────────────────────────────────────────────

@admin.register(EngineAccuracy)
class EngineAccuracyAdmin(admin.ModelAdmin):
    list_display = [
        'engine', 'match_type', 'accuracy_display', 'home_accuracy',
        'away_accuracy', 'draw_accuracy', 'weight_adjustment', 'sample_size', 'updated_at',
    ]
    list_filter = ['engine', 'match_type']
    readonly_fields = ['updated_at', 'created_at', 'tactical_matchup_accuracy']
    ordering = ['engine', 'match_type']

    def accuracy_display(self, obj):
        pct = obj.accuracy_pct
        color = '#10b981' if pct >= 65 else '#f59e0b' if pct >= 50 else '#ef4444'
        return format_html(
            '<span style="color:{};font-weight:700">{:.1f}%</span>', color, pct
        )
    accuracy_display.short_description = 'Accuracy'
    accuracy_display.admin_order_field = 'accuracy_pct'


# ─── PredictionResult ─────────────────────────────────────────────────────────

@admin.register(PredictionResult)
class PredictionResultAdmin(admin.ModelAdmin):
    list_display = [
        'prediction_id', 'prediction_teams', 'actual_result', 'actual_score',
        'correctness_badge', 'margin_of_error', 'result_source', 'result_checked_at',
    ]
    list_filter = ['was_correct', 'result_source']
    search_fields = ['prediction__home_team', 'prediction__away_team', 'actual_result']
    readonly_fields = ['created_at', 'raw_data']
    date_hierarchy = 'created_at'

    def prediction_id(self, obj):
        return f'#{obj.prediction_id}'
    prediction_id.short_description = 'Pred ID'

    def prediction_teams(self, obj):
        return f'{obj.prediction.home_team} vs {obj.prediction.away_team}'
    prediction_teams.short_description = 'Match'

    def correctness_badge(self, obj):
        if obj.was_correct is True:
            return format_html('<span style="color:#10b981;font-weight:700">✓ Correct</span>')
        elif obj.was_correct is False:
            return format_html('<span style="color:#ef4444;font-weight:700">✗ Wrong</span>')
        return format_html('<span style="color:#94a3b8">— Pending</span>')
    correctness_badge.short_description = 'Correct?'


# ─── TeamProfile ──────────────────────────────────────────────────────────────

@admin.register(TeamProfile)
class TeamProfileAdmin(admin.ModelAdmin):
    list_display = [
        'team_name', 'tactical_style', 'avg_goals_scored', 'avg_goals_conceded',
        'home_accuracy', 'away_accuracy', 'sample_size', 'freshness', 'updated_at',
    ]
    list_filter = ['tactical_style']
    search_fields = ['team_name']
    readonly_fields = ['updated_at', 'created_at', 'last_20_results', 'key_players',
                       'injury_history', 'vs_style_accuracy']
    ordering = ['-sample_size']

    def freshness(self, obj):
        if obj.needs_update():
            return format_html('<span style="color:#ef4444">⚠ Stale</span>')
        return format_html('<span style="color:#10b981">✓ Fresh</span>')
    freshness.short_description = 'Status'


# ─── WeightAdjustment ─────────────────────────────────────────────────────────

@admin.register(WeightAdjustment)
class WeightAdjustmentAdmin(admin.ModelAdmin):
    list_display = [
        'engine', 'parameter', 'match_type', 'old_weight', 'new_weight',
        'delta_display', 'accuracy_before', 'accuracy_after', 'improvement_badge', 'applied_at',
    ]
    list_filter = ['engine', 'match_type']
    search_fields = ['engine', 'parameter', 'reason']
    readonly_fields = ['applied_at']
    date_hierarchy = 'applied_at'
    ordering = ['-applied_at']

    def delta_display(self, obj):
        delta = obj.delta
        color = '#10b981' if delta > 0 else '#ef4444' if delta < 0 else '#94a3b8'
        sign = '+' if delta >= 0 else ''
        return format_html('<span style="color:{}">{}{:.4f}</span>', color, sign, delta)
    delta_display.short_description = 'Δ Weight'

    def improvement_badge(self, obj):
        improved = obj.improved
        if improved is True:
            return format_html('<span style="color:#10b981">↑ Better</span>')
        elif improved is False:
            return format_html('<span style="color:#ef4444">↓ Worse</span>')
        return format_html('<span style="color:#94a3b8">—</span>')
    improvement_badge.short_description = 'Impact'


# ─── PatternMemory ────────────────────────────────────────────────────────────

@admin.register(PatternMemory)
class PatternMemoryAdmin(admin.ModelAdmin):
    list_display = [
        'pattern_type', 'pattern_key', 'accuracy_display', 'occurrences',
        'min_sample', 'reliability_badge', 'last_seen_at',
    ]
    list_filter = ['pattern_type']
    search_fields = ['pattern_key']
    readonly_fields = ['last_updated', 'created_at', 'pattern_value']
    ordering = ['-occurrences', '-accuracy']

    def accuracy_display(self, obj):
        color = '#10b981' if obj.accuracy >= 65 else '#f59e0b' if obj.accuracy >= 50 else '#ef4444'
        return format_html('<span style="color:{};font-weight:700">{:.1f}%</span>', color, obj.accuracy)
    accuracy_display.short_description = 'Accuracy'
    accuracy_display.admin_order_field = 'accuracy'

    def reliability_badge(self, obj):
        if obj.is_reliable():
            return format_html('<span style="color:#10b981">✓ Reliable</span>')
        return format_html('<span style="color:#f59e0b">⚠ Low data</span>')
    reliability_badge.short_description = 'Reliability'


# ─── PlayerProfile ────────────────────────────────────────────────────────────

@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'team', 'position', 'overall_rating_display', 'injury_status_badge',
        'goals_this_season', 'assists_this_season', 'appearances_this_season',
        'prediction_impact', 'freshness', 'updated_at',
    ]
    list_filter = ['position', 'injury_status', 'team']
    search_fields = ['name', 'team']
    readonly_fields = ['updated_at', 'created_at', 'injury_history', 'recent_ratings', 'raw_data']
    ordering = ['-overall_rating']

    def overall_rating_display(self, obj):
        r = obj.overall_rating
        color = '#10b981' if r >= 75 else '#f59e0b' if r >= 55 else '#ef4444'
        return format_html('<span style="color:{};font-weight:700">{:.0f}</span>', color, r)
    overall_rating_display.short_description = 'Rating'
    overall_rating_display.admin_order_field = 'overall_rating'

    def injury_status_badge(self, obj):
        colors = {'fit': '#10b981', 'doubt': '#f59e0b', 'out': '#ef4444', 'unknown': '#94a3b8'}
        color = colors.get(obj.injury_status, '#94a3b8')
        return format_html('<span style="color:{};font-weight:600">{}</span>', color, obj.injury_status.title())
    injury_status_badge.short_description = 'Injury'
    injury_status_badge.admin_order_field = 'injury_status'

    def freshness(self, obj):
        if obj.needs_update():
            return format_html('<span style="color:#ef4444">⚠ Stale</span>')
        return format_html('<span style="color:#10b981">✓ Fresh</span>')
    freshness.short_description = 'Status'


# ─── ConversationMemory ───────────────────────────────────────────────────────

@admin.register(ConversationMemory)
class ConversationMemoryAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'session_id', 'message_count', 'is_expired_badge', 'expires_at', 'updated_at']
    list_filter = ['created_at']
    search_fields = ['user_id', 'session_id']
    readonly_fields = ['created_at', 'updated_at', 'messages', 'context']
    ordering = ['-updated_at']

    def message_count(self, obj):
        return len(obj.messages)
    message_count.short_description = 'Messages'

    def is_expired_badge(self, obj):
        if obj.is_expired():
            return format_html('<span style="color:#ef4444">Expired</span>')
        return format_html('<span style="color:#10b981">Active</span>')
    is_expired_badge.short_description = 'Status'

