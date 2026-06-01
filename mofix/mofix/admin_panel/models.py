from django.db import models
from django.conf import settings


class AdminLog(models.Model):
    """Tracks every action performed by staff members in the custom admin panel."""

    ACTION_CHOICES = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
        ('view',   'Viewed'),
        ('login',  'Logged In'),
        ('other',  'Other'),
    ]

    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='admin_logs',
    )
    action      = models.CharField(max_length=20, choices=ACTION_CHOICES, default='other')
    # Human-readable description, e.g. "Created WeeklyTip: Arsenal vs Chelsea"
    description = models.TextField()
    # Optional: the model/object that was affected
    object_type = models.CharField(max_length=100, blank=True)
    object_id   = models.CharField(max_length=50, blank=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Admin Log'
        verbose_name_plural = 'Admin Logs'

    def __str__(self):
        admin_email = self.admin_user.email if self.admin_user else 'unknown'
        return f"[{self.get_action_display()}] {admin_email} — {self.description[:60]}"
