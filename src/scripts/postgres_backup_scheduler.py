#!/usr/bin/env python3
"""Planificateur minimal des sauvegardes PostgreSQL hors serveur.

Le conteneur reste autonome : pas de cron de l'hôte, pas de socket Docker et
pas de dépendance à Celery. Un échec est retenté périodiquement jusqu'à succès,
puis la prochaine exécution revient à l'heure locale configurée.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SCRIPT = "/opt/iteag/postgres_backup_r2.py"


def _booleen(nom: str, defaut: bool) -> bool:
    valeur = os.environ.get(nom)
    if valeur is None:
        return defaut
    return valeur.strip().lower() in {"1", "true", "yes", "oui", "on"}


def _entier(nom: str, defaut: int) -> int:
    return int(os.environ.get(nom, str(defaut)))


def _prochaine_execution() -> datetime:
    fuseau = ZoneInfo(os.environ.get("BACKUP_TIMEZONE", "America/Cayenne"))
    maintenant = datetime.now(fuseau)
    heure = _entier("BACKUP_HOUR_LOCAL", 3)
    minute = _entier("BACKUP_MINUTE_LOCAL", 0)
    cible = maintenant.replace(hour=heure, minute=minute, second=0, microsecond=0)
    if cible <= maintenant:
        cible += timedelta(days=1)
    return cible


def _lancer() -> bool:
    debut = datetime.now().astimezone()
    print(f"[{debut.isoformat()}] lancement de la sauvegarde PostgreSQL…", flush=True)
    resultat = subprocess.run(["python3", SCRIPT, "backup"], check=False)
    if resultat.returncode == 0:
        print("Sauvegarde terminée avec succès.", flush=True)
        return True
    print(f"Sauvegarde en échec (code {resultat.returncode}).", flush=True)
    return False


def main() -> None:
    retry = max(_entier("BACKUP_RETRY_SECONDS", 3600), 60)

    if _booleen("BACKUP_RUN_ON_START", True):
        while not _lancer():
            print(f"Nouvelle tentative dans {retry} secondes.", flush=True)
            time.sleep(retry)

    while True:
        cible = _prochaine_execution()
        maintenant = datetime.now(cible.tzinfo)
        attente = max((cible - maintenant).total_seconds(), 1)
        print(f"Prochaine sauvegarde : {cible.isoformat()} ({int(attente)} s).", flush=True)
        time.sleep(attente)

        while not _lancer():
            print(f"Nouvelle tentative dans {retry} secondes.", flush=True)
            time.sleep(retry)


if __name__ == "__main__":
    main()
