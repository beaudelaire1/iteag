from django.db import migrations


def annuler_derive_totp(apps, schema_editor):
    # La dérive apprise avant OTP_TOTP_SYNC = False peut exclure le code courant.
    TOTPDevice = apps.get_model("otp_totp", "TOTPDevice")
    TOTPDevice.objects.exclude(drift=0).update(drift=0)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_volet_masque"),
        ("otp_totp", "0003_add_timestamps"),
    ]

    operations = [
        migrations.RunPython(annuler_derive_totp, migrations.RunPython.noop),
    ]
