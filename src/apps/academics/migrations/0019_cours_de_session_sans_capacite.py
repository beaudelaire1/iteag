from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0018_paiements_cours_et_formations_2026"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="coursdesession",
            name="cours_session_capacite_positive",
        ),
        migrations.RemoveField(
            model_name="coursdesession",
            name="capacite",
        ),
    ]
