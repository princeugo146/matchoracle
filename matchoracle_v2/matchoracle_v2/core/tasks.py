"""Celery tasks for MatchOracle.

All tasks degrade gracefully:
- If Redis unavailable: CELERY_TASK_ALWAYS_EAGER=True runs them synchronously
- If Celery unavailable: fallback to synchronous execution
- Every task catches exceptions so failures don't crash the app
"""
import logging
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

# ── LIVE SCORES ──────────────────────────────────────────────────────────────

@shared_task(bind=True, name='core.tasks.fetch_live_scores', max_retries=2, default_retry_delay=15, ignore_result=True)
def fetch_live_scores(self):
    """Fetch live scores from Football API and cache them.

    Scheduled every 60 seconds by Celery Beat. Context processor reads from
    this cache so it never blocks requests.
    """
    try:
        from core.live_scores import get_live_scores
        scores = get_live_scores()
        logger.info("fetch_live_scores: cached %d fixtures", len(scores))
        return len(scores)
    except Exception as exc:
        logger.error("fetch_live_scores failed: %s", exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.warning("fetch_live_scores: max retries exceeded")
        return 0

# ── EMAIL ─────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name='core.tasks.send_email_task', max_retries=3, default_retry_delay=30, ignore_result=True)
def send_email_task(self, subject, message, recipient_list, from_email=None):
    """Send transactional email asynchronously with retries."""
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
            logger.error("send_email_task: max retries exceeded for '%s'", subject)

# ── PAYMENT VERIFICATION ─────────────────────────────────────────────────────

@shared_task(bind=True, name='core.tasks.verify_payment_task', max_retries=5, default_retry_delay=60, ignore_result=False)
def verify_payment_task(self, reference, user_id):
    """Verify Paystack payment and activate subscription asynchronously."""
    import requests as http_requests
    from datetime import timedelta
    from django.utils import timezone

    try:
        from accounts.models import User, Payment
    except ImportError as exc:
        logger.error("verify_payment_task: import error: %s", exc)
        return {'success': False, 'message': 'Internal error'}

    cfg = settings.MATCHORACLE

    try:
        payment = Payment.objects.get(reference=reference)
    except Payment.DoesNotExist:
        logger.warning("verify_payment_task: payment %s not found", reference)
        return {'success': False, 'message': 'Payment not found'}

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
            return {'success': False, 'message': 'Paystack API unreachable'}

    if data.get('data', {}).get('status') != 'success':
        logger.info("verify_payment_task: payment %s not successful yet", reference)
        return {'success': False, 'message': 'Payment not confirmed'}

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

        # Send confirmation email
        send_email_task.delay(
            subject=f'MatchOracle {payment.plan.title()} Plan Active! ⚽',
            message=(
                f"Hi {user.first_name or user.username},\n\n"
                f"Your {payment.plan.title()} plan is now active!\n\n"
                f"Plan: {cfg['PLANS'][payment.plan]['name']}\n"
                f"Expires: {user.subscription_end.strftime('%d %B %Y')}\n\n"
                f"The MatchOracle Team"
            ),
            recipient_list=[user.email],
        )

        logger.info("verify_payment_task: activated %s plan for user %s", payment.plan, user_id)
        return {'success': True, 'message': f'{payment.plan.title()} plan activated'}
    except Exception as exc:
        logger.error("verify_payment_task: activation error: %s", exc, exc_info=True)
        return {'success': False, 'message': 'Activation failed'}

# ── PREDICTION OUTCOMES ───────────────────────────────────────────────────────

@shared_task(bind=True, name='core.tasks.update_prediction_outcomes', max_retries=2, default_retry_delay=120, ignore_result=True)
def update_prediction_outcomes(self):
    """Update prediction outcomes based on finished match results.

    Matches finished fixtures against pending Prediction records using the
    home_team/away_team fields and updates was_correct accordingly.
    """
    try:
        from predictions.models import Prediction
        from core.live_scores import get_live_scores

        scores = get_live_scores()
        # Build a lookup by (home, away) for finished matches
        finished = {
            (s['home'].lower(), s['away'].lower()): s
            for s in scores if s.get('status') == 'FT'
        }

        # Only process predictions that haven't been evaluated yet
        pending = Prediction.objects.filter(
            was_correct__isnull=True,
            home_team__gt='',
            away_team__gt='',
        ).exclude(predicted_result='')

        updated = 0
        for pred in pending:
            key = (pred.home_team.lower(), pred.away_team.lower())
            if key not in finished:
                continue

            result = finished[key]
            hg = result.get('home_score') or 0
            ag = result.get('away_score') or 0
            actual = 'home win' if hg > ag else ('away win' if ag > hg else 'draw')

            predicted = (pred.predicted_result or '').lower()
            pred.was_correct = (predicted == actual)
            pred.actual_result = actual
            pred.save(update_fields=['was_correct', 'actual_result'])
            updated += 1

        logger.info("update_prediction_outcomes: updated %d predictions", updated)
    except Exception as exc:
        logger.error("update_prediction_outcomes failed: %s", exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.warning("update_prediction_outcomes: max retries exceeded")
