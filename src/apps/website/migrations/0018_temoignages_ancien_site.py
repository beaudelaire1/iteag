"""Reprend les deux témoignages publiés sur l'ancien site iteag.org.

L'ancien site était une application React ; son carrousel « Ils l'ont vécu »
portait deux témoignages d'étudiants, figés dans le paquet JavaScript. La
refonte a emporté la page, pas les textes : ils ne sont plus visibles nulle
part, alors que la fiche Google de l'institut n'affiche, elle, qu'une étoile
sans commentaire.

Les textes viennent du dernier instantané public de l'ancien site. Rien n'y a
été récrit : seule la typographie a été mise à la norme française, comme pour
n'importe quel texte que l'institut publie — l'espace avant le point
d'exclamation de « ouverte à tous ! », l'accent d'« éthiques », et « etc. »
rendu à ses trois points. Le champ « position » de l'ancien modèle devient
« promotion », qui est son équivalent le plus proche ici.

Le consentement à la publication est marqué comme acquis parce qu'il l'était :
ces deux témoignages étaient affichés publiquement, sous le nom et la qualité
de leurs auteurs, sur le site officiel de l'institut. Si l'un d'eux souhaite
aujourd'hui se retirer, le statut « retiré » de la rubrique d'administration
suffit — il n'y a pas à repasser par une migration.

« valide_par » reste vide : aucune personne n'a validé ces textes dans la
nouvelle application, et prétendre le contraire fausserait la piste d'audit.

La migration ne réécrit jamais un témoignage déjà présent sous le même nom
affiché : une fois en base, le texte appartient à la direction, qui peut
l'amender depuis sa rubrique sans qu'un déploiement le remette à l'état
d'origine. Elle est irréversible pour la même raison — défaire créerait le
risque d'effacer une correction humaine.
"""

import datetime

from django.db import migrations

# Date de reprise, fixée plutôt que calculée : deux bases rejouant la migration
# à des moments différents doivent porter la même trace.
REPRISE_LE = datetime.datetime(2026, 9, 10, 12, 0, tzinfo=datetime.UTC)

TEMOIGNAGES = (
    {
        "nom_affiche": "Eliane Kancel",
        "promotion": "Étudiante",
        "texte": (
            "<p>L'ITEAG : une formation de haut niveau ! Nous l'attendions de nos vœux depuis fort "
            "longtemps. Durant ces six années de formation, j'ai pu : apprécier la qualité des cours "
            "dispensés par d'éminents professeurs, approfondir mes connaissances théologiques et "
            "bibliques, acquérir de nouvelles compétences pour un service efficace dans l'église. "
            "Cette formation est ouverte à tous ! Alors, inscrivez-vous !</p>"
        ),
    },
    {
        "nom_affiche": "Frédéric Jean-Louis",
        "promotion": "Étudiant, conducteur de louange en Martinique",
        "texte": (
            "<p>Souhaitant progresser dans ma vie spirituelle et mon ministère, j'ai choisi l'ITEAG "
            "pour approfondir mes connaissances théologiques. J'y ai trouvé une formation de qualité "
            "avec des professeurs de qualité, de sérieuses références bibliographiques et une riche "
            "bibliothèque. Des thèmes doctrinaux, éthiques, etc., abordés sans complexes, avec une "
            "ouverture d'esprit et un esprit critique pour mieux comprendre les écritures, s'y "
            "enraciner, s'édifier et améliorer le service à l'église. Si vous souhaitez progresser "
            "spirituellement tant individuellement que dans votre service, je vous conseille cette "
            "formation avec l'ITEAG.</p>"
        ),
    },
)


def reprendre_les_temoignages(apps, schema_editor):
    Temoignage = apps.get_model("website", "TemoignageEtudiant")

    for donnees in TEMOIGNAGES:
        if Temoignage.objects.filter(nom_affiche=donnees["nom_affiche"]).exists():
            continue
        Temoignage.objects.create(
            etudiant=None,
            nom_affiche=donnees["nom_affiche"],
            promotion=donnees["promotion"],
            texte=donnees["texte"],
            consentement_publication=True,
            statut="publie",
            valide_le=REPRISE_LE,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0017_actualites_rentree_2026"),
    ]

    operations = [
        migrations.RunPython(reprendre_les_temoignages, migrations.RunPython.noop),
    ]
