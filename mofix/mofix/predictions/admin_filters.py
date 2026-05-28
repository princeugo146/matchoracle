"""
Custom Django admin list filters for the predictions app.
"""
from django.contrib.admin import SimpleListFilter
from django.utils import timezone
from datetime import timedelta


class DateRangeFilter(SimpleListFilter):
    title = 'date range'
    parameter_name = 'date_range'

    def lookups(self, request, model_admin):
        return [
            ('today',   'Today'),
            ('week',    'Last 7 days'),
            ('month',   'Last 30 days'),
            ('quarter', 'Last 90 days'),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        mapping = {
            'today':   now - timedelta(days=1),
            'week':    now - timedelta(days=7),
            'month':   now - timedelta(days=30),
            'quarter': now - timedelta(days=90),
        }
        cutoff = mapping.get(self.value())
        if cutoff:
            return queryset.filter(created_at__gte=cutoff)
        return queryset


class EngineFilter(SimpleListFilter):
    title = 'engine'
    parameter_name = 'engine_filter'

    def lookups(self, request, model_admin):
        return [
            ('A',  'Match (A)'),
            ('B',  'Player (B)'),
            ('D',  'Simulation (D)'),
            ('NL', 'AI (NL)'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(engine=self.value())
        return queryset


class MatchTypeFilter(SimpleListFilter):
    title = 'match type'
    parameter_name = 'match_type_filter'

    def lookups(self, request, model_admin):
        return [
            ('league',    'League'),
            ('cup',       'Cup'),
            ('champions', 'Champions League'),
            ('friendly',  'Friendly'),
            ('knockout',  'Knockout'),
            ('final',     'Final'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(match_type=self.value())
        return queryset


class AccuracyRangeFilter(SimpleListFilter):
    title = 'accuracy range'
    parameter_name = 'accuracy_range'

    def lookups(self, request, model_admin):
        return [
            ('high',   'High (≥70%)'),
            ('medium', 'Medium (55–69%)'),
            ('low',    'Low (<55%)'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'high':
            return queryset.filter(accuracy_pct__gte=70)
        if self.value() == 'medium':
            return queryset.filter(accuracy_pct__gte=55, accuracy_pct__lt=70)
        if self.value() == 'low':
            return queryset.filter(accuracy_pct__lt=55)
        return queryset


class PatternTypeFilter(SimpleListFilter):
    title = 'pattern type'
    parameter_name = 'pattern_type_filter'

    def lookups(self, request, model_admin):
        return [
            ('team',      'Team Pattern'),
            ('player',    'Player Pattern'),
            ('matchup',   'Tactical Matchup'),
            ('condition', 'Match Condition'),
            ('h2h',       'Head-to-Head'),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(pattern_type=self.value())
        return queryset
