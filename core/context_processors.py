from django.conf import settings


def global_context(request):
    """Makes global variables available in all templates."""
    cfg = settings.MATCHORACLE
    live_count = 0
    try:
        from core.live_scores import get_live_count
        live_count = get_live_count()
    except Exception:
        pass

    return {
        'CURRENCY_SYMBOL': cfg['CURRENCY_SYMBOL'],
        'PLANS': cfg['PLANS'],
        'APP_VERSION': cfg['VERSION'],
        'PAYSTACK_PUBLIC_KEY': cfg['PAYSTACK_PUBLIC_KEY'],
        'live_count': live_count,
    }
