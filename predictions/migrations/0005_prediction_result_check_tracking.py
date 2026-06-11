from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('predictions', '0004_matchresult_prediction_result_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='prediction',
            name='result_check_attempts',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='prediction',
            name='last_result_check_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
