from django.http import JsonResponse
from django.core.mail import send_mail
from django.conf import settings

def test_email(request):
    """Test if email sending works"""
    try:
        # Try to send a test email
        send_mail(
            subject='MatchOracle Email Test',
            message='If you received this, email is working!',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['princeugo146@gmail.com'],
            fail_silently=False,
        )
        return JsonResponse({
            'status': 'success',
            'message': 'Test email sent successfully!',
            'from_email': settings.DEFAULT_FROM_EMAIL,
            'email_host': settings.EMAIL_HOST,
            'email_port': settings.EMAIL_PORT,
            'email_use_tls': settings.EMAIL_USE_TLS,
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'error_type': type(e).__name__,
            'from_email': settings.DEFAULT_FROM_EMAIL,
            'email_host': settings.EMAIL_HOST,
            'email_port': settings.EMAIL_PORT,
            'email_use_tls': settings.EMAIL_USE_TLS,
        }, status=500)
