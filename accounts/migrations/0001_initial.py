from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = [('auth', '0012_alter_user_first_name_max_length')]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('password', models.CharField(max_length=128)),
                ('last_login', models.DateTimeField(blank=True, null=True)),
                ('is_superuser', models.BooleanField(default=False)),
                ('username', models.CharField(max_length=150, unique=True)),
                ('first_name', models.CharField(blank=True, max_length=150)),
                ('last_name', models.CharField(blank=True, max_length=150)),
                ('is_staff', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now)),
                ('email', models.EmailField(unique=True)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('plan', models.CharField(default='free', max_length=20)),
                ('trial_count', models.IntegerField(default=0)),
                ('subscription_start', models.DateTimeField(blank=True, null=True)),
                ('subscription_end', models.DateTimeField(blank=True, null=True)),
                ('api_key', models.CharField(blank=True, default='', max_length=64, unique=True)),
                ('predictions_today', models.IntegerField(default=0)),
                ('predictions_date', models.DateField(blank=True, null=True)),
                ('referral_code', models.CharField(blank=True, default='', max_length=10)),
                ('total_predictions', models.IntegerField(default=0)),
                ('correct_predictions', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('groups', models.ManyToManyField(blank=True, related_name='user_set', to='auth.group')),
                ('user_permissions', models.ManyToManyField(blank=True, related_name='user_set', to='auth.permission')),
            ],
            options={'abstract': False},
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('plan', models.CharField(max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('currency', models.CharField(default='NGN', max_length=5)),
                ('reference', models.CharField(max_length=100, unique=True)),
                ('status', models.CharField(default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='accounts.user')),
            ],
        ),
    ]
