import functools
from django.shortcuts import redirect
from django.contrib import messages
from .models import AdminLog


def admin_required(view_func):
    """Restrict view to superusers and staff members only."""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/accounts/login/?next={request.path}')
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'Access denied. Admin privileges required.')
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


def log_admin_action(action, model_name='', get_object_repr=None):
    """
    Decorator that logs admin actions to AdminLog after the view executes.
    Usage:
        @log_admin_action('create', 'WeeklyTipAdmin')
        def my_view(request): ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)
            if request.user.is_authenticated and request.method in ('POST', 'DELETE'):
                obj_id = kwargs.get('pk', kwargs.get('tip_id', kwargs.get('user_id', '')))
                obj_repr = ''
                if get_object_repr and callable(get_object_repr):
                    try:
                        obj_repr = get_object_repr(request, *args, **kwargs)
                    except Exception:
                        pass
                ip = _get_client_ip(request)
                AdminLog.objects.create(
                    admin=request.user,
                    action=action,
                    model_name=model_name,
                    object_id=str(obj_id) if obj_id else '',
                    object_repr=obj_repr[:300] if obj_repr else '',
                    ip_address=ip,
                )
            return response
        return wrapper
    return decorator


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_action(request, action, model_name='', object_id='', object_repr='', details=''):
    """Helper to manually log an admin action from within a view."""
    if request.user.is_authenticated:
        AdminLog.objects.create(
            admin=request.user,
            action=action,
            model_name=model_name,
            object_id=str(object_id),
            object_repr=object_repr[:300],
            details=details[:1000],
            ip_address=_get_client_ip(request),
        )
