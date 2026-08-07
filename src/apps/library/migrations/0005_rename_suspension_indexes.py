from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0004_suspensionbibliotheque"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="suspensionbibliotheque",
            old_name="library_sus_emprunt_78ad3c_idx",
            new_name="library_sus_emprunt_5f04d3_idx",
        ),
        migrations.RenameIndex(
            model_name="suspensionbibliotheque",
            old_name="library_sus_levee_l_346ed8_idx",
            new_name="library_sus_levee_l_801d1a_idx",
        ),
    ]
