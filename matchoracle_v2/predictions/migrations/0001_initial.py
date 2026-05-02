from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [('accounts', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='Prediction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('engine', models.CharField(choices=[('A','Match'),('B','Player'),('C','Ranking'),('D','Simulation'),('NL','Natural Language')], max_length=2)),
                ('input_data', models.JSONField()),
                ('output_data', models.JSONField()),
                ('confidence', models.IntegerField(default=0)),
                ('home_team', models.CharField(blank=True, max_length=100)),
                ('away_team', models.CharField(blank=True, max_length=100)),
                ('predicted_result', models.CharField(blank=True, max_length=50)),
                ('actual_result', models.CharField(blank=True, max_length=50)),
                ('was_correct', models.BooleanField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='predictions', to='accounts.user')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='TeamRanking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
                ('power_elo', models.IntegerField(default=1000)),
                ('wins', models.IntegerField(default=0)),
                ('draws', models.IntegerField(default=0)),
                ('losses', models.IntegerField(default=0)),
                ('goals_for', models.IntegerField(default=0)),
                ('goals_against', models.IntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rankings', to='accounts.user')),
            ],
            options={'ordering': ['-power_elo']},
        ),
        migrations.CreateModel(
            name='WeeklyTip',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('home_team', models.CharField(max_length=100)),
                ('away_team', models.CharField(max_length=100)),
                ('competition', models.CharField(max_length=100)),
                ('match_date', models.DateTimeField()),
                ('tip', models.CharField(max_length=200)),
                ('odds', models.CharField(blank=True, max_length=20)),
                ('confidence', models.IntegerField(default=70)),
                ('is_pro_only', models.BooleanField(default=False)),
                ('result', models.CharField(blank=True, max_length=50)),
                ('was_correct', models.BooleanField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-match_date']},
        ),
        migrations.AlterUniqueTogether(
            name='teamranking',
            unique_together={('user', 'name')},
        ),
    ]
