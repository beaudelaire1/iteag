from django.db import migrations


def reinitialiser_blocages_totp(apps, schema_editor):
    TOTPDevice = apps.get_model("otp_totp", "TOTPDevice")
    TOTPDevice.objects.filter(throttling_failure_count__gt=0).update(
        throttling_failure_count=0,
        throttling_failure_timestamp=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_volet_masque"),
        ("otp_totp", "0003_add_timestamps"),
    ]

    operations = [
        migrations.RunPython(reinitialiser_blocages_totp, migrations.RunPython.noop),
    ]
