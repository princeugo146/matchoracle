from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[
                    ('user_edit', 'User Edited'),
                    ('user_deactivate', 'User Deactivated'),
                    ('user_activate', 'User Activated'),
                    ('user_delete', 'User Deleted'),
                    ('tip_create', 'Tip Created'),
                    ('tip_edit', 'Tip Edited'),
                    ('tip_delete', 'Tip Deleted'),
                    ('plan_change', 'Plan Changed'),
                    ('other', 'Other'),
                ], max_length=30)),
                ('target_type', models.CharField(blank=True, max_length=50)),
                ('target_id', models.IntegerField(blank=True, null=True)),
                ('description', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('admin', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='admin_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Admin Log',
                'verbose_name_plural': 'Admin Logs',
                'ordering': ['-created_at'],
            },
        ),
    ]
