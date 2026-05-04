"""Celery tasks for MatchOracle core functionality.

All tasks are designed to degrade gracefully:
- If Redis / Celery is unavailable, CELERY_TASK_ALWAYS_EAGER=True means they
  run synchronously in the calling process.
- Every task catches its own exceptions and logs them so a failure in a
  background task never propagates to the HTTP request cycle.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


# ── LIVE SCORES ──────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name='core.tasks.fetch_live_scores',
    max_retries=2,
    default_retry_delay=15,
    ignore_result=True,
)
def fetch_live_scores(self):
    """Fetch live scores from the Football API and store them in the cache.

    Scheduled every 60 s by Celery Beat (see CELERY_BEAT_SCHEDULE in
    settings.py).  The context processor reads from this cache key so it
    never blocks an HTTP request.
    """
    try:
        from core.live_scores import get_live_scores  # local import avoids circular deps
        scores = get_live_scores()
        logger.info("fetch_live_scores: cached %d fixtures", len(scores))
        return len(scores)
    except Exception as exc:
        logger.error("fetch_live_scores failed: %s", exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.warning("fetch_live_scores: max retries exceeded, giving up")
        return 0


# ── EMAIL ─────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name='core.tasks.send_email_task',
    max_retries=3,
    default_retry_delay=30,
    ignore_result=True,
)
def send_email_task(self, subject, message, recipient_list, from_email=None):
    """Send a transactional email asynchronously.

    Falls back to fail_silently=True so a broken SMTP config never crashes
    the worker.
    """
    if from_email is None:
        from_email = settings.DEFAULT_FROM_EMAIL
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info("send_email_task: sent '%s' to %s", subject, recipient_list)
    except Exception as exc:
        logger.error("send_email_task failed (attempt %d): %s", self.request.retries + 1, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                "send_email_task: max retries exceeded for '%s' → %s",
                subject, recipient_list,
            )


# ── PAYMENT VERIFICATION ─────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name='core.tasks.verify_payment_task',
    max_retries=5,
    default_retry_delay=60,
    ignore_result=False,
)
def verify_payment_task(self, reference, user_id):
    """Verify a Paystack payment reference and activate the user's subscription.

    Returns a dict with keys ``success`` (bool) and ``message`` (str).
    The view should poll this task result or use a webhook instead of waiting
    synchronously.
    """
    import requests as http_requests
    from datetime import timedelta
    from django.utils import timezone

    try:
        from accounts.models import User, Payment  # avoid top-level circular import
    except ImportError as exc:
        logger.error("verify_payment_task: import error: %s", exc)
        return {'success': False, 'message': 'Internal import error'}

    cfg = settings.MATCHORACLE

    try:
        payment = Payment.objects.get(reference=reference)
    except Payment.DoesNotExist:
        logger.warning("verify_payment_task: payment %s not found", reference)
        return {'success': False, 'message': 'Payment record not found'}

    try:
        headers = {'Authorization': f'Bearer {cfg["PAYSTACK_SECRET_KEY"]}'}
        resp = http_requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("verify_payment_task: Paystack API error for %s: %s", reference, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {'success': False, 'message': 'Paystack API unreachable after retries'}

    if data.get('data', {}).get('status') != 'success':
        logger.info("verify_payment_task: payment %s not successful yet", reference)
        return {'success': False, 'message': 'Payment not confirmed by Paystack'}

    # Activate subscription
    try:
        user = User.objects.get(pk=user_id)
        payment.status = 'success'
        payment.verified_at = timezone.now()
        payment.save()

        plan_days = cfg['PLANS'][payment.plan]['duration_days']
        user.plan = payment.plan
        user.subscription_start = timezone.now()
        user.subscription_end = timezone.now() + timedelta(days=plan_days)
        user.save()

        # Send confirmation email asynchronously (chain another task)
        send_email_task.delay(
            subject=f'MatchOracle {payment.plan.title()} Plan Active! ⚽',
            message=_subscription_email_body(user, payment.plan, cfg),
            recipient_list=[user.email],
        )

        logger.info(
            "verify_payment_task: activated %s plan for user %s (ref=%s)",
            payment.plan, user_id, reference,
        )
        return {'success': True, 'message': f'{payment.plan.title()} plan activated'}
    except Exception as exc:
        logger.error("verify_payment_task: activation error for %s: %s", reference, exc, exc_info=True)
        return {'success': False, 'message': 'Subscription activation failed'}


# ── PREDICTION UPDATES ────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name='core.tasks.update_prediction_outcomes',
    max_retries=2,
    default_retry_delay=120,
    ignore_result=True,
)
def update_prediction_outcomes(self):
    """Update the outcome field on pending Prediction records.

    Compares stored predictions against live/finished fixture results and
    marks each prediction as 'correct', 'incorrect', or leaves it 'pending'.
    """
    try:
        from predictions.models import Prediction  # avoid top-level circular import
        from core.live_scores import get_live_scores

        scores = get_live_scores()
        finished = {s['id']: s for s in scores if s.get('status') == 'FT'}

        pending = Prediction.objects.filter(outcome='pending').select_related('user')
        updated = 0
        for pred in pending:
            fixture_id = pred.input_data.get('fixture_id') if pred.input_data else None
            if fixture_id and fixture_id in finished:
                result = finished[fixture_id]
                # Simple home/draw/away outcome check
                hg = result.get('home_score', 0) or 0
                ag = result.get('away_score', 0) or 0
                actual = 'home' if hg > ag else ('away' if ag > hg else 'draw')
                predicted = (pred.result or {}).get('verdict', '').lower()
                if predicted in ('home win', 'home'):
                    predicted_norm = 'home'
                elif predicted in ('away win', 'away'):
                    predicted_norm = 'away'
                else:
                    predicted_norm = 'draw'
                pred.outcome = 'correct' if predicted_norm == actual else 'incorrect'
                pred.save(update_fields=['outcome'])
                updated += 1

        logger.info("update_prediction_outcomes: updated %d predictions", updated)
    except Exception as exc:
        logger.error("update_prediction_outcomes failed: %s", exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.warning("update_prediction_outcomes: max retries exceeded")


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _subscription_email_body(user, plan, cfg):
    plan_info = cfg['PLANS'][plan]
    return f"""Hi {user.first_name or user.username},

Your {plan_info['name']} subscription is now ACTIVE!

Plan: {plan_info['name']}
Expires: {user.subscription_end.strftime('%d %B %Y')}
Predictions/day: {plan_info['predictions_per_day']}
API Access: {'Yes' if plan_info['api_access'] else 'No'}

Your API Key: {user.api_key}

The MatchOracle Team
"""
