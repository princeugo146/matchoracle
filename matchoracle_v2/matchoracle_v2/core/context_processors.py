from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


def global_context(request):
    """Makes global variables available in all templates.

    IMPORTANT: This function is called on EVERY request. It must NOT make
    synchronous HTTP calls or do any blocking I/O. Live scores are fetched
    asynchronously by Celery tasks and stored in cache.
    """
    cfg = settings.MATCHORACLE

    # Read live_count from cache only - never make API calls here
    live_count = 0
    try:
        cached_scores = cache.get('live_scores_v2')
        if cached_scores:
            live_count = len([s for s in cached_scores if s.get('minute')])
    except Exception as exc:
        logger.warning("global_context: cache read failed: %s", exc)

    return {
        'CURRENCY_SYMBOL': cfg['CURRENCY_SYMBOL'],
        'PLANS': cfg['PLANS'],
        'APP_VERSION': cfg['VERSION'],
        'PAYSTACK_PUBLIC_KEY': cfg['PAYSTACK_PUBLIC_KEY'],
        'live_count': live_count,
    }
