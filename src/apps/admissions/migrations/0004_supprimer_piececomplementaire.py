"""Retire le jumeau de « PieceDemandee ».

Deux modèles décrivaient la même chose — une pièce réclamée à un candidat,
déposée par lui, puis acceptée ou refusée. Ils sont nés sur deux branches
parallèles et ont survécu tous les deux à la fusion, réconciliés par une
migration de fusion qui ne tranchait rien. Seul « PieceDemandee » a jamais été
relié à une URL, à un gabarit et à un courriel : c'est celui qui reste.

**À vérifier avant de déployer.** La table est vide sur la base de
développement, et elle devrait l'être partout : la seule vue qui y écrivait a
perdu sa route à la fusion. Mais elle en a eu une avant, sur la branche d'où
elle vient — si un déploiement en est parti, des lignes existent. Une
suppression de table ne se rejoue pas :

    SELECT COUNT(*) FROM admissions_piececomplementaire;

Zéro : appliquer. Autre chose : exporter les lignes avant, et me le dire — le
modèle vivant sait les accueillir.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("admissions", "0003_merge_0002_piececomplementaire_0002_piecedemandee"),
    ]

    operations = [
        migrations.DeleteModel(name="PieceComplementaire"),
    ]
