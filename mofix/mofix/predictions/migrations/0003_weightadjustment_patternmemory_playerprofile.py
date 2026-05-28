from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('predictions', '0002_teamprofile_engineaccuracy_predictionresult_conversationmemory'),
    ]

    operations = [
        # ── WeightAdjustment ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='WeightAdjustment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('engine', models.CharField(
                    choices=[('A', 'Match'), ('B', 'Player'), ('D', 'Simulation'), ('NL', 'AI')],
                    db_index=True, max_length=2,
                )),
                ('parameter', models.CharField(max_length=100)),
                ('old_weight', models.FloatField()),
                ('new_weight', models.FloatField()),
                ('reason', models.TextField(blank=True)),
                ('accuracy_before', models.FloatField(blank=True, null=True)),
                ('accuracy_after', models.FloatField(blank=True, null=True)),
                ('match_type', models.CharField(default='league', max_length=20)),
                ('applied_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-applied_at'],
            },
        ),
        migrations.AddIndex(
            model_name='weightadjustment',
            index=models.Index(fields=['engine', 'parameter'], name='pred_wa_eng_param_idx'),
        ),

        # ── PatternMemory ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='PatternMemory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('pattern_type', models.CharField(
                    choices=[
                        ('team',      'Team Pattern'),
                        ('player',    'Player Pattern'),
                        ('matchup',   'Tactical Matchup'),
                        ('condition', 'Match Condition'),
                        ('h2h',       'Head-to-Head'),
                    ],
                    db_index=True, max_length=20,
                )),
                ('pattern_key', models.CharField(db_index=True, max_length=200)),
                ('pattern_value', models.JSONField(default=dict)),
                ('accuracy', models.FloatField(default=0.0)),
                ('occurrences', models.IntegerField(default=1)),
                ('min_sample', models.IntegerField(default=5)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-occurrences', '-accuracy'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='patternmemory',
            unique_together={('pattern_type', 'pattern_key')},
        ),

        # ── PlayerProfile ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='PlayerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(db_index=True, max_length=100, unique=True)),
                ('team', models.CharField(blank=True, max_length=100)),
                ('position', models.CharField(
                    blank=True,
                    choices=[
                        ('GK', 'Goalkeeper'), ('CB', 'Centre-Back'), ('LB', 'Left-Back'),
                        ('RB', 'Right-Back'), ('CDM', 'Defensive Mid'), ('CM', 'Central Mid'),
                        ('CAM', 'Attacking Mid'), ('LW', 'Left Wing'), ('RW', 'Right Wing'),
                        ('ST', 'Striker'),
                    ],
                    max_length=5,
                )),
                ('goals_this_season', models.IntegerField(default=0)),
                ('assists_this_season', models.IntegerField(default=0)),
                ('appearances_this_season', models.IntegerField(default=0)),
                ('attack_rating', models.FloatField(default=0.0)),
                ('defense_rating', models.FloatField(default=0.0)),
                ('overall_rating', models.FloatField(default=0.0)),
                ('injury_status', models.CharField(
                    choices=[
                        ('fit', 'Fit'), ('doubt', 'Doubt'),
                        ('out', 'Out'), ('unknown', 'Unknown'),
                    ],
                    default='unknown', max_length=20,
                )),
                ('injury_history', models.JSONField(default=list)),
                ('recent_ratings', models.JSONField(default=list)),
                ('prediction_impact', models.FloatField(default=0.0)),
                ('raw_data', models.JSONField(default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-overall_rating', 'name'],
            },
        ),
    ]
