from django.db import models
from django.conf import settings


class WeeklyTipAdmin(models.Model):
    """Admin-managed weekly tips shown on the tips page."""
    CONFIDENCE_CHOICES = [
        ('high', 'High (80%+)'),
        ('medium', 'Medium (60-79%)'),
        ('low', 'Low (<60%)'),
    ]
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    competition = models.CharField(max_length=100, default='Premier League')
    match_date = models.DateTimeField()
    tip = models.CharField(max_length=300, help_text='e.g. Home Win, Over 2.5 Goals, BTTS')
    confidence = models.IntegerField(default=70, help_text='Confidence percentage 0-100')
    confidence_label = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default='medium')
    is_pro_only = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    result = models.CharField(max_length=20, blank=True, choices=[
        ('', 'Pending'), ('win', 'Win'), ('loss', 'Loss'), ('void', 'Void')
    ])
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_tips'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-match_date']
        verbose_name = 'Weekly Tip'
        verbose_name_plural = 'Weekly Tips'

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} — {self.tip}"

    @property
    def confidence_class(self):
        if self.confidence >= 80:
            return 'high'
        elif self.confidence >= 60:
            return 'medium'
        return 'low'


class AdminLog(models.Model):
    """Audit trail for all admin actions."""
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('activate', 'Activate'),
        ('deactivate', 'Deactivate'),
        ('view', 'View'),
        ('login', 'Login'),
        ('other', 'Other'),
    ]
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='admin_logs'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=300, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Admin Log'
        verbose_name_plural = 'Admin Logs'

    def __str__(self):
        return f"[{self.action.upper()}] {self.admin} — {self.model_name} #{self.object_id}"
