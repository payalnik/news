from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('news_app', '0006_newsitem_dedup_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='newsitem',
            name='confidence',
        ),
    ]
