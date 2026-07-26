"""
Diffusion des vidéos — voir ADR-005 (qui remplace la décision de l'ADR-001).

La lecture passe par une interface unique. Ce qui distingue les fournisseurs
n'est pas le stockage mais le **niveau de protection** : la capacité à retirer
un accès déjà délivré. Un lien non répertorié ne se retire pas ; une adresse
signée expire. Cette différence est portée par le code, pas par la
documentation — voir `NiveauProtection` et l'invariant du modèle.
"""

import base64
import hashlib
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.core import signing
from django.core.files.storage import default_storage
from django.urls import reverse

SEL_SIGNATURE = "elearning.lecture-video"


class NiveauProtection:
    """
    Ce qu'un fournisseur sait garantir sur l'adresse qu'il délivre.

    Seul SIGNEE autorise un module restreint — voir l'invariant du modèle.
    """

    AUCUNE = "aucune"
    """L'adresse est un porteur permanent. Un partage ouvre l'accès à tous."""

    DOMAINE = "domaine"
    """La lecture est refusée hors de notre domaine. Protège de la
    republication, pas du partage entre étudiants, et l'adresse sous-jacente
    reste non révocable."""

    SIGNEE = "signee"
    """Adresse signée, à durée de vie courte, liée au demandeur. Seul niveau
    compatible avec une révocation réelle."""


class ModeLecture:
    """Comment le gabarit doit rendre la vidéo."""

    FICHIER = "fichier"
    HLS = "hls"
    IFRAME = "iframe"


@dataclass(frozen=True)
class Lecture:
    """
    Ce qu'un fournisseur remet pour lire une vidéo.

    `origine` sert à construire la directive CSP : seules les origines des
    fournisseurs réellement configurés sont autorisées.
    """

    url: str
    mode: str
    expire_dans: int
    origine: str = ""


class FournisseurVideo(Protocol):
    """Contrat commun aux fournisseurs de diffusion."""

    nom: str
    protection: str
    mode: str
    accepte_televersement: bool

    def lecture(self, cle: str, ttl: int = 300, adresse_ip: str = "") -> Lecture: ...

    def televerser(self, fichier, cle: str) -> None: ...

    def supprimer(self, cle: str) -> None: ...

    def existe(self, cle: str) -> bool: ...


def nouvelle_cle(nom_origine: str) -> str:
    """Clé opaque : le nom d'origine ne doit rien révéler ni entrer en collision."""
    extension = Path(nom_origine).suffix.lower()[:10]
    return f"videos/{uuid.uuid4().hex}{extension}"


