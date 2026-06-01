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
            name='WeeklyTipAdmin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('home_team', models.CharField(max_length=100)),
                ('away_team', models.CharField(max_length=100)),
                ('competition', models.CharField(default='Premier League', max_length=100)),
                ('match_date', models.DateTimeField()),
                ('tip', models.CharField(help_text='e.g. Home Win, Over 2.5 Goals, BTTS', max_length=300)),
                ('confidence', models.IntegerField(default=70, help_text='Confidence percentage 0-100')),
                ('confidence_label', models.CharField(choices=[('high', 'High (80%+)'), ('medium', 'Medium (60-79%)'), ('low', 'Low (<60%)')], default='medium', max_length=10)),
                ('is_pro_only', models.BooleanField(default=False)),
                ('is_published', models.BooleanField(default=True)),
                ('result', models.CharField(blank=True, choices=[('', 'Pending'), ('win', 'Win'), ('loss', 'Loss'), ('void', 'Void')], max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_tips', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Weekly Tip',
                'verbose_name_plural': 'Weekly Tips',
                'ordering': ['-match_date'],
            },
        ),
        migrations.CreateModel(
            name='AdminLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('create', 'Create'), ('update', 'Update'), ('delete', 'Delete'), ('activate', 'Activate'), ('deactivate', 'Deactivate'), ('view', 'View'), ('login', 'Login'), ('other', 'Other')], max_length=20)),
                ('model_name', models.CharField(blank=True, max_length=100)),
                ('object_id', models.CharField(blank=True, max_length=50)),
                ('object_repr', models.CharField(blank=True, max_length=300)),
                ('details', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('admin', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admin_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Admin Log',
                'verbose_name_plural': 'Admin Logs',
                'ordering': ['-created_at'],
            },
        ),
    ]
