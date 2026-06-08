from django.http import HttpResponse
from django.core.mail import send_mail
from django.conf import settings
import traceback

def test_email(request):
    """Test if email sending works"""
    try:
        # Try to send a test email
        result = send_mail(
            subject='MatchOracle Email Test',
            message='If you received this, email is working!',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['princeugo146@gmail.com'],
            fail_silently=False,
        )
        return HttpResponse(f"""
        <h1>✅ Email Test Successful!</h1>
        <p>Test email sent successfully!</p>
        <hr>
        <h2>Configuration:</h2>
        <ul>
            <li>From Email: {settings.DEFAULT_FROM_EMAIL}</li>
            <li>Email Host: {settings.EMAIL_HOST}</li>
            <li>Email Port: {settings.EMAIL_PORT}</li>
            <li>Email Use TLS: {settings.EMAIL_USE_TLS}</li>
            <li>Email Host User: {settings.EMAIL_HOST_USER}</li>
            <li>Result: {result} email(s) sent</li>
        </ul>
        """, content_type='text/html')
    except Exception as e:
        error_trace = traceback.format_exc()
        return HttpResponse(f"""
        <h1>❌ Email Test Failed!</h1>
        <p><strong>Error Type:</strong> {type(e).__name__}</p>
        <p><strong>Error Message:</strong> {str(e)}</p>
        <hr>
        <h2>Configuration:</h2>
        <ul>
            <li>From Email: {settings.DEFAULT_FROM_EMAIL}</li>
            <li>Email Host: {settings.EMAIL_HOST}</li>
            <li>Email Port: {settings.EMAIL_PORT}</li>
            <li>Email Use TLS: {settings.EMAIL_USE_TLS}</li>
            <li>Email Host User: {settings.EMAIL_HOST_USER}</li>
        </ul>
        <hr>
        <h2>Full Traceback:</h2>
        <pre>{error_trace}</pre>
        """, content_type='text/html', status=500)
