"""Synchronise src/media vers le bucket R2 déclaré dans src/.env.production.

Usage : python scripts/sync-media-r2.py [--inclure-videos]
N'écrase jamais : un objet déjà présent avec la même taille est ignoré.
"""

import mimetypes
import sys
from pathlib import Path

import boto3

RACINE = Path(__file__).resolve().parents[1]
MEDIA = RACINE / "media"


def lire_env(chemin: Path) -> dict[str, str]:
    valeurs = {}
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if "=" in ligne and not ligne.lstrip().startswith("#"):
            cle, _, val = ligne.partition("=")
            valeurs[cle.strip()] = val.strip()
    return valeurs


def main() -> None:
    env = lire_env(RACINE / ".env.production")
    s3 = boto3.client(
        "s3",
        endpoint_url=env["AWS_S3_ENDPOINT_URL"],
        aws_access_key_id=env["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=env["AWS_SECRET_ACCESS_KEY"],
    )
    bucket = env["AWS_STORAGE_BUCKET_NAME"]

    existants: dict[str, int] = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for objet in page.get("Contents", []):
            existants[objet["Key"]] = objet["Size"]

    inclure_videos = "--inclure-videos" in sys.argv
    envoyes = ignores = 0
    for fichier in sorted(MEDIA.rglob("*")):
        if not fichier.is_file():
            continue
        cle = fichier.relative_to(MEDIA).as_posix()
        if not inclure_videos and cle.startswith("videos/"):
            continue
        if existants.get(cle) == fichier.stat().st_size:
            ignores += 1
            continue
        type_mime = mimetypes.guess_type(fichier.name)[0] or "application/octet-stream"
        s3.upload_file(str(fichier), bucket, cle, ExtraArgs={"ContentType": type_mime})
        envoyes += 1
        if envoyes % 200 == 0:
            print(f"  {envoyes} fichiers envoyés…")

    print(f"Terminé : {envoyes} envoyés, {ignores} déjà présents.")


if __name__ == "__main__":
    main()
