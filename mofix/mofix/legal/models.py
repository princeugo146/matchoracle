from django.db import models


class LegalPage(models.Model):
    PAGE_TYPE_CHOICES = [
        ('privacy', 'Privacy Policy'),
        ('terms', 'Terms of Service'),
    ]
    page_type = models.CharField(max_length=20, choices=PAGE_TYPE_CHOICES, unique=True)
    content = models.TextField(blank=True, help_text='HTML content for the page (optional override)')
    version = models.CharField(max_length=20, default='1.0')
    last_updated = models.DateField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Legal Page'
        verbose_name_plural = 'Legal Pages'

    def __str__(self):
        return self.get_page_type_display()
