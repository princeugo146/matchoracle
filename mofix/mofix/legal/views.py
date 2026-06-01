from django.shortcuts import render
from django.utils import timezone


def privacy_policy(request):
    return render(request, 'legal/privacy_policy.html', {
        'last_updated': timezone.now().date(),
        'version': '1.0',
    })


def terms_of_service(request):
    return render(request, 'legal/terms_of_service.html', {
        'last_updated': timezone.now().date(),
        'version': '1.0',
    })
