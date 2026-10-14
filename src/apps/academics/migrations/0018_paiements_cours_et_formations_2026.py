"""Rattache les paiements à des cours précis et inscrit les activités annoncées.

Ces activités figuraient dans les actualités de septembre 2026, mais pas
nécessairement dans le catalogue académique. Aucun paiement, aucune demande
d'inscription ni aucune inscription existante n'est modifié automatiquement.
Les cours sont fermés aux nouvelles inscriptions jusqu'au contrôle du secrétariat.
"""
import datetime
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


def _slug_disponible(modele, texte, limite):
    base = slugify(texte)[:limite]
    candidat = base
    i = 2
    while modele.objects.filter(slug=candidat).exists():
        suffixe = f"-{i}"
        candidat = f"{base[:limite-len(suffixe)]}{suffixe}"
        i += 1
    return candidat


def _cours(Cours, titre, discipline):
    existant = Cours.objects.filter(titre__iexact=titre).first()
    if existant:
        return existant
    return Cours.objects.create(
        titre=titre,
        slug=_slug_disponible(Cours, titre, 250),
        discipline=discipline,
    )


def _enseignant(Professeur, prenom, nom):
    existant = Professeur.objects.filter(prenom__iexact=prenom, nom__iexact=nom).first()
    if existant:
        return existant
    return Professeur.objects.create(
        prenom=prenom, nom=nom,
        slug=_slug_disponible(Professeur, f"{prenom} {nom}", 200),
        actif=False,
    )


def programmer_activites_annoncees(apps, schema_editor):
    Session = apps.get_model("academics", "SessionAcademique")
    Programmation = apps.get_model("academics", "CoursDeSession")
    Cours = apps.get_model("formations", "Cours")
    Discipline = apps.get_model("formations", "Discipline")
    Professeur = apps.get_model("formations", "Professeur")

    # Respecter la convention des migrations de référence ITEAG : ne pas
    # introduire de catalogue artificiel dans une base encore vide.
    if not Discipline.objects.exists():
        return

    nouveau_testament = Discipline.objects.filter(nom__iexact="Nouveau Testament").first()
    pratique = Discipline.objects.filter(nom__iexact="Théologie pratique").first()
    if not nouveau_testament or not pratique:
        return

    session_octobre, _ = Session.objects.get_or_create(
        periode="formation", annee_academique="2026-2027",
        defaults={
            "nom": "Formation biblique du 26 au 30 octobre 2026",
            "date_debut": datetime.date(2026, 10, 26),
            "date_fin": datetime.date(2026, 10, 30),
            "statut": "planifiee",
        },
    )
    for titre, prenom, nom, discipline in [
        ("La « Bible » éthiopienne est-elle la « vraie » Bible ?", "Alain", "Nisus", nouveau_testament),
        ("Comment étudier rigoureusement un texte du Nouveau Testament ?", "Cédric", "Eugène", nouveau_testament),
    ]:
        cours = _cours(Cours, titre, discipline)
        Programmation.objects.get_or_create(
            session=session_octobre, cours=cours,
            defaults={
                "enseignant": _enseignant(Professeur, prenom, nom),
                "modalite": "presentiel",
                "salle": "Église Protestante Évangélique, Morne Bernard, Baie-Mahault",
                "horaires": "26 au 30 octobre 2026, de 8 h à 13 h",
                "inscriptions_ouvertes": False,
            },
        )

    session_ateliers, _ = Session.objects.get_or_create(
        periode="ateliers", annee_academique="2026-2027",
        defaults={
            "nom": "Ateliers de théologie — cycle 2026-2027",
            "date_debut": datetime.date(2026, 9, 26),
            "date_fin": datetime.date(2027, 6, 19),
            "statut": "planifiee",
        },
    )
    # L'annonce publique appelle ce cycle « ateliers de prédication ».
    # Le titre opérationnel conserve aussi le terme « théologie » utilisé
    # par le secrétariat pour ses encaissements.
    titre = "Ateliers de théologie — cycle de prédication 2026-2027"
    cours = _cours(Cours, titre, pratique)
    Programmation.objects.get_or_create(
        session=session_ateliers, cours=cours,
        defaults={
            "enseignant": _enseignant(Professeur, "Alain", "Nisus"),
            "modalite": "presentiel",
            "horaires": "Dix samedis, de 9 h à 12 h, du 26 septembre 2026 au 19 juin 2027.",
            "frais_inscription": Decimal("200.00"),
            "inscriptions_ouvertes": False,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0017_sessions_2027"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sessionacademique",
            name="periode",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("carnaval", "Carnaval"),
                    ("paques", "Pâques"),
                    ("juillet", "Grandes vacances"),
                    ("toussaint", "Toussaint"),
                    ("ateliers", "Cycle d’ateliers"),
                    ("formation", "Formation ponctuelle"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="paiement",
            name="cours_session",
            field=models.ForeignKey(
                to="academics.coursdesession",
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True,
                related_name="paiements_affectes",
                verbose_name="Cours ou atelier réglé",
            ),
        ),
        migrations.RunPython(programmer_activites_annoncees, migrations.RunPython.noop),
    ]
