"""
Custom Django admin actions for the predictions app.
"""
import csv
import json
from django.http import HttpResponse
from django.utils import timezone
from django.contrib import messages


def export_predictions_csv(modeladmin, request, queryset):
    """Export selected PredictionResult records to CSV."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="predictions_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Home Team', 'Away Team', 'Engine',
        'Predicted Result', 'Actual Result', 'Actual Score',
        'Was Correct', 'Margin of Error', 'Result Source', 'Created At',
    ])
    for obj in queryset.select_related('prediction'):
        p = obj.prediction
        writer.writerow([
            obj.id,
            getattr(p, 'home_team', ''),
            getattr(p, 'away_team', ''),
            getattr(p, 'engine', ''),
            getattr(p, 'predicted_result', ''),
            obj.actual_result,
            obj.actual_score,
            obj.was_correct,
            obj.margin_of_error,
            obj.result_source,
            obj.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])
    return response


export_predictions_csv.short_description = 'Export selected predictions to CSV'


def export_patterns_json(modeladmin, request, queryset):
    """Export selected PatternMemory records to JSON."""
    data = list(queryset.values(
        'pattern_type', 'pattern_key', 'pattern_value',
        'accuracy', 'occurrences', 'min_sample', 'last_seen_at',
    ))
    # Convert datetimes to strings for JSON serialisation
    for row in data:
        if row.get('last_seen_at'):
            row['last_seen_at'] = str(row['last_seen_at'])
    response = HttpResponse(
        json.dumps(data, indent=2),
        content_type='application/json',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="patterns_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'
    )
    return response


export_patterns_json.short_description = 'Export selected patterns to JSON'


def recalculate_accuracy(modeladmin, request, queryset):
    """
    Recalculate accuracy_pct for selected EngineAccuracy rows
    directly from PredictionResult records.
    """
    from .models import PredictionResult

    updated = 0
    for ea in queryset:
        qs = PredictionResult.objects.filter(
            prediction__engine=ea.engine,
            was_correct__isnull=False,
        )
        total = qs.count()
        if total == 0:
            continue
        correct = qs.filter(was_correct=True).count()
        ea.accuracy_pct = round(correct / total * 100, 2)
        ea.sample_size = total
        ea.save(update_fields=['accuracy_pct', 'sample_size', 'updated_at'])
        updated += 1

    messages.success(request, f'Recalculated accuracy for {updated} engine record(s).')


recalculate_accuracy.short_description = 'Recalculate accuracy from results'


def reset_weights(modeladmin, request, queryset):
    """Reset weight_adjustment to 1.0 for selected EngineAccuracy rows."""
    count = queryset.update(weight_adjustment=1.0)
    messages.success(request, f'Reset weight_adjustment to 1.0 for {count} record(s).')


reset_weights.short_description = 'Reset weight adjustments to 1.0'


def archive_old_data(modeladmin, request, queryset):
    """
    Mark old PatternMemory records as archived by setting occurrences to 0.
    (A soft-archive — they remain in the DB but won't be applied by the engine.)
    """
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=180)
    stale = queryset.filter(last_updated__lt=cutoff)
    count = stale.update(occurrences=0)
    messages.success(request, f'Archived {count} stale pattern(s) older than 180 days.')


archive_old_data.short_description = 'Archive stale patterns (>180 days old)'
