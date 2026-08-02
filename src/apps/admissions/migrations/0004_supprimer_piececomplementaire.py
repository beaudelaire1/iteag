"""Retire le jumeau de « PieceDemandee ».

Deux modèles décrivaient la même chose — une pièce réclamée à un candidat,
déposée par lui, puis acceptée ou refusée. Ils sont nés sur deux branches
parallèles et ont survécu tous les deux à la fusion, réconciliés par une
migration de fusion qui ne tranchait rien. Seul « PieceDemandee » a jamais été
relié à une URL, à un gabarit et à un courriel : c'est celui qui reste.

La table supprimée est vide en production — aucune vue n'y a jamais écrit.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("admissions", "0003_merge_0002_piececomplementaire_0002_piecedemandee"),
    ]

    operations = [
        migrations.DeleteModel(name="PieceComplementaire"),
    ]
