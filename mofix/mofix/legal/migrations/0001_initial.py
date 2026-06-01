from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='LegalPage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('page_type', models.CharField(choices=[('privacy', 'Privacy Policy'), ('terms', 'Terms of Service')], max_length=20, unique=True)),
                ('content', models.TextField(blank=True, help_text='HTML content for the page (optional override)')),
                ('version', models.CharField(default='1.0', max_length=20)),
                ('last_updated', models.DateField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Legal Page',
                'verbose_name_plural': 'Legal Pages',
            },
        ),
    ]
