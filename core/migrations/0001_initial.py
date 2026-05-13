from django.db import migrations, models
class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='WeeklyForecast',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
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
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-match_date']},
        ),
    ]
