import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def global_context(request):
    """Makes global variables available in all templates.

    live_count is served from cache only — never from a blocking API call.
    The cache is populated by the fetch_live_scores Celery task (or the
    /api/scores/ endpoint on first client-side request).  If the cache is
    cold the value defaults to 0 so that template rendering is never blocked
    by an external HTTP call.
    """
    cfg = settings.MATCHORACLE

    # Read from cache only — never make a synchronous API call here.
    live_count = 0
    try:
        cached = cache.get('live_scores_v2')
        if cached:
            live_count = len([s for s in cached if s.get('minute')])
    except Exception as exc:
        logger.warning("global_context: cache read failed: %s", exc)

    return {
        'CURRENCY_SYMBOL': cfg['CURRENCY_SYMBOL'],
        'PLANS': cfg['PLANS'],
        'APP_VERSION': cfg['VERSION'],
        'PAYSTACK_PUBLIC_KEY': cfg['PAYSTACK_PUBLIC_KEY'],
        'live_count': live_count,
    }

