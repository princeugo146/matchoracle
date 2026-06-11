from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_security_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='free_trials_used',
            field=models.IntegerField(default=0),
        ),
    ]
