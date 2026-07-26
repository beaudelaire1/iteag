"""
Stockage des vidéos — voir ADR-001.

L'accès au fichier passe par une interface unique, ce qui rend le passage
ultérieur à un flux segmenté ou à un CDN signé non intrusif : seul le backend
change, ni les vues ni les gabarits.
"""

import uuid
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.core import signing
from django.core.files.storage import default_storage
from django.urls import reverse

SEL_SIGNATURE = "elearning.lecture-video"


class BackendStockageVideo(Protocol):
    """Contrat commun aux implémentations de stockage."""

    nom: str

    def url_lecture(self, cle: str, ttl: int = 300) -> str:
        """Adresse de lecture à durée de vie limitée."""
        ...

    def televerser(self, fichier, cle: str) -> None: ...

    def supprimer(self, cle: str) -> None: ...

    def existe(self, cle: str) -> bool: ...


def nouvelle_cle(nom_origine: str) -> str:
    """Clé opaque : le nom d'origine ne doit rien révéler ni entrer en collision."""
    extension = Path(nom_origine).suffix.lower()[:10]
    return f"videos/{uuid.uuid4().hex}{extension}"


class LocalStockageVideo:
    """
    Stockage sur le système de fichiers, pour le développement et les tests.

    L'adresse est signée par Django et expire : le comportement observable est
    le même qu'en production, ce qui permet de tester la logique d'accès sans
    dépendre d'un service externe.
    """

    nom = "local"

    def url_lecture(self, cle: str, ttl: int = 300) -> str:
        # La clé est sérialisée en base64 URL-safe : elle contient des « / »
        # qui, signés tels quels, casseraient le motif d'URL.
        jeton = signing.dumps(cle, salt=SEL_SIGNATURE)
        return reverse("elearning:fichier_video", kwargs={"jeton": jeton})

    @staticmethod
    def cle_depuis_jeton(jeton: str, ttl: int = 300) -> str | None:
        """Clé portée par un jeton encore valide, sinon None."""
        try:
            return signing.loads(jeton, salt=SEL_SIGNATURE, max_age=ttl)
        except signing.BadSignature:
            return None

    def televerser(self, fichier, cle: str) -> None:
        default_storage.save(cle, fichier)

    def supprimer(self, cle: str) -> None:
        if default_storage.exists(cle):
            default_storage.delete(cle)

    def existe(self, cle: str) -> bool:
        return default_storage.exists(cle)

    def ouvrir(self, cle: str):
        return default_storage.open(cle, "rb")


class S3StockageVideo:
    """
    Stockage objet privé avec adresse présignée — production.

    Le bucket ne porte aucune autorisation publique : sans signature valide,
    l'objet est inaccessible.
    """

    nom = "s3"

    def __init__(self):
        import boto3

        self._bucket = settings.AWS_STORAGE_BUCKET_NAME_VIDEOS
        self._client = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None) or None,
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or None,
        )

    def url_lecture(self, cle: str, ttl: int = 300) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": cle},
            ExpiresIn=ttl,
        )

    def televerser(self, fichier, cle: str) -> None:
        self._client.upload_fileobj(fichier, self._bucket, cle)

    def supprimer(self, cle: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=cle)

    def existe(self, cle: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=cle)
            return True
        except ClientError:
            return False


def stockage_video() -> BackendStockageVideo:
    """Backend courant, déterminé par le réglage `ELEARNING_STOCKAGE_VIDEO`."""
    choix = getattr(settings, "ELEARNING_STOCKAGE_VIDEO", "local")
    if choix == "s3":
        return S3StockageVideo()
    return LocalStockageVideo()
