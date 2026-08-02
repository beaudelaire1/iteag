"""Exécution d'un import : tout ou rien, avec un rapport ligne à ligne.

Le choix structurant est l'atomicité. Un import à moitié appliqué laisse un
fichier dont plus personne ne sait quelle moitié est à jour : il faut alors
comparer ligne par ligne avec la source, ce qui coûte plus cher que de
recommencer un import refusé.

Les erreurs sont donc **toutes** collectées — on ne s'arrête pas à la
première — puis la transaction est annulée. L'utilisateur corrige son fichier
en une passe au lieu de le redéposer dix fois.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.services.tableur import (
    FichierIllisible,
    Rapport,
    Schema,
    ligne_vide,
    lire,
    valider_entetes,
)

# Au-delà, l'import relève d'une commande de gestion : une requête HTTP qui
# tient une transaction sur des milliers de lignes finit par expirer, et le
# verrou gêne tout le monde pendant ce temps.
LIGNES_MAXIMUM = 5000


class _Annulation(Exception):
    """Sort de la transaction sans la valider, sans masquer d'erreur réelle."""


def executer(schema: Schema, fichier) -> Rapport:
    """Applique un fichier au schéma donné, ou n'applique rien."""
    rapport = Rapport()

    if not schema.importable:
        rapport.erreurs.append((0, f"« {schema.libelle} » ne peut être qu'exporté."))
        return rapport

    try:
        donnees = lire(fichier)
    except FichierIllisible as erreur:
        rapport.erreurs.append((0, str(erreur)))
        return rapport

    if not donnees:
        rapport.erreurs.append((0, "Le fichier ne contient aucune ligne sous les en-têtes."))
        return rapport

    if len(donnees) > LIGNES_MAXIMUM:
        rapport.erreurs.append(
            (0, f"{len(donnees)} lignes : au-delà de {LIGNES_MAXIMUM}, passez par une commande de gestion.")
        )
        return rapport

    manquantes = valider_entetes(donnees, schema.colonnes)
    if manquantes:
        rapport.erreurs.append((1, "Colonnes obligatoires absentes : " + ", ".join(manquantes) + "."))
        return rapport

    try:
        with transaction.atomic():
            for index, ligne in enumerate(donnees, start=2):  # 1 = en-têtes, comme à l'écran
                if ligne_vide(ligne):
                    rapport.ignores += 1
                    continue
                try:
                    cree = schema.importer_ligne(ligne)
                except ValidationError as erreur:
                    rapport.erreurs.append((index, erreur.messages[0]))
                except Exception as erreur:  # noqa: BLE001 — une ligne fautive ne doit pas tout interrompre
                    rapport.erreurs.append((index, f"Ligne rejetée : {erreur}"))
                else:
                    if cree:
                        rapport.crees += 1
                    else:
                        rapport.mis_a_jour += 1

            if rapport.est_en_echec:
                raise _Annulation
    except _Annulation:
        # Le rapport est conservé ; la base, elle, n'a pas bougé.
        rapport.crees = rapport.mis_a_jour = 0

    return rapport
