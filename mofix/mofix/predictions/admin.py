from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.db.models import Count, Avg, Q

from .models import (
    Prediction, TeamRanking, WeeklyTip,
    TeamProfile, EngineAccuracy, PredictionResult, ConversationMemory,
    WeightAdjustment, PatternMemory, PlayerProfile,
)
from .admin_filters import (
    DateRangeFilter, EngineFilter, MatchTypeFilter,
    AccuracyRangeFilter, PatternTypeFilter,
)
from .admin_actions import (
    export_predictions_csv, export_patterns_json,
    recalculate_accuracy, reset_weights, archive_old_data,
)

# ─── Inline helpers ───────────────────────────────────────────────────────────

admin.site.register(Prediction)
admin.site.register(TeamRanking)
admin.site.register(WeeklyTip)


# ─── PredictionResult ─────────────────────────────────────────────────────────

@admin.register(PredictionResult)
class PredictionResultAdmin(admin.ModelAdmin):
    list_display = (
        'prediction_id', 'home_away', 'engine_badge',
        'actual_result', 'was_correct_badge', 'margin_of_error',
        'result_source', 'created_at',
    )
    list_filter = ('was_correct', 'result_source', DateRangeFilter)
    search_fields = ('prediction__home_team', 'prediction__away_team')
    readonly_fields = (
        'prediction', 'actual_result', 'actual_score', 'was_correct',
        'margin_of_error', 'result_checked_at', 'raw_data', 'created_at',
    )
    actions = [export_predictions_csv]
    list_per_page = 50

    def home_away(self, obj):
        p = obj.prediction
        return f"{p.home_team} vs {p.away_team}" if p else '—'
    home_away.short_description = 'Match'

    def engine_badge(self, obj):
        colours = {'A': '#00d4ff', 'B': '#10b981', 'D': '#f59e0b', 'NL': '#a78bfa'}
        engine = getattr(obj.prediction, 'engine', '?')
        colour = colours.get(engine, '#94a3b8')
        return format_html(
            '<span style="background:{}22;color:{};border:1px solid {}44;'
            'padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;">{}</span>',
            colour, colour, colour, engine,
        )
    engine_badge.short_description = 'Engine'

    def was_correct_badge(self, obj):
        if obj.was_correct is None:
            return format_html('<span style="color:#94a3b8;">⏳ Pending</span>')
        if obj.was_correct:
            return format_html('<span style="color:#10b981;font-weight:700;">✓ Correct</span>')
        return format_html('<span style="color:#ef4444;font-weight:700;">✗ Wrong</span>')
    was_correct_badge.short_description = 'Result'


# ─── EngineAccuracy ───────────────────────────────────────────────────────────

@admin.register(EngineAccuracy)
class EngineAccuracyAdmin(admin.ModelAdmin):
    list_display = (
        'engine', 'match_type', 'accuracy_pct_badge',
        'home_accuracy', 'away_accuracy', 'draw_accuracy',
        'weight_adjustment', 'sample_size', 'updated_at',
    )
    list_filter = ('engine', 'match_type', AccuracyRangeFilter)
    readonly_fields = (
        'engine', 'match_type', 'accuracy_pct', 'sample_size',
        'home_accuracy', 'away_accuracy', 'draw_accuracy',
        'tactical_matchup_accuracy', 'created_at', 'updated_at',
    )
    actions = [recalculate_accuracy, reset_weights]

    def accuracy_pct_badge(self, obj):
        pct = obj.accuracy_pct
        if pct >= 70:
            colour = '#10b981'
        elif pct >= 55:
            colour = '#f59e0b'
        else:
            colour = '#ef4444'
        return format_html(
            '<span style="color:{};font-weight:700;">{:.1f}%</span>',
            colour, pct,
        )
    accuracy_pct_badge.short_description = 'Accuracy'
    accuracy_pct_badge.admin_order_field = 'accuracy_pct'


# ─── WeightAdjustment ────────────────────────────────────────────────────────

@admin.register(WeightAdjustment)
class WeightAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        'engine', 'parameter', 'old_weight', 'new_weight',
        'delta_badge', 'match_type', 'accuracy_before', 'accuracy_after',
        'improved_badge', 'applied_at',
    )
    list_filter = ('engine', 'match_type', DateRangeFilter)
    search_fields = ('parameter', 'reason')
    readonly_fields = (
        'engine', 'parameter', 'old_weight', 'new_weight',
        'reason', 'accuracy_before', 'accuracy_after', 'applied_at',
    )
    list_per_page = 50

    def delta_badge(self, obj):
        delta = obj.delta
        colour = '#10b981' if delta >= 0 else '#ef4444'
        sign = '+' if delta >= 0 else ''
        return format_html(
            '<span style="color:{};font-weight:700;">{}{:.4f}</span>',
            colour, sign, delta,
        )
    delta_badge.short_description = 'Δ Weight'

    def improved_badge(self, obj):
        result = obj.improved
        if result is None:
            return format_html('<span style="color:#94a3b8;">—</span>')
        if result:
            return format_html('<span style="color:#10b981;font-weight:700;">↑ Better</span>')
        return format_html('<span style="color:#ef4444;font-weight:700;">↓ Worse</span>')
    improved_badge.short_description = 'Impact'


