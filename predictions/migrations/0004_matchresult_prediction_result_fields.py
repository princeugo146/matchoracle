from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('predictions', '0003_weightadjustment_patternmemory_playerprofile'),
    ]

    operations = [
        # ── New fields on Prediction ──────────────────────────────────────────
        migrations.AddField(
            model_name='prediction',
            name='result_label',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='prediction',
            name='result_checked',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='prediction',
            name='actual_result',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='prediction',
            name='actual_score',
            field=models.CharField(blank=True, max_length=20),
        ),

        # ── MatchResult model ─────────────────────────────────────────────────
        migrations.CreateModel(
            name='MatchResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('home_team', models.CharField(max_length=100)),
                ('away_team', models.CharField(max_length=100)),
                ('home_score', models.IntegerField()),
                ('away_score', models.IntegerField()),
                ('match_date', models.DateField()),
                ('competition', models.CharField(default='Unknown', max_length=100)),
                ('match_type', models.CharField(default='league', max_length=50)),
                ('home_possession', models.FloatField(default=50)),
                ('away_possession', models.FloatField(default=50)),
                ('home_shots', models.IntegerField(default=0)),
                ('away_shots', models.IntegerField(default=0)),
                ('home_tactical_style', models.CharField(default='balanced', max_length=50)),
                ('away_tactical_style', models.CharField(default='balanced', max_length=50)),
                ('home_key_player', models.CharField(blank=True, max_length=100)),
                ('away_key_player', models.CharField(blank=True, max_length=100)),
                ('match_summary', models.TextField(blank=True)),
                ('what_decided_match', models.TextField(blank=True)),
                ('result', models.CharField(blank=True, max_length=10)),
                ('processed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-match_date'],
            },
        ),
    ]
