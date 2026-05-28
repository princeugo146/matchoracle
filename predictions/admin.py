from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Count, Avg, Q
from django.urls import path
from django.shortcuts import render
from django.contrib.admin import SimpleListFilter
from django.utils import timezone
from datetime import timedelta

from .models import (
    Prediction, TeamRanking, WeeklyTip,
    TeamProfile, EngineAccuracy, PredictionResult,
    WeightAdjustment, PatternMemory, PlayerProfile,
)


# ─── Filters ──────────────────────────────────────────────────────────────────

class AccuracyFilter(SimpleListFilter):
    title = 'accuracy range'
    parameter_name = 'accuracy_range'

    def lookups(self, request, model_admin):
        return [
            ('high',   'High (≥70%)'),
            ('medium', 'Medium (40–69%)'),
            ('low',    'Low (<40%)'),
        ]

    def queryset(self, request, queryset):
        val = self.value()
        if val == 'high':
            return queryset.filter(accuracy_pct__gte=70)
        if val == 'medium':
            return queryset.filter(accuracy_pct__gte=40, accuracy_pct__lt=70)
        if val == 'low':
            return queryset.filter(accuracy_pct__lt=40)
        return queryset


class ReliablePatternFilter(SimpleListFilter):
    title = 'reliability'
    parameter_name = 'reliable'

    def lookups(self, request, model_admin):
        return [('yes', 'Reliable (≥ min_sample)'), ('no', 'Not yet reliable')]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            from django.db.models import F
            return queryset.filter(occurrences__gte=F('min_sample'))
        if self.value() == 'no':
            from django.db.models import F
            return queryset.filter(occurrences__lt=F('min_sample'))
        return queryset


# ─── Prediction ───────────────────────────────────────────────────────────────

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user_email', 'engine_badge', 'match_display',
        'predicted_result', 'confidence_bar', 'correctness_badge', 'created_at',
    )
    list_filter = ('engine', 'was_correct', 'created_at')
    search_fields = ('user__email', 'home_team', 'away_team', 'predicted_result')
    readonly_fields = ('created_at', 'input_data', 'output_data')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 50

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'

    def engine_badge(self, obj):
        colours = {'A': '#00d4ff', 'B': '#a78bfa', 'C': '#10b981', 'D': '#fb923c', 'NL': '#f472b6'}
        c = colours.get(obj.engine, '#94a3b8')
        return format_html(
            '<span style="background:{};color:#030508;padding:2px 8px;border-radius:12px;'
            'font-size:11px;font-weight:700">{}</span>', c, obj.get_engine_display()
        )
    engine_badge.short_description = 'Engine'

    def match_display(self, obj):
        if obj.home_team and obj.away_team:
            return f'{obj.home_team} vs {obj.away_team}'
        return '—'
    match_display.short_description = 'Match'

    def confidence_bar(self, obj):
        pct = obj.confidence
        colour = '#10b981' if pct >= 70 else '#f59e0b' if pct >= 50 else '#ef4444'
        return format_html(
            '<div style="width:80px;background:#1a2332;border-radius:4px;height:8px">'
            '<div style="width:{}%;background:{};height:8px;border-radius:4px"></div></div>'
            '<span style="font-size:11px;color:{}">{} %</span>',
            min(pct, 100), colour, colour, pct
        )
    confidence_bar.short_description = 'Confidence'

    def correctness_badge(self, obj):
        if obj.was_correct is True:
            return format_html('<span style="color:#10b981;font-weight:700">✓ Correct</span>')
        if obj.was_correct is False:
            return format_html('<span style="color:#ef4444;font-weight:700">✗ Wrong</span>')
        return format_html('<span style="color:#94a3b8">Pending</span>')
    correctness_badge.short_description = 'Result'


# ─── EngineAccuracy ───────────────────────────────────────────────────────────

@admin.register(EngineAccuracy)
class EngineAccuracyAdmin(admin.ModelAdmin):
    list_display = (
        'engine', 'match_type', 'accuracy_display', 'home_accuracy',
        'away_accuracy', 'draw_accuracy', 'sample_size', 'weight_adjustment', 'updated_at',
    )
    list_filter = ('engine', 'match_type', AccuracyFilter)
    readonly_fields = ('updated_at', 'created_at', 'tactical_matchup_accuracy')
    ordering = ('engine', 'match_type')

    def accuracy_display(self, obj):
        pct = obj.accuracy_pct
        colour = '#10b981' if pct >= 70 else '#f59e0b' if pct >= 50 else '#ef4444'
        return format_html(
            '<strong style="color:{};font-size:14px">{:.1f}%</strong>', colour, pct
        )
    accuracy_display.short_description = 'Accuracy'
    accuracy_display.admin_order_field = 'accuracy_pct'


# ─── WeightAdjustment ─────────────────────────────────────────────────────────

