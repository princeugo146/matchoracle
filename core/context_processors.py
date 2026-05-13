from django.conf import settings
def global_context(request):
    cfg = settings.MATCHORACLE
    return {
        'CURRENCY_SYMBOL': cfg['CURRENCY_SYMBOL'],
        'PLANS': cfg['PLANS'],
        'APP_VERSION': cfg['VERSION'],
        'PAYSTACK_PUBLIC_KEY': cfg.get('PAYSTACK_PUBLIC_KEY', ''),
        'live_count': 0,
    }