# ─── PatternMemory ────────────────────────────────────────────────────────────

@admin.register(PatternMemory)
class PatternMemoryAdmin(admin.ModelAdmin):
    list_display = (
        'pattern_type', 'pattern_key', 'accuracy_badge',
        'occurrences', 'min_sample', 'is_reliable_badge',
        'last_seen_at', 'last_updated',
    )
    list_filter = ('pattern_type', PatternTypeFilter, DateRangeFilter)
    search_fields = ('pattern_key',)
    readonly_fields = ('pattern_type', 'pattern_key', 'accuracy', 'occurrences', 'created_at', 'last_updated')
    actions = [export_patterns_json, archive_old_data]
    list_per_page = 50

    def accuracy_badge(self, obj):
        pct = obj.accuracy
        if pct >= 70:
            colour = '#10b981'
        elif pct >= 55:
            colour = '#f59e0b'
        else:
            colour = '#ef4444'
        return format_html(
            '<span style="color:{};font-weight:700;">{:.1f}%</span>',
            colour, pct,
        )
    accuracy_badge.short_description = 'Accuracy'
    accuracy_badge.admin_order_field = 'accuracy'

    def is_reliable_badge(self, obj):
        if obj.is_reliable():
            return format_html('<span style="color:#10b981;font-weight:700;">✓ Reliable</span>')
        return format_html('<span style="color:#f59e0b;">⏳ Building</span>')
    is_reliable_badge.short_description = 'Status'


# ─── TeamProfile ──────────────────────────────────────────────────────────────

@admin.register(TeamProfile)
class TeamProfileAdmin(admin.ModelAdmin):
    list_display = (
        'team_name', 'tactical_style',
        'avg_goals_scored', 'avg_goals_conceded',
        'home_accuracy_badge', 'away_accuracy_badge',
        'sample_size', 'updated_at',
    )
    list_filter = ('tactical_style',)
    search_fields = ('team_name',)
    readonly_fields = (
        'team_name', 'last_20_results', 'avg_goals_scored',
        'avg_goals_conceded', 'created_at', 'updated_at',
    )
    list_per_page = 50

    def home_accuracy_badge(self, obj):
        return format_html(
            '<span style="color:#00d4ff;font-weight:700;">{:.1f}%</span>',
            obj.home_accuracy,
        )
    home_accuracy_badge.short_description = 'Home Acc.'
    home_accuracy_badge.admin_order_field = 'home_accuracy'

    def away_accuracy_badge(self, obj):
        return format_html(
            '<span style="color:#a78bfa;font-weight:700;">{:.1f}%</span>',
            obj.away_accuracy,
        )
    away_accuracy_badge.short_description = 'Away Acc.'
    away_accuracy_badge.admin_order_field = 'away_accuracy'


# ─── PlayerProfile ────────────────────────────────────────────────────────────

@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'team', 'position',
        'overall_rating_badge', 'attack_rating', 'defense_rating',
        'injury_status_badge', 'appearances_this_season', 'updated_at',
    )
    list_filter = ('position', 'injury_status')
    search_fields = ('name', 'team')
    readonly_fields = (
        'name', 'goals_this_season', 'assists_this_season',
        'recent_ratings', 'raw_data', 'created_at', 'updated_at',
    )
    list_per_page = 50

    def overall_rating_badge(self, obj):
        r = obj.overall_rating
        if r >= 75:
            colour = '#10b981'
        elif r >= 55:
            colour = '#f59e0b'
        else:
            colour = '#94a3b8'
        return format_html(
            '<span style="color:{};font-weight:700;">{:.0f}</span>',
            colour, r,
        )
    overall_rating_badge.short_description = 'Rating'
    overall_rating_badge.admin_order_field = 'overall_rating'

    def injury_status_badge(self, obj):
        colours = {
            'fit':     ('#10b981', '✓ Fit'),
            'doubt':   ('#f59e0b', '⚠ Doubt'),
            'out':     ('#ef4444', '✗ Out'),
            'unknown': ('#94a3b8', '? Unknown'),
        }
        colour, label = colours.get(obj.injury_status, ('#94a3b8', obj.injury_status))
        return format_html(
            '<span style="color:{};font-weight:700;">{}</span>',
            colour, label,
        )
    injury_status_badge.short_description = 'Injury'
    injury_status_badge.admin_order_field = 'injury_status'


# ─── ConversationMemory ───────────────────────────────────────────────────────

@admin.register(ConversationMemory)
class ConversationMemoryAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'session_id', 'message_count', 'expires_at', 'updated_at')
    list_filter = ('expires_at',)
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 50

    def message_count(self, obj):
        return len(obj.messages) if obj.messages else 0
    message_count.short_description = '# Messages'

