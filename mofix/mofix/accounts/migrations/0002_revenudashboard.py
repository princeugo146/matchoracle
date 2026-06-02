from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RevenueDashboard',
            fields=[
            ],
            options={
                'verbose_name': 'Revenue Dashboard',
                'verbose_name_plural': 'Revenue Dashboard',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('accounts.payment',),
        ),
    ]
