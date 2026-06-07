from django.contrib import admin
from .models import (
    Prediction, TeamRanking, WeeklyTip,
    TeamProfile, EngineAccuracy, PredictionResult,
    WeightAdjustment, PatternMemory, PlayerProfile, ConversationMemory,
)


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'engine', 'home_team', 'away_team',
                    'predicted_result', 'confidence', 'was_correct', 'created_at')
    list_filter = ('engine', 'was_correct', 'created_at')
    search_fields = ('home_team', 'away_team', 'user__email')
    readonly_fields = ('created_at',)


@admin.register(TeamRanking)
class TeamRankingAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'power_elo', 'wins', 'draws', 'losses')
    search_fields = ('name',)


@admin.register(WeeklyTip)
class WeeklyTipAdmin(admin.ModelAdmin):
    list_display = ('home_team', 'away_team', 'competition', 'tip', 'confidence',
                    'is_pro_only', 'match_date')
    list_filter = ('is_pro_only', 'competition')


@admin.register(TeamProfile)
class TeamProfileAdmin(admin.ModelAdmin):
    list_display = ('team_name', 'tactical_style', 'avg_goals_scored',
                    'avg_goals_conceded', 'home_accuracy', 'away_accuracy',
                    'sample_size', 'updated_at')
    list_filter = ('tactical_style',)
    search_fields = ('team_name',)
    readonly_fields = ('updated_at', 'created_at')


@admin.register(EngineAccuracy)
class EngineAccuracyAdmin(admin.ModelAdmin):
    list_display = ('engine', 'match_type', 'accuracy_pct', 'weight_adjustment',
                    'sample_size', 'updated_at')
    list_filter = ('engine', 'match_type')
    readonly_fields = ('updated_at', 'created_at')


@admin.register(PredictionResult)
class PredictionResultAdmin(admin.ModelAdmin):
    list_display = ('prediction', 'actual_result', 'actual_score', 'was_correct',
                    'margin_of_error', 'result_source', 'result_checked_at')
    list_filter = ('was_correct', 'result_source')
    search_fields = ('prediction__home_team', 'prediction__away_team')
    readonly_fields = ('created_at',)


@admin.register(WeightAdjustment)
class WeightAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('engine', 'parameter', 'old_weight', 'new_weight',
                    'match_type', 'accuracy_before', 'accuracy_after', 'applied_at')
    list_filter = ('engine', 'match_type')
    readonly_fields = ('applied_at',)


@admin.register(PatternMemory)
class PatternMemoryAdmin(admin.ModelAdmin):
    list_display = ('pattern_type', 'pattern_key', 'accuracy', 'occurrences',
                    'min_sample', 'last_seen_at', 'last_updated')
    list_filter = ('pattern_type',)
    search_fields = ('pattern_key',)
    readonly_fields = ('last_updated', 'created_at')


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'team', 'position', 'overall_rating', 'injury_status',
                    'goals_this_season', 'assists_this_season', 'updated_at')
    list_filter = ('position', 'injury_status')
    search_fields = ('name', 'team')
    readonly_fields = ('updated_at', 'created_at')


@admin.register(ConversationMemory)
class ConversationMemoryAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'session_id', 'expires_at', 'updated_at')
    list_filter = ('expires_at',)
    readonly_fields = ('created_at', 'updated_at')