@admin.register(WeightAdjustment)
class WeightAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'engine', 'parameter', 'old_weight', 'new_weight',
        'delta_display', 'match_type', 'improvement_badge', 'applied_at',
    )
    list_filter = ('engine', 'match_type', 'applied_at')
    search_fields = ('parameter', 'reason')
    readonly_fields = ('applied_at', 'delta_display')
    date_hierarchy = 'applied_at'
    ordering = ('-applied_at',)

    def delta_display(self, obj):
        d = obj.delta
        colour = '#10b981' if d > 0 else '#ef4444' if d < 0 else '#94a3b8'
        sign = '+' if d > 0 else ''
        return format_html('<span style="color:{};font-weight:700">{}{:.4f}</span>', colour, sign, d)
    delta_display.short_description = 'Δ Weight'

    def improvement_badge(self, obj):
        imp = obj.improved
        if imp is True:
            return format_html('<span style="color:#10b981;font-weight:700">↑ Improved</span>')
        if imp is False:
            return format_html('<span style="color:#ef4444;font-weight:700">↓ Declined</span>')
        return format_html('<span style="color:#94a3b8">—</span>')
    improvement_badge.short_description = 'Impact'


# ─── PatternMemory ────────────────────────────────────────────────────────────

@admin.register(PatternMemory)
class PatternMemoryAdmin(admin.ModelAdmin):
    list_display = (
        'pattern_type', 'pattern_key', 'accuracy_display',
        'occurrences', 'min_sample', 'reliability_badge', 'last_seen_at',
    )
    list_filter = ('pattern_type', ReliablePatternFilter)
    search_fields = ('pattern_key',)
    readonly_fields = ('created_at', 'last_updated', 'pattern_value')
    ordering = ('-occurrences', '-accuracy')

    def accuracy_display(self, obj):
        colour = '#10b981' if obj.accuracy >= 70 else '#f59e0b' if obj.accuracy >= 50 else '#ef4444'
        return format_html('<strong style="color:{}">{:.1f}%</strong>', colour, obj.accuracy)
    accuracy_display.short_description = 'Accuracy'

    def reliability_badge(self, obj):
        if obj.is_reliable():
            return format_html('<span style="color:#10b981;font-weight:700">✓ Reliable</span>')
        remaining = obj.min_sample - obj.occurrences
        return format_html('<span style="color:#f59e0b">Need {} more</span>', remaining)
    reliability_badge.short_description = 'Reliability'


# ─── TeamProfile ──────────────────────────────────────────────────────────────

@admin.register(TeamProfile)
class TeamProfileAdmin(admin.ModelAdmin):
    list_display = (
        'team_name', 'tactical_style', 'avg_goals_scored', 'avg_goals_conceded',
        'home_accuracy', 'away_accuracy', 'sample_size', 'updated_at',
    )
    list_filter = ('tactical_style',)
    search_fields = ('team_name',)
    readonly_fields = ('updated_at', 'created_at', 'last_20_results', 'vs_style_accuracy', 'key_players', 'injury_history')
    ordering = ('team_name',)

    fieldsets = (
        ('Identity', {'fields': ('team_name', 'tactical_style', 'key_players')}),
        ('Scoring', {'fields': ('avg_goals_scored', 'avg_goals_conceded')}),
        ('Accuracy', {'fields': ('home_accuracy', 'away_accuracy', 'vs_style_accuracy', 'sample_size')}),
        ('History', {'fields': ('last_20_results', 'injury_history')}),
        ('Timestamps', {'fields': ('updated_at', 'created_at')}),
    )


# ─── PlayerProfile ────────────────────────────────────────────────────────────

