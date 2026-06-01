from django.contrib import admin
from .models import LegalPage


@admin.register(LegalPage)
class LegalPageAdmin(admin.ModelAdmin):
    list_display = ['page_type', 'version', 'last_updated']
    readonly_fields = ['last_updated', 'created_at']
