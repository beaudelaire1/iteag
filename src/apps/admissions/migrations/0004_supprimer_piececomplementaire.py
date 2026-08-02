"""Retire le jumeau de « PieceDemandee ».

Deux modèles décrivaient la même chose — une pièce réclamée à un candidat,
déposée par lui, puis acceptée ou refusée. Ils sont nés sur deux branches
parallèles et ont survécu tous les deux à la fusion, réconciliés par une
migration de fusion qui ne tranchait rien. Seul « PieceDemandee » a jamais été
relié à une URL, à un gabarit et à un courriel : c'est celui qui reste.

La table est vide sur la base de développement, et elle devrait l'être partout :
la seule vue qui y écrivait a perdu sa route à la fusion. Mais elle en a eu une
avant, sur la branche d'où elle vient — si un déploiement en est parti, des
lignes existent quelque part.

Une suppression de table ne se rejoue pas. La migration compte donc avant de
détruire, et **s'arrête si elle trouve la moindre ligne** : mieux vaut un
déploiement en échec, qui se répare, qu'un dossier de candidature effacé sans
que personne ne l'apprenne. Le message dit quoi faire.
"""

from django.db import migrations


def refuser_si_des_lignes_existent(apps, schema_editor):
    PieceComplementaire = apps.get_model("admissions", "PieceComplementaire")
    nombre = PieceComplementaire.objects.count()
    if nombre:
        raise RuntimeError(
            f"« admissions_piececomplementaire » contient {nombre} ligne(s) : la table n'est pas "
            "supprimée. Ces pièces ont été réclamées par une vue retirée depuis. Exportez-les, "
            "reportez-les sur « PieceDemandee », puis relancez la migration."
        )


def sans_objet(apps, schema_editor):
    """Le retour arrière recrée une table vide : rien à contrôler."""


class Migration(migrations.Migration):
    dependencies = [
        ("admissions", "0003_merge_0002_piececomplementaire_0002_piecedemandee"),
    ]

    operations = [
        migrations.RunPython(refuser_si_des_lignes_existent, sans_objet),
        migrations.DeleteModel(name="PieceComplementaire"),
    ]
