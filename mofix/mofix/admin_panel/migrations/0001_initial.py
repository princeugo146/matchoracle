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
                ('action', models.CharField(
                    choices=[
                        ('create', 'Created'),
                        ('update', 'Updated'),
                        ('delete', 'Deleted'),
                        ('view',   'Viewed'),
                        ('login',  'Logged In'),
                        ('other',  'Other'),
                    ],
                    default='other',
                    max_length=20,
                )),
                ('description', models.TextField()),
                ('object_type', models.CharField(blank=True, max_length=100)),
                ('object_id',   models.CharField(blank=True, max_length=50)),
                ('ip_address',  models.GenericIPAddressField(blank=True, null=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('admin_user',  models.ForeignKey(
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
