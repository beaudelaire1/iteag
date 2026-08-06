from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_groupe_redaction_mediatheque"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="signature",
            field=models.ImageField(
                blank=True,
                help_text="Image PNG, JPEG ou WebP apposée sur les documents que vous rédigez.",
                upload_to="comptes/signatures/%Y/",
                verbose_name="Signature numérique",
            ),
        ),
    ]
