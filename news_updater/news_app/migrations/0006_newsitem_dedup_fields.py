from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news_app', '0005_fetchlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='newsitem',
            name='content_hash',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='newsitem',
            name='embedding',
            field=models.TextField(blank=True, null=True),
        ),
    ]