class LocalStockageVideo:
    """
    Système de fichiers, pour le développement et les tests.

    L'adresse est signée par Django et expire : le comportement observable est
    celui de la production, ce qui permet de tester la logique d'accès sans
    dépendre d'un service externe.
    """

    nom = "local"
    protection = NiveauProtection.SIGNEE
    mode = ModeLecture.FICHIER
    accepte_televersement = True
    origine = ""

    @classmethod
    def origine_csp(cls) -> str:
        return ""

    def lecture(self, cle: str, ttl: int = 300, adresse_ip: str = "") -> Lecture:
        return Lecture(url=self.url_lecture(cle, ttl=ttl), mode=self.mode, expire_dans=ttl)

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
    Stockage objet privé avec adresse présignée — décision de l'ADR-001.

    Conservé et testé bien que l'ADR-005 lui préfère un fournisseur externe :
    c'est le chemin de retour si celui-ci devait être abandonné.
    """

    nom = "s3"
    protection = NiveauProtection.SIGNEE
    mode = ModeLecture.FICHIER
    accepte_televersement = True
    origine = ""

    @classmethod
    def origine_csp(cls) -> str:
        return ""

    def __init__(self):
        import boto3

        self._bucket = settings.AWS_STORAGE_BUCKET_NAME_VIDEOS
        self._client = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None) or None,
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or None,
        )

    def lecture(self, cle: str, ttl: int = 300, adresse_ip: str = "") -> Lecture:
        return Lecture(url=self.url_lecture(cle, ttl=ttl), mode=self.mode, expire_dans=ttl)

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


class BunnyStreamVideo:
    """
    Bunny Stream — fournisseur retenu pour les modules protégés (ADR-005).

    L'adresse du manifeste HLS est signée par un jeton à expiration, calculé
    localement : délivrer une lecture ne demande aucun appel réseau, ce qui
    laisse le chemin critique sans dépendance externe.

    La liaison à l'adresse IP du demandeur est activable. Elle resserre la
    protection mais coupe la lecture des étudiants dont l'adresse change en
    cours de séance — courant en mobile. Désactivée par défaut, à assumer.
    """

    nom = "bunny"
    protection = NiveauProtection.SIGNEE
    mode = ModeLecture.HLS
    accepte_televersement = False

    def __init__(self):
        self._zone = settings.BUNNY_ZONE_DIFFUSION.rstrip("/")
        self._cle = settings.BUNNY_CLE_SIGNATURE
        self._lier_ip = getattr(settings, "BUNNY_LIER_ADRESSE_IP", False)

    @property
    def origine(self) -> str:
        return self._zone

    @classmethod
    def origine_csp(cls) -> str:
        return getattr(settings, "BUNNY_ZONE_DIFFUSION", "").rstrip("/")

    def _chemin(self, cle: str) -> str:
        return f"/{cle.strip('/')}/playlist.m3u8"

    def jeton(self, chemin: str, expiration: int, adresse_ip: str = "") -> str:
        """
        Jeton d'authentification Bunny.

        Le condensé porte sur la clé secrète, le chemin signé, l'expiration et
        — si la liaison est active — l'adresse du demandeur. Le résultat est
        transposé en base64 URL-safe sans remplissage, comme l'attend le CDN.
        """
        base = f"{self._cle}{chemin}{expiration}{adresse_ip}"
        condense = hashlib.sha256(base.encode()).digest()
        return base64.b64encode(condense).decode().replace("+", "-").replace("/", "_").replace("=", "")

    def lecture(self, cle: str, ttl: int = 300, adresse_ip: str = "") -> Lecture:
        chemin = self._chemin(cle)
        expiration = int(time.time()) + ttl
        ip = adresse_ip if self._lier_ip else ""
        jeton = self.jeton(chemin, expiration, ip)
        return Lecture(
            url=f"{self._zone}{chemin}?token={jeton}&expires={expiration}",
            mode=self.mode,
            expire_dans=ttl,
            origine=self._zone,
        )

    def televerser(self, fichier, cle: str) -> None:
        raise NotImplementedError("Le dépôt se fait dans la console Bunny ; la leçon référence l'identifiant.")

    def supprimer(self, cle: str) -> None:
        # La suppression relève de la console du fournisseur : la faire d'ici
        # ferait croire à une maîtrise que nous n'avons pas.
        return None

    def existe(self, cle: str) -> bool:
        return bool(cle)


class _FournisseurIframe:
    """
    Base des fournisseurs lus dans un cadre tiers.

    Aucun ne protège l'accès : l'adresse est un porteur, et les événements de
    lecture nous échappent. Réservés au contenu public.
    """

    mode = ModeLecture.IFRAME
    accepte_televersement = False
    gabarit_url = ""
    origine = ""

    @classmethod
    def origine_csp(cls) -> str:
        return cls.origine

    def lecture(self, cle: str, ttl: int = 300, adresse_ip: str = "") -> Lecture:
        return Lecture(
            url=self.gabarit_url.format(identifiant=cle.strip("/")),
            mode=self.mode,
            expire_dans=ttl,
            origine=self.origine,
        )

    def televerser(self, fichier, cle: str) -> None:
        raise NotImplementedError("Le dépôt se fait chez le fournisseur ; la leçon référence l'identifiant.")

    def supprimer(self, cle: str) -> None:
        return None

    def existe(self, cle: str) -> bool:
        return bool(cle)


class YouTubeVideo(_FournisseurIframe):
    """
    YouTube — bandes-annonces du catalogue public uniquement.

    Le domaine `nocookie` évite le dépôt de traceurs tant que la lecture n'a
    pas commencé. `rel=0` restreint les vidéos suggérées : sur la page d'un
    institut, se voir proposer n'importe quoi est indésirable.
    """

    nom = "youtube"
    protection = NiveauProtection.AUCUNE
    gabarit_url = "https://www.youtube-nocookie.com/embed/{identifiant}?rel=0&modestbranding=1"
    origine = "https://www.youtube-nocookie.com"


class VimeoVideo(_FournisseurIframe):
    """
    Vimeo — lecture sans marque, verrouillage de domaine côté fournisseur.

    Le verrouillage se configure dans le compte Vimeo, pas ici : il ne peut pas
    être vérifié depuis le code, et il porte sur le référent, pas sur la
    personne. D'où le niveau `DOMAINE` et non `SIGNEE`.
    """

    nom = "vimeo"
    protection = NiveauProtection.DOMAINE
    gabarit_url = "https://player.vimeo.com/video/{identifiant}?dnt=1&title=0&byline=0&portrait=0"
    origine = "https://player.vimeo.com"


FOURNISSEURS: dict[str, type] = {
    LocalStockageVideo.nom: LocalStockageVideo,
    S3StockageVideo.nom: S3StockageVideo,
    BunnyStreamVideo.nom: BunnyStreamVideo,
    YouTubeVideo.nom: YouTubeVideo,
    VimeoVideo.nom: VimeoVideo,
}

PROTECTION_PAR_FOURNISSEUR: dict[str, str] = {nom: classe.protection for nom, classe in FOURNISSEURS.items()}

CHOIX_FOURNISSEUR = [
    (BunnyStreamVideo.nom, "Bunny Stream (adresse signée)"),
    (VimeoVideo.nom, "Vimeo (contenu public)"),
    (YouTubeVideo.nom, "YouTube (contenu public)"),
]


# Niveau de protection minimal exigé par politique d'accès du module.
#
# La règle est graduée plutôt que binaire, parce que les enjeux le sont. Un
# module public n'a rien à protéger. Un module réservé aux comptes connectés
# serait contourné par un lien porteur, mais le verrouillage de domaine y
# suffit. Dès qu'un droit individuel est en jeu — inscription au parcours ou
# octroi nominatif — seule une adresse signée permet de le retirer.
PROTECTION_MINIMALE: dict[str, str] = {
    "public": NiveauProtection.AUCUNE,
    "authentifie": NiveauProtection.DOMAINE,
    "inscrit_parcours": NiveauProtection.SIGNEE,
    "sur_octroi": NiveauProtection.SIGNEE,
}

_ORDRE_PROTECTION = [NiveauProtection.AUCUNE, NiveauProtection.DOMAINE, NiveauProtection.SIGNEE]


def protection_suffisante(protection: str, politique: str) -> bool:
    """Le fournisseur protège-t-il assez pour cette politique d'accès ?"""
    exigee = PROTECTION_MINIMALE.get(politique, NiveauProtection.SIGNEE)
    try:
        return _ORDRE_PROTECTION.index(protection) >= _ORDRE_PROTECTION.index(exigee)
    except ValueError:
        # Fournisseur inconnu : on refuse plutôt que de supposer.
        return False


