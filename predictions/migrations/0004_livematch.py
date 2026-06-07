from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('predictions', '0003_weightadjustment_patternmemory_playerprofile'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiveMatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('home_team', models.CharField(max_length=100)),
                ('away_team', models.CharField(max_length=100)),
                ('home_score', models.IntegerField(blank=True, null=True)),
                ('away_score', models.IntegerField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('LIVE', 'Live'),
                        ('SCHEDULED', 'Scheduled'),
                        ('FINISHED', 'Finished'),
                        ('POSTPONED', 'Postponed'),
                        ('CANCELLED', 'Cancelled'),
                    ],
                    default='SCHEDULED',
                    max_length=50,
                )),
                ('minute', models.IntegerField(blank=True, null=True)),
                ('competition', models.CharField(blank=True, max_length=100)),
                ('start_time', models.DateTimeField()),
                ('sportmonks_id', models.IntegerField(blank=True, null=True, unique=True)),
                ('home_logo', models.URLField(blank=True, default='')),
                ('away_logo', models.URLField(blank=True, default='')),
            ],
            options={
                'ordering': ['-start_time'],
            },
        ),
    ]
