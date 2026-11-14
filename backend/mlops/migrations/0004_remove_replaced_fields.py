from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mlops', '0003_move_metrics_and_periods'),
    ]

    operations = [
        migrations.RemoveField(model_name='modelversion', name='decision'),
        migrations.RemoveField(model_name='modelversion', name='activated_at'),
        migrations.RemoveField(model_name='modelversion', name='deactivated_at'),
        migrations.RemoveField(model_name='modelversion', name='dice'),
        migrations.RemoveField(model_name='modelversion', name='hd95'),
        migrations.RemoveField(model_name='modelversion', name='f1'),
    ]