def fournisseur(nom: str = "") -> FournisseurVideo:
    """
    Fournisseur demandé, ou celui du réglage `ELEARNING_DIFFUSION_VIDEO`.

    Un nom inconnu retombe sur Bunny, le fournisseur externe protégé. Le
    stockage local reste disponible explicitement pour relire les références
    historiques, mais il ne constitue plus un chemin de création implicite.
    """
    choix = nom or getattr(settings, "ELEARNING_DIFFUSION_VIDEO", "bunny")
    return FOURNISSEURS.get(choix, BunnyStreamVideo)()


def origines_actives() -> list[str]:
    """Origines des fournisseurs externes acceptés par le formulaire vidéo."""
    noms = {nom for nom, _libelle in CHOIX_FOURNISSEUR}
    noms.add(getattr(settings, "ELEARNING_DIFFUSION_VIDEO", "bunny"))
    noms.update(getattr(settings, "ELEARNING_DIFFUSION_PUBLIQUE", []))
    origines = set()
    for nom in noms:
        classe = FOURNISSEURS.get(nom)
        if classe is None:
            continue
        origine = classe.origine_csp()
        if origine:
            origines.add(origine)
    return sorted(origines)


# `stockage_video()` reste le nom employé par le code existant : l'alias évite
# une modification mécanique sans valeur.
stockage_video = fournisseur
