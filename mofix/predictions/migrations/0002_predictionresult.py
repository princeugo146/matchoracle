from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('predictions', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PredictionResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('home_team', models.CharField(blank=True, db_index=True, max_length=100)),
                ('away_team', models.CharField(blank=True, db_index=True, max_length=100)),
                ('match_date', models.DateField(blank=True, null=True)),
                ('predicted_verdict', models.CharField(blank=True, max_length=100)),
                ('predicted_score', models.CharField(blank=True, max_length=20)),
                ('confidence_level', models.IntegerField(default=0)),
                ('engine_a_verdict', models.CharField(blank=True, max_length=100)),
                ('engine_d_verdict', models.CharField(blank=True, max_length=100)),
                ('smart_ai_verdict', models.CharField(blank=True, max_length=100)),
                ('actual_result', models.CharField(blank=True, max_length=100)),
                ('actual_score', models.CharField(blank=True, max_length=20)),
                ('is_correct', models.BooleanField(blank=True, null=True)),
                ('prediction', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='analytics_result',
                    to='predictions.prediction',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='predictionresult',
            index=models.Index(fields=['created_at'], name='predictions_created_at_idx'),
        ),
        migrations.AddIndex(
            model_name='predictionresult',
            index=models.Index(fields=['home_team', 'away_team'], name='predictions_teams_idx'),
        ),
    ]
