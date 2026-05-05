from django.conf import settings

def global_context(request):
    """Makes global variables available in all templates."""
    cfg = settings.MATCHORACLE
    
    # DO NOT call get_live_count() here - it blocks requests!
    # Live count will be 0 by default
    live_count = 0
    
    return {
        'CURRENCY_SYMBOL': cfg['CURRENCY_SYMBOL'],
        'PLANS': cfg['PLANS'],
        'APP_VERSION': cfg['VERSION'],
        'PAYSTACK_PUBLIC_KEY': cfg['PAYSTACK_PUBLIC_KEY'],
        'live_count': live_count,
    }