@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'team', 'position', 'overall_rating_display',
        'injury_status_badge', 'goals_this_season', 'assists_this_season',
        'appearances_this_season', 'prediction_impact', 'updated_at',
    )
    list_filter = ('position', 'injury_status', 'team')
    search_fields = ('name', 'team')
    readonly_fields = ('updated_at', 'created_at', 'recent_ratings', 'injury_history', 'raw_data')
    ordering = ('-overall_rating', 'name')

    fieldsets = (
        ('Identity', {'fields': ('name', 'team', 'position')}),
        ('Season Stats', {'fields': ('goals_this_season', 'assists_this_season', 'appearances_this_season')}),
        ('Ratings', {'fields': ('attack_rating', 'defense_rating', 'overall_rating', 'prediction_impact', 'recent_ratings')}),
        ('Injury', {'fields': ('injury_status', 'injury_history')}),
        ('Raw Data', {'fields': ('raw_data',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('updated_at', 'created_at')}),
    )

    def overall_rating_display(self, obj):
        r = obj.overall_rating
        colour = '#10b981' if r >= 75 else '#f59e0b' if r >= 55 else '#ef4444'
        return format_html('<strong style="color:{};font-size:14px">{:.0f}</strong>', colour, r)
    overall_rating_display.short_description = 'Rating'
    overall_rating_display.admin_order_field = 'overall_rating'

    def injury_status_badge(self, obj):
        colours = {'fit': '#10b981', 'doubt': '#f59e0b', 'out': '#ef4444', 'unknown': '#94a3b8'}
        c = colours.get(obj.injury_status, '#94a3b8')
        return format_html(
            '<span style="color:{};font-weight:700;text-transform:uppercase">{}</span>',
            c, obj.injury_status
        )
    injury_status_badge.short_description = 'Status'


# ─── PredictionResult ─────────────────────────────────────────────────────────

@admin.register(PredictionResult)
class PredictionResultAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'prediction_link', 'actual_result', 'actual_score',
        'correctness_badge', 'margin_of_error', 'result_source', 'result_checked_at',
    )
    list_filter = ('was_correct', 'result_source', 'result_checked_at')
    search_fields = (
        'prediction__home_team', 'prediction__away_team',
        'actual_result', 'actual_score',
    )
    readonly_fields = ('created_at', 'raw_data', 'prediction')
    date_hierarchy = 'result_checked_at'
    ordering = ('-created_at',)
    actions = ['mark_correct', 'mark_wrong']

    def prediction_link(self, obj):
        p = obj.prediction
        label = f'{p.home_team} vs {p.away_team}' if p.home_team else f'Pred #{p.id}'
        return format_html(
            '<a href="/admin/predictions/prediction/{}/change/">{}</a>', p.id, label
        )
    prediction_link.short_description = 'Prediction'

    def correctness_badge(self, obj):
        if obj.was_correct is True:
            return format_html('<span style="color:#10b981;font-weight:700">✓ Correct</span>')
        if obj.was_correct is False:
            return format_html('<span style="color:#ef4444;font-weight:700">✗ Wrong</span>')
        return format_html('<span style="color:#94a3b8">Pending</span>')
    correctness_badge.short_description = 'Correct?'

    @admin.action(description='Mark selected results as correct')
    def mark_correct(self, request, queryset):
        updated = queryset.update(was_correct=True)
        # Sync back to Prediction.was_correct
        for pr in queryset:
            pr.prediction.was_correct = True
            pr.prediction.save(update_fields=['was_correct'])
        self.message_user(request, f'{updated} result(s) marked as correct.')

    @admin.action(description='Mark selected results as wrong')
    def mark_wrong(self, request, queryset):
        updated = queryset.update(was_correct=False)
        for pr in queryset:
            pr.prediction.was_correct = False
            pr.prediction.save(update_fields=['was_correct'])
        self.message_user(request, f'{updated} result(s) marked as wrong.')


# ─── TeamRanking & WeeklyTip (keep existing) ──────────────────────────────────

@admin.register(TeamRanking)
class TeamRankingAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'power_elo', 'wins', 'draws', 'losses', 'goals_for', 'goals_against')
    list_filter = ('user',)
    search_fields = ('name', 'user__email')
    ordering = ('-power_elo',)


@admin.register(WeeklyTip)
class WeeklyTipAdmin(admin.ModelAdmin):
    list_display = ('home_team', 'away_team', 'competition', 'tip', 'confidence', 'is_pro_only', 'match_date')
    list_filter = ('is_pro_only', 'competition')
    search_fields = ('home_team', 'away_team', 'tip')
    ordering = ('-match_date',)


# ─── Custom Admin Dashboard ───────────────────────────────────────────────────

class PredictionsAdminSite(admin.AdminSite):
    """Extend the default admin site with a custom dashboard summary."""
    pass


# Inject a custom index view into the default admin site
_original_index = admin.site.__class__.index

def _custom_index(self, request, extra_context=None):
    extra_context = extra_context or {}
    try:
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        total_preds = Prediction.objects.count()
        verified = Prediction.objects.filter(was_correct__isnull=False).count()
        correct = Prediction.objects.filter(was_correct=True).count()
        overall_accuracy = round(correct / verified * 100, 1) if verified else 0

        engine_stats = (
            EngineAccuracy.objects
            .values('engine')
            .annotate(avg_acc=Avg('accuracy_pct'), total=Count('id'))
            .order_by('-avg_acc')
        )

        recent_adjustments = WeightAdjustment.objects.select_related().order_by('-applied_at')[:5]
        reliable_patterns = PatternMemory.objects.filter(occurrences__gte=5).count()
        pending_results = PredictionResult.objects.filter(was_correct__isnull=True).count()
        week_preds = Prediction.objects.filter(created_at__gte=week_ago).count()

        extra_context.update({
            'dashboard_stats': {
                'total_predictions': total_preds,
                'week_predictions': week_preds,
                'overall_accuracy': overall_accuracy,
                'verified_predictions': verified,
                'reliable_patterns': reliable_patterns,
                'pending_results': pending_results,
                'engine_stats': list(engine_stats),
                'recent_adjustments': recent_adjustments,
            }
        })
    except Exception:
        pass  # Never crash the admin
    return _original_index(self, request, extra_context)

admin.site.__class__.index = _custom_index
admin.site.site_header = 'MatchOracle Admin'
admin.site.site_title = 'MatchOracle'
admin.site.index_title = 'System Dashboard'

