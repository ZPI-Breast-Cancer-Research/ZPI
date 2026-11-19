import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlops', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelTable(name='modelversion', table='module_version'),
        migrations.AlterField(
            model_name='modelversion',
            name='module',
            field=models.CharField(choices=[('seg', 'SEG'), ('ext', 'EXT'), ('ocr', 'OCR')], default='seg', max_length=3),
        ),
        migrations.AlterField(
            model_name='modelversion',
            name='status',
            field=models.CharField(choices=[('new', 'New'), ('training', 'Training'), ('candidate', 'Candidate'), ('production', 'Production'), ('archived', 'Archived'), ('rejected', 'Rejected')], default='new', max_length=20),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='proposed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='proposed_versions', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='proposed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='reason',
            field=models.TextField(blank=True, default='', help_text='Reason of the proposal or the decision'),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='restore',
            field=models.BooleanField(default=False, help_text='The proposal brings back an archived version'),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='trained_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='training_cases',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='celery_task_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='dataset',
            field=models.CharField(blank=True, default='', help_text='Set the version was trained on and its metrics were computed on; written by the worker', max_length=100),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='metrics',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='modelversion',
            name='metrics_cases',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ModuleUsagePeriod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField()),
                ('ended_at', models.DateTimeField(blank=True, help_text='Empty while the version is in use', null=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('module_version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='periods', to='mlops.modelversion')),
            ],
            options={
                'db_table': 'module_usage_period',
                'ordering': ['started_at'],
            },
        ),
    ]
