from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from datetime import timedelta


def default_expires_at():
    return django.utils.timezone.now() + timedelta(hours=24)


class Migration(migrations.Migration):

    dependencies = [
        ('predictions', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TeamProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('team_name', models.CharField(db_index=True, max_length=100, unique=True)),
                ('last_20_results', models.JSONField(default=list)),
                ('avg_goals_scored', models.FloatField(default=0.0)),
                ('avg_goals_conceded', models.FloatField(default=0.0)),
                ('tactical_style', models.CharField(default='balanced', max_length=50)),
                ('key_players', models.JSONField(default=list)),
                ('injury_history', models.JSONField(default=list)),
                ('home_accuracy', models.FloatField(default=0.0)),
                ('away_accuracy', models.FloatField(default=0.0)),
                ('vs_style_accuracy', models.JSONField(default=dict)),
                ('sample_size', models.IntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['team_name'],
            },
        ),
        migrations.CreateModel(
            name='EngineAccuracy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('engine', models.CharField(
                    choices=[('A', 'Match'), ('B', 'Player'), ('D', 'Simulation'), ('NL', 'AI')],
                    db_index=True, max_length=2,
                )),
                ('match_type', models.CharField(
                    choices=[
                        ('league', 'League'), ('cup', 'Cup'), ('champions', 'Champions League'),
                        ('friendly', 'Friendly'), ('knockout', 'Knockout'), ('final', 'Final'),
                    ],
                    default='league', max_length=20,
                )),
                ('accuracy_pct', models.FloatField(default=0.0)),
                ('tactical_matchup_accuracy', models.JSONField(default=dict)),
                ('home_accuracy', models.FloatField(default=0.0)),
                ('away_accuracy', models.FloatField(default=0.0)),
                ('draw_accuracy', models.FloatField(default=0.0)),
                ('weight_adjustment', models.FloatField(default=1.0)),
                ('sample_size', models.IntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['engine', 'match_type'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='engineaccuracy',
            unique_together={('engine', 'match_type')},
        ),
        migrations.CreateModel(
            name='PredictionResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('prediction', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='result_record',
                    to='predictions.prediction',
                )),
                ('actual_result', models.CharField(blank=True, max_length=100)),
                ('actual_score', models.CharField(blank=True, max_length=20)),
                ('was_correct', models.BooleanField(blank=True, null=True)),
                ('margin_of_error', models.FloatField(blank=True, null=True)),
                ('result_checked_at', models.DateTimeField(blank=True, null=True)),
                ('result_source', models.CharField(
                    choices=[
                        ('sportmonks', 'Sportmonks API'),
                        ('web_search', 'Web Search'),
                        ('manual', 'Manual Entry'),
                    ],
                    default='web_search', max_length=20,
                )),
                ('raw_data', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ConversationMemory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('user_id', models.IntegerField(db_index=True)),
                ('session_id', models.CharField(db_index=True, max_length=64)),
                ('context', models.JSONField(default=dict)),
                ('messages', models.JSONField(default=list)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='conversationmemory',
            unique_together={('user_id', 'session_id')},
        ),
    ]
