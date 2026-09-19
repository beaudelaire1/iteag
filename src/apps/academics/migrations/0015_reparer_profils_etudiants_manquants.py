from django.db import migrations
from django.utils import timezone


def reparer_profils_etudiants(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    ProfilEtudiant = apps.get_model("academics", "ProfilEtudiant")

    annee = timezone.now().year
    prefixe = f"ETU{annee}"

    dernier = (
        ProfilEtudiant.objects.filter(numero_etudiant__startswith=prefixe)
        .order_by("-numero_etudiant")
        .values_list("numero_etudiant", flat=True)
        .first()
    )
    rang = int(dernier.removeprefix(prefixe)) + 1 if dernier else 1

    comptes = (
        User.objects.filter(
            role="etudiant",
            is_superuser=False,
            is_staff=False,
            profil_etudiant__isnull=True,
        )
        .order_by("pk")
        .iterator()
    )

    for compte in comptes:
        while ProfilEtudiant.objects.filter(numero_etudiant=f"{prefixe}{rang:03d}").exists():
            rang += 1

        ProfilEtudiant.objects.create(
            utilisateur_id=compte.pk,
            numero_etudiant=f"{prefixe}{rang:03d}",
            statut_inscription="pre_inscrit",
        )
        rang += 1


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_invitations_illustrees"),
        ("academics", "0014_delai_correction_par_cours"),
    ]

    operations = [
        migrations.RunPython(
            reparer_profils_etudiants,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
