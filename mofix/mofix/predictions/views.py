import json, logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from .models import Prediction, TeamRanking, WeeklyTip, TeamProfile, EngineAccuracy, PredictionResult
from .engine import engine_a, engine_b, compute_elo, engine_d, natural_language, get_confidence_badge

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    from core.live_scores import get_live_scores
    from core.models import WeeklyForecast
    user = request.user
    recent = Prediction.objects.filter(user=user)[:8]
    rankings = TeamRanking.objects.filter(user=user)[:10]
    tips = WeeklyTip.objects.filter(is_pro_only=False)[:3]
    forecasts = WeeklyForecast.objects.filter(is_published=True)[:4]
    live_scores = get_live_scores()[:4]
    plan_info = settings.MATCHORACLE['PLANS'].get(user.plan, {})
    stats = {
        'total': Prediction.objects.filter(user=user).count(),
        'accuracy': user.accuracy_rate,
        'left_today': user.predictions_left_today,
        'limit': plan_info.get('predictions_per_day', 3),
    }
    return render(request, 'predictions/dashboard.html', {
        'recent': recent, 'rankings': rankings, 'stats': stats,
        'tips': tips, 'forecasts': forecasts, 'live_scores': live_scores,
        'plan_info': plan_info,
    })

@login_required
def run_engine(request, engine):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    user = request.user

    # Reset counter if new day
    today = timezone.now().date()
    if user.predictions_date != today:
        user.predictions_today = 0
        user.predictions_date = today
        user.save(update_fields=['predictions_today', 'predictions_date'])

    if not user.can_predict:
        plan_info = settings.MATCHORACLE['PLANS'].get(user.plan, {})
        limit = plan_info.get('predictions_per_day', 3)
        return JsonResponse({
            'error': 'daily_limit_reached',
            'message': f'You have used all {limit} predictions for today. Upgrade for more!',
        }, status=429)

    try:
        input_data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        result = None
        home_team = ''; away_team = ''; predicted_result = ''
        if engine == 'A':
            result = engine_a(input_data)
            home_team = input_data.get('home', {}).get('name', '')
            away_team = input_data.get('away', {}).get('name', '')
            predicted_result = result.get('verdict', '')
        elif engine == 'B':
            result = engine_b(input_data)
            predicted_result = f"{result.get('tier','')} ({result.get('rating',0)})"
        elif engine == 'D':
            result = engine_d(input_data)
            home_team = input_data.get('home', {}).get('name', '')
            away_team = input_data.get('away', {}).get('name', '')
            predicted_result = result.get('likely_score', '')
        elif engine == 'NL':
            result = natural_language(input_data.get('question', ''))
            predicted_result = result.get('prediction', '')
            if result and 'confidence' in result and 'confidence_badge' not in result:
                result['confidence_badge'] = get_confidence_badge(result['confidence'])
        else:
            return JsonResponse({'error': 'Invalid engine'}, status=400)

        if result:
            pred_obj = Prediction.objects.create(
                user=user, engine=engine, input_data=input_data,
                output_data=result, confidence=result.get('confidence', 0),
                home_team=home_team, away_team=away_team,
                predicted_result=predicted_result,
            )
            user.predictions_today += 1
            user.total_predictions += 1
            user.save(update_fields=['predictions_today', 'total_predictions'])
            # Queue a deferred result check (runs ~2 days later via Celery)
            if engine in ('A', 'NL') and home_team and away_team:
                try:
                    from .learning_tasks import queue_result_check
                    queue_result_check(pred_obj.id)
                except Exception:
                    pass  # learning is optional — never block the response
            return JsonResponse({
                'success': True,
                'result': result,
                'predictions_left': user.predictions_left_today,
            })
    except Exception as e:
        logger.error(f"Engine {engine} error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def add_ranking(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Name required'}, status=400)
        wins = int(data.get('wins', 0)); draws = int(data.get('draws', 0))
        losses = int(data.get('losses', 0)); gf = int(data.get('goals_for', 0))
        ga = int(data.get('goals_against', 0)); opp = float(data.get('opp_strength', 5))
        base = int(data.get('base_elo', 1000))
        elo = compute_elo(wins, draws, losses, gf, ga, opp, base)
        TeamRanking.objects.update_or_create(
            user=request.user, name=name,
            defaults={'power_elo': elo, 'wins': wins, 'draws': draws,
                      'losses': losses, 'goals_for': gf, 'goals_against': ga}
        )
        rankings = list(TeamRanking.objects.filter(user=request.user).values(
            'name', 'power_elo', 'wins', 'draws', 'losses', 'goals_for', 'goals_against'
        ))
        return JsonResponse({'success': True, 'rankings': rankings})
    except Exception as e:
        logger.error(f"Ranking error: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def history(request):
    predictions = Prediction.objects.filter(user=request.user)[:50]
    return render(request, 'predictions/history.html', {
        'predictions': predictions,
        'stats': {'total': predictions.count(), 'accuracy': request.user.accuracy_rate}
    })

@login_required
def tips(request):
    free_tips = WeeklyTip.objects.filter(is_pro_only=False)[:10]
    pro_tips = WeeklyTip.objects.filter(is_pro_only=True)[:10] if request.user.plan == 'pro' else []
    return render(request, 'predictions/tips.html', {
        'free_tips': free_tips, 'pro_tips': pro_tips,
        'is_pro': request.user.plan == 'pro',
    })

@login_required
def smart_ai(request):
    """Handle smart AI natural language predictions"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    user = request.user

    # Reset counter if new day
    today = timezone.now().date()
    if user.predictions_date != today:
        user.predictions_today = 0
        user.predictions_date = today
        user.save(update_fields=['predictions_today', 'predictions_date'])

    if not user.can_predict:
        plan_info = settings.MATCHORACLE['PLANS'].get(user.plan, {})
        limit = plan_info.get('predictions_per_day', 3)
        return JsonResponse({
            'error': 'daily_limit_reached',
            'message': f'You have used all {limit} predictions for today. Upgrade for more!',
        }, status=429)

    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
        if not question:
            return JsonResponse({'error': 'Please ask a question'}, status=400)

        from .smart_ai import smart_predict
        result = smart_predict(question)

        # Attach confidence badge if not already present
        if result and 'confidence' in result and 'confidence_badge' not in result:
            result['confidence_badge'] = get_confidence_badge(result['confidence'])

        # Save as prediction
        nl_pred = Prediction.objects.create(
            user=user,
            engine='NL',
            input_data={'question': question},
            output_data=result,
            confidence=result.get('confidence', 0),
            home_team=result.get('home_team', '') or '',
            away_team=result.get('away_team', '') or '',
            predicted_result=result.get('verdict', '') or result.get('answer', '')[:50],
        )

        # Store conversation context in ConversationMemory
        try:
            from .models import ConversationMemory
            from .learning_utils import make_session_id
            session_id = make_session_id(request)
            mem = ConversationMemory.get_or_create_session(user.id, session_id)
            mem.add_message(
                question=question,
                answer=result.get('answer', ''),
                intent=result.get('intent', 'general'),
            )
            # Update context with any teams/competition detected
            ctx_update = {}
            if result.get('home_team') and result.get('away_team'):
                ctx_update['teams'] = [result['home_team'], result['away_team']]
            if result.get('competition'):
                ctx_update['competition'] = result['competition']
            if ctx_update:
                mem.update_context(ctx_update)
        except Exception:
            pass  # memory is optional — never block the response

        # Queue a deferred result check (runs ~2 days later via Celery)
        home_t = result.get('home_team', '') or ''
        away_t = result.get('away_team', '') or ''
        if home_t and away_t:
            try:
                from .learning_tasks import queue_result_check
                queue_result_check(nl_pred.id)
            except Exception:
                pass

        # Update counter
        user.predictions_today += 1
        user.total_predictions += 1
        user.save(update_fields=['predictions_today', 'total_predictions'])

        return JsonResponse({
            'success': True,
            'result': result,
            'predictions_left': user.predictions_left_today,
        })

    except Exception as e:
        logger.error(f"Smart AI error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


# ─── Self-Learning API Endpoints ──────────────────────────────────────────────

@login_required
def team_profile(request, team_name):
    """
    GET /predictions/team-profile/<team_name>/

    Returns the learned profile for a team: recent form, goal averages,
    tactical style, accuracy stats, and key players.
    """
    try:
        profile = TeamProfile.objects.get(team_name__iexact=team_name)
        return JsonResponse({
            'success': True,
            'team_name': profile.team_name,
            'avg_goals_scored': profile.avg_goals_scored,
            'avg_goals_conceded': profile.avg_goals_conceded,
            'tactical_style': profile.tactical_style,
            'key_players': profile.key_players,
            'last_20_results': profile.last_20_results,
            'home_accuracy': profile.home_accuracy,
            'away_accuracy': profile.away_accuracy,
            'vs_style_accuracy': profile.vs_style_accuracy,
            'sample_size': profile.sample_size,
            'updated_at': profile.updated_at.isoformat(),
        })
    except TeamProfile.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f"No profile found for '{team_name}'. "
                     "Profiles are built automatically after predictions are made.",
        }, status=404)
    except Exception as e:
        logger.error(f"team_profile error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def engine_accuracy(request, engine):
    """
    GET /predictions/engine-accuracy/<engine>/

    Returns accuracy statistics for a prediction engine (A, B, D, or NL),
    broken down by match type.
    """
    engine = engine.upper()
    valid_engines = ['A', 'B', 'D', 'NL']
    if engine not in valid_engines:
        return JsonResponse(
            {'error': f"Invalid engine '{engine}'. Choose from: {valid_engines}"},
            status=400,
        )

    try:
        records = EngineAccuracy.objects.filter(engine=engine)
        if not records.exists():
            return JsonResponse({
                'success': True,
                'engine': engine,
                'message': 'No accuracy data yet. Data accumulates after 10+ verified predictions.',
                'records': [],
            })

        data = []
        for r in records:
            data.append({
                'match_type': r.match_type,
                'accuracy_pct': r.accuracy_pct,
                'home_accuracy': r.home_accuracy,
                'away_accuracy': r.away_accuracy,
                'draw_accuracy': r.draw_accuracy,
                'weight_adjustment': r.weight_adjustment,
                'tactical_matchup_accuracy': r.tactical_matchup_accuracy,
                'sample_size': r.sample_size,
                'updated_at': r.updated_at.isoformat(),
            })

        overall_acc = (
            sum(r['accuracy_pct'] * r['sample_size'] for r in data)
            / max(sum(r['sample_size'] for r in data), 1)
        )

        return JsonResponse({
            'success': True,
            'engine': engine,
            'overall_accuracy_pct': round(overall_acc, 2),
            'total_predictions': sum(r['sample_size'] for r in data),
            'records': data,
        })
    except Exception as e:
        logger.error(f"engine_accuracy error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def prediction_result(request, prediction_id):
    """
    GET /predictions/<prediction_id>/result/

    Returns the actual result for a prediction alongside the original
    prediction, so users can see how accurate the system was.
    """
    try:
        pred = Prediction.objects.get(id=prediction_id, user=request.user)
    except Prediction.DoesNotExist:
        return JsonResponse({'error': 'Prediction not found'}, status=404)

    try:
        pr = pred.result_record
        return JsonResponse({
            'success': True,
            'prediction_id': pred.id,
            'home_team': pred.home_team,
            'away_team': pred.away_team,
            'predicted_result': pred.predicted_result,
            'predicted_score': pred.output_data.get('predicted_score', ''),
            'confidence': pred.confidence,
            'created_at': pred.created_at.isoformat(),
            'actual_result': pr.actual_result,
            'actual_score': pr.actual_score,
            'was_correct': pr.was_correct,
            'margin_of_error': pr.margin_of_error,
            'result_source': pr.result_source,
            'result_checked_at': pr.result_checked_at.isoformat() if pr.result_checked_at else None,
        })
    except PredictionResult.DoesNotExist:
        return JsonResponse({
            'success': True,
            'prediction_id': pred.id,
            'home_team': pred.home_team,
            'away_team': pred.away_team,
            'predicted_result': pred.predicted_result,
            'predicted_score': pred.output_data.get('predicted_score', ''),
            'confidence': pred.confidence,
            'created_at': pred.created_at.isoformat(),
            'actual_result': None,
            'actual_score': None,
            'was_correct': None,
            'message': 'Result not yet available. The system checks results 2–3 days after the match.',
        })
    except Exception as e:
        logger.error(f"prediction_result error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
