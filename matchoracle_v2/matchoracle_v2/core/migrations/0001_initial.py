from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [('accounts', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='WeeklyForecast',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('home_team', models.CharField(max_length=100)),
                ('away_team', models.CharField(max_length=100)),
                ('match_date', models.DateTimeField()),
                ('competition', models.CharField(default='Premier League', max_length=100)),
                ('home_win_pct', models.FloatField(default=0)),
                ('draw_pct', models.FloatField(default=0)),
                ('away_win_pct', models.FloatField(default=0)),
                ('predicted_score', models.CharField(default='1-1', max_length=10)),
                ('confidence', models.IntegerField(default=70)),
                ('ai_insight', models.TextField(blank=True)),
                ('is_published', models.BooleanField(default=True)),
                ('result', models.CharField(blank=True, max_length=20)),
                ('was_correct', models.BooleanField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-match_date']},
        ),
        migrations.CreateModel(
            name='SiteAnalytics',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('date', models.DateField(unique=True)),
                ('total_predictions', models.IntegerField(default=0)),
                ('total_users', models.IntegerField(default=0)),
                ('active_subscriptions', models.IntegerField(default=0)),
                ('revenue_ngn', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
            ],
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=200)),
                ('message', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='accounts.user')),
            ],
        ),
    ]
