#!/usr/bin/env python3
"""Sauvegarde PostgreSQL ITEAG vers un bucket Cloudflare R2 dédié.

Le script tourne dans le conteneur ``backup`` : il possède le client PostgreSQL
16 et boto3, mais aucun accès au volume ``postgres_data``. La sauvegarde passe
uniquement par le protocole PostgreSQL, puis quitte le serveur vers R2.

Sous-commandes :
- ``backup`` : pg_dump, empreinte SHA-256, upload, vérification et rétention ;
- ``status`` : vérifie qu'une sauvegarde récente existe réellement sur R2 ;
- ``restore`` : restaure un dump dans une base cible explicite et distincte de
  la production par défaut.

Aucun secret n'est affiché dans les journaux.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


def _obligatoire(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        raise RuntimeError(f"Variable obligatoire absente : {nom}")
    return valeur


def _entier(nom: str, defaut: int) -> int:
    try:
        return int(os.environ.get(nom, str(defaut)))
    except ValueError as erreur:
        raise RuntimeError(f"{nom} doit être un entier.") from erreur


def _postgres() -> dict[str, str]:
    return {
        "host": os.environ.get("POSTGRES_HOST", "db"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "database": os.environ.get("POSTGRES_DB", "iteag"),
        "user": os.environ.get("POSTGRES_USER", "iteag"),
        "password": _obligatoire("POSTGRES_PASSWORD"),
    }


def _r2():
    endpoint = _obligatoire("BACKUP_R2_ENDPOINT_URL")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("BACKUP_R2_REGION", "auto"),
        aws_access_key_id=_obligatoire("BACKUP_R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_obligatoire("BACKUP_R2_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _bucket() -> str:
    return _obligatoire("BACKUP_R2_BUCKET")


def _prefixe() -> str:
    return os.environ.get("BACKUP_R2_PREFIX", "postgres").strip("/") or "postgres"


def _env_pg() -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = _postgres()["password"]
    return env


def _sha256(chemin: Path) -> str:
    hachage = hashlib.sha256()
    with chemin.open("rb") as fichier:
        for bloc in iter(lambda: fichier.read(1024 * 1024), b""):
            hachage.update(bloc)
    return hachage.hexdigest()


def _executer(commande: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        commande,
        env=_env_pg(),
        check=True,
        text=True,
        capture_output=capture,
    )


def _dump(chemin: Path) -> None:
    pg = _postgres()
    commande = [
        "pg_dump",
        "--host",
        pg["host"],
        "--port",
        pg["port"],
        "--username",
        pg["user"],
        "--dbname",
        pg["database"],
        "--format=custom",
        "--compress=9",
        "--no-owner",
        "--no-acl",
        "--file",
        str(chemin),
    ]
    _executer(commande)
    if not chemin.exists() or chemin.stat().st_size == 0:
        raise RuntimeError("pg_dump a terminé sans produire d'archive exploitable.")


def _cle_quotidienne(maintenant: datetime) -> str:
    horodatage = maintenant.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{_prefixe()}/daily/{maintenant:%Y/%m}/iteag-{horodatage}.dump"


def _cle_mensuelle(maintenant: datetime) -> str:
    return f"{_prefixe()}/monthly/{maintenant:%Y}/iteag-{maintenant:%Y-%m}.dump"


def _upload(client, chemin: Path, cle: str, empreinte: str) -> None:
    taille = chemin.stat().st_size
    client.upload_file(
        str(chemin),
        _bucket(),
        cle,
        ExtraArgs={
            "ContentType": "application/octet-stream",
            "Metadata": {
                "sha256": empreinte,
                "database": _postgres()["database"],
                "created-at": datetime.now(UTC).isoformat(),
            },
        },
    )
    tete = client.head_object(Bucket=_bucket(), Key=cle)
    if int(tete.get("ContentLength", -1)) != taille:
        raise RuntimeError("La taille de l'objet R2 diffère du dump local après upload.")
    if tete.get("Metadata", {}).get("sha256") != empreinte:
        raise RuntimeError("L'empreinte SHA-256 enregistrée sur R2 ne correspond pas au dump local.")


def _existe(client, cle: str) -> bool:
    try:
        client.head_object(Bucket=_bucket(), Key=cle)
        return True
    except ClientError as erreur:
        code = erreur.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def _objets(client, prefixe: str) -> list[dict]:
    objets: list[dict] = []
    jeton = None
    while True:
        params = {"Bucket": _bucket(), "Prefix": prefixe}
        if jeton:
            params["ContinuationToken"] = jeton
        reponse = client.list_objects_v2(**params)
        objets.extend(reponse.get("Contents", []))
        if not reponse.get("IsTruncated"):
            break
        jeton = reponse.get("NextContinuationToken")
    return objets


def _purger(client, sous_prefixe: str, jours: int) -> None:
    if jours <= 0:
        return
    limite = datetime.now(UTC) - timedelta(days=jours)
    a_supprimer = [
        objet["Key"]
        for objet in _objets(client, f"{_prefixe()}/{sous_prefixe}/")
        if objet.get("LastModified") and objet["LastModified"] < limite
    ]
    for debut in range(0, len(a_supprimer), 1000):
        lot = a_supprimer[debut : debut + 1000]
        try:
            reponse = client.delete_objects(
                Bucket=_bucket(),
                Delete={"Objects": [{"Key": cle} for cle in lot], "Quiet": True},
            )
        except ClientError as erreur:
            # Une règle Bucket Lock peut volontairement empêcher la purge. La
            # nouvelle sauvegarde est déjà vérifiée : la rétention ne doit pas
            # la transformer artificiellement en échec.
            code = erreur.response.get("Error", {}).get("Code", "inconnu")
            print(f"AVERTISSEMENT : purge R2 refusée ({code}).", file=sys.stderr)
            continue
        erreurs = reponse.get("Errors", [])
        if erreurs:
            print(f"AVERTISSEMENT : {len(erreurs)} objet(s) ancien(s) n'ont pas pu être supprimés.", file=sys.stderr)


def sauvegarder() -> None:
    fuseau = ZoneInfo(os.environ.get("BACKUP_TIMEZONE", "America/Cayenne"))
    maintenant = datetime.now(fuseau)
    client = _r2()

    with tempfile.TemporaryDirectory(prefix="iteag-backup-") as dossier:
        archive = Path(dossier) / "iteag.dump"
        print("Sauvegarde PostgreSQL : création du dump…")
        _dump(archive)
        empreinte = _sha256(archive)
        taille = archive.stat().st_size

        cle = _cle_quotidienne(maintenant)
        print(f"Envoi R2 : {cle} ({taille} octets)…")
        _upload(client, archive, cle, empreinte)

        if maintenant.day == 1:
            mensuelle = _cle_mensuelle(maintenant)
            if not _existe(client, mensuelle):
                print(f"Copie mensuelle : {mensuelle}…")
                _upload(client, archive, mensuelle, empreinte)

    _purger(client, "daily", _entier("BACKUP_RETENTION_DAYS", 35))
    _purger(client, "monthly", _entier("BACKUP_MONTHLY_RETENTION_DAYS", 400))
    print(f"OK — sauvegarde vérifiée sur R2 : {cle}")


def _dernier_objet(client) -> dict:
    objets = _objets(client, f"{_prefixe()}/daily/")
    if not objets:
        raise RuntimeError("Aucune sauvegarde quotidienne trouvée sur R2.")
    return max(objets, key=lambda objet: objet["LastModified"])


def statut(age_max: int) -> None:
    client = _r2()
    dernier = _dernier_objet(client)
    age = datetime.now(UTC) - dernier["LastModified"]
    if age.total_seconds() > age_max:
        raise RuntimeError(f"Dernière sauvegarde trop ancienne : {int(age.total_seconds())} s (maximum {age_max} s).")
    print(f"OK — dernière sauvegarde R2 : {dernier['Key']} ({int(age.total_seconds())} s).")


def _telecharger_verifier(client, cle: str, destination: Path) -> None:
    tete = client.head_object(Bucket=_bucket(), Key=cle)
    attendu = tete.get("Metadata", {}).get("sha256", "")
    client.download_file(_bucket(), cle, str(destination))
    if attendu and _sha256(destination) != attendu:
        raise RuntimeError("L'empreinte SHA-256 du dump téléchargé ne correspond pas à celle stockée sur R2.")


def restaurer(cle: str | None, cible: str, supprimer_apres: bool, autoriser_production: bool) -> None:
    pg = _postgres()
    if cible == pg["database"] and not autoriser_production:
        raise RuntimeError(
            "Refus de restaurer par-dessus la base de production. Utilisez une base temporaire, "
            "ou --allow-production lors d'une procédure de reprise explicitement décidée."
        )

    client = _r2()
    cle = cle or _dernier_objet(client)["Key"]
    with tempfile.TemporaryDirectory(prefix="iteag-restore-") as dossier:
        archive = Path(dossier) / "restauration.dump"
        print(f"Téléchargement et vérification : {cle}…")
        _telecharger_verifier(client, cle, archive)

        base = ["--host", pg["host"], "--port", pg["port"], "--username", pg["user"]]
        _executer(["dropdb", *base, "--if-exists", cible])
        _executer(["createdb", *base, cible])
        try:
            _executer(
                [
                    "pg_restore",
                    *base,
                    "--dbname",
                    cible,
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                    str(archive),
                ]
            )
            resultat = _executer(
                [
                    "psql",
                    *base,
                    "--dbname",
                    cible,
                    "--tuples-only",
                    "--no-align",
                    "--command",
                    "SELECT count(*) FROM django_migrations;",
                ],
                capture=True,
            )
            migrations = resultat.stdout.strip()
            if not migrations.isdigit() or int(migrations) <= 0:
                raise RuntimeError("La restauration ne contient pas de table django_migrations exploitable.")
            print(f"OK — restauration validée dans {cible} ({migrations} migrations enregistrées).")
        finally:
            if supprimer_apres and cible != pg["database"]:
                _executer(["dropdb", *base, "--if-exists", "--force", cible])
                print(f"Base temporaire supprimée : {cible}.")


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    sous = analyseur.add_subparsers(dest="commande", required=True)

    sous.add_parser("backup", help="Créer et envoyer une sauvegarde PostgreSQL sur R2.")

    etat = sous.add_parser("status", help="Vérifier la fraîcheur de la dernière sauvegarde R2.")
    etat.add_argument("--max-age", type=int, default=36 * 3600, help="Âge maximal en secondes.")

    restauration = sous.add_parser("restore", help="Restaurer et vérifier une sauvegarde R2.")
    restauration.add_argument("--key", default=None, help="Clé R2 précise ; par défaut, dernier dump quotidien.")
    restauration.add_argument("--target-db", required=True, help="Base PostgreSQL cible.")
    restauration.add_argument("--drop-after", action="store_true", help="Supprimer la base cible après vérification.")
    restauration.add_argument(
        "--allow-production",
        action="store_true",
        help="Autoriser explicitement une restauration sur POSTGRES_DB.",
    )

    options = analyseur.parse_args()
    try:
        if options.commande == "backup":
            sauvegarder()
        elif options.commande == "status":
            statut(options.max_age)
        elif options.commande == "restore":
            restaurer(options.key, options.target_db, options.drop_after, options.allow_production)
        return 0
    except (RuntimeError, subprocess.CalledProcessError, ClientError) as erreur:
        print(f"ERREUR — {erreur}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
