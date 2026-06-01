from django.db import models
from django.conf import settings


class AdminLog(models.Model):
    """Audit log for all admin panel actions."""
    ACTION_CHOICES = [
        ('user_edit',       'User Edited'),
        ('user_deactivate', 'User Deactivated'),
        ('user_activate',   'User Activated'),
        ('user_delete',     'User Deleted'),
        ('tip_create',      'Tip Created'),
        ('tip_edit',        'Tip Edited'),
        ('tip_delete',      'Tip Deleted'),
        ('plan_change',     'Plan Changed'),
        ('other',           'Other'),
    ]

    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='admin_logs',
    )
    action      = models.CharField(max_length=30, choices=ACTION_CHOICES)
    target_type = models.CharField(max_length=50, blank=True)   # e.g. "User", "WeeklyTip"
    target_id   = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Admin Log'
        verbose_name_plural = 'Admin Logs'

    def __str__(self):
        admin_email = self.admin.email if self.admin else 'unknown'
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {admin_email} — {self.get_action_display()}"
