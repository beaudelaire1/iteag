"""
Éprouve les identifiants Bunny contre le compte réel.

Pourquoi cette commande existe : le dialogue avec Bunny est la seule partie du
dispositif vidéo qui ne peut pas être vérifiée hors ligne. Nos tests confirment
que le jeton et l'en-tête sont *formés* comme nous l'avons décidé — ils ne
peuvent pas confirmer que Bunny les *accepte*. Seul un aller-retour le dit.

Deux clés, deux usages, et la commande éprouve les deux :

  · **La clé d'API du dépôt** autorise à créer et à téléverser. Elle n'était pas
    contrôlée ici, si bien qu'une clé fausse ne se découvrait que le jour où
    quelqu'un déposait une vidéo — et sortait alors en « 401 » brut devant un
    utilisateur. C'est arrivé.
  · **La clé de signature** autorise à lire. Sa vérification passe par deux
    étapes, car la première réussit souvent quand la seconde échoue : le
    manifeste se charge, puis chaque segment est refusé, et la lecture s'arrête
    après quelques secondes en paraissant d'abord fonctionner. C'est le défaut
    qu'un jeton de fichier, au lieu d'un jeton de répertoire, produit.

Sans argument, seule la clé d'API est éprouvée — c'est le contrôle qui ne
demande rien à personne. L'identifiant d'une vidéo ajoute l'épreuve de lecture.

Aucun secret n'est affiché : ni les clés, ni le jeton complet.
"""

import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.elearning import bunny_televersement as depot
from apps.elearning.diffusion import BunnyStreamVideo

DELAI = 15


def _statut(url: str) -> tuple[int, str]:
    """Code de réponse pour `url`, et un extrait du corps en cas d'échec."""
    # Adresse construite ici même, jamais reçue de l'extérieur.
    entetes = {"User-Agent": "ITEAG-verification/1.0"}
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    if site_url:
        entetes["Referer"] = f"{site_url}/"
    requete = urllib.request.Request(url, headers=entetes)  # noqa: S310
    try:
        with urllib.request.urlopen(requete, timeout=DELAI) as reponse:  # noqa: S310 — adresse construite ici
            return reponse.status, reponse.read(2048).decode("utf-8", "replace")
    except urllib.error.HTTPError as erreur:
        return erreur.code, erreur.read(200).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as erreur:
        return 0, str(erreur)


def _premier_segment(manifeste: str) -> str:
    """Première ressource référencée par un manifeste HLS — segment ou sous-manifeste."""
    for ligne in manifeste.splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#"):
            return ligne
    return ""


class Command(BaseCommand):
    help = "Vérifie les identifiants Bunny : clé d'API du dépôt, puis signature de lecture sur une vidéo réelle."

    def add_arguments(self, analyseur):
        analyseur.add_argument(
            "identifiant",
            nargs="?",
            default="",
            help="Identifiant d'une vidéo de la bibliothèque. Sans lui, seule la clé d'API est éprouvée.",
        )
        analyseur.add_argument("--ip", default="", help="Adresse à lier, si la liaison est activée")
        analyseur.add_argument("--ttl", type=int, default=300, help="Durée de validité du jeton, en secondes")

    def handle(self, *args, **options):
        identifiant = options["identifiant"]

        self._eprouver_la_cle_de_depot()

        if not identifiant:
            self.stdout.write(self.style.MIGRATE_HEADING("\nLecture"))
            self.stdout.write("  Non éprouvée — passer l'identifiant d'une vidéo pour la contrôler aussi.")
            return

        zone = getattr(settings, "BUNNY_ZONE_DIFFUSION", "").rstrip("/")
        cle = getattr(settings, "BUNNY_CLE_SIGNATURE", "")
        if not zone or not cle:
            raise CommandError(
                "BUNNY_ZONE_DIFFUSION et BUNNY_CLE_SIGNATURE doivent être renseignés.\n"
                "La zone ressemble à « https://vz-xxxx.b-cdn.net » ; la clé est celle\n"
                "de l'authentification par jeton de la zone de diffusion."
            )

        backend = BunnyStreamVideo()
        expiration = int(time.time()) + options["ttl"]
        adresse_ip = options["ip"]

        self.stdout.write(self.style.MIGRATE_HEADING("\nLecture — configuration de la zone"))
        self.stdout.write(f"  Zone de diffusion   {zone}")
        self.stdout.write(f"  Clé de signature    {'renseignée (' + str(len(cle)) + ' caractères)'}")
        self.stdout.write(f"  Liaison d'adresse   {'oui — ' + adresse_ip if adresse_ip else 'non'}")
        self.stdout.write(f"  Référent simulé     {getattr(settings, 'SITE_URL', '') or 'aucun'}")
        self.stdout.write(f"  Vidéo               {identifiant}")

        # ── 1. Le manifeste ──────────────────────────────────────────
        url_manifeste = backend.url_signee(identifiant, expiration, adresse_ip)

        self.stdout.write(self.style.MIGRATE_HEADING("\n1. Manifeste"))
        code, corps = _statut(url_manifeste)
        self._dire(code, "manifeste")

        if code != 200:
            self._diagnostiquer_signature(backend, zone, identifiant, expiration, adresse_ip)
            return

        # ── 2. Un segment ────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING("\n2. Segment"))
        segment = _premier_segment(corps)
        if not segment:
            self.stdout.write(self.style.WARNING("  Aucun segment référencé — manifeste vide ou inattendu."))
            return
        self.stdout.write(f"  Référencé par le manifeste : {segment[:80]}")

        url_segment = urljoin(url_manifeste, segment)
        code_segment, _ = _statut(url_segment)
        self._dire(code_segment, "segment")

        # ── 3. Verdict ───────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING("\nVerdict"))
        if code_segment == 200:
            self.stdout.write(self.style.SUCCESS("  Manifeste et segment acceptés : la lecture protégée fonctionne."))
        else:
            self.stdout.write(
                self.style.ERROR(
                    "  Le manifeste passe mais pas le segment. C'est la signature de\n"
                    "  répertoire qui est en cause : vérifiez que le manifeste référence\n"
                    "  des chemins relatifs, et qu'aucune restriction de domaine, pays\n"
                    "  ou référent ne s'ajoute dans la bibliothèque Bunny."
                )
            )

    def _eprouver_la_cle_de_depot(self) -> None:
        """La clé qui autorise à déposer — celle dont le refus sortait en 401 brut.

        Un refus arrête la commande. Ce n'est pas un excès de zèle : le dépôt est
        le seul chemin par lequel un enseignant sans compte Bunny crée une leçon
        vidéo. Refusé, il ne peut plus créer la leçon, donc plus lui attacher de
        ressource. Laisser le contrôle continuer en signalant la chose au passage
        reviendrait à la faire glisser sous les lignes suivantes.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nDépôt — clé d'API de la bibliothèque"))

        bibliotheque = str(getattr(settings, "BUNNY_STREAM_LIBRARY_ID", "") or "").strip()
        cle = str(getattr(settings, "BUNNY_STREAM_API_KEY", "") or "").strip()

        self.stdout.write(f"  Bibliothèque        {bibliotheque or 'non renseignée'}")
        self.stdout.write(f"  Clé d'API           {f'renseignée ({len(cle)} caractères)' if cle else 'non renseignée'}")

        if not bibliotheque or not cle:
            self.stdout.write(
                self.style.WARNING(
                    "  Dépôt non configuré — l'écran de leçon ne proposera que le lien.\n"
                    "  Renseigner BUNNY_STREAM_LIBRARY_ID et BUNNY_STREAM_API_KEY pour l'ouvrir."
                )
            )
            return

        try:
            total = depot.verifier_acces()
        except depot.TeleversementBunnyIndisponible as erreur:
            raise CommandError(f"Dépôt refusé.\n{erreur}") from erreur

        self.stdout.write(self.style.SUCCESS(f"  Accepté — la bibliothèque contient {total} vidéo(s)."))

    def _dire(self, code: int, quoi: str) -> None:
        if code == 200:
            self.stdout.write(self.style.SUCCESS(f"  200 — {quoi} accepté."))
        elif code == 403:
            self.stdout.write(self.style.ERROR(f"  403 — {quoi} refusé : jeton invalide, expiré, ou restriction."))
        elif code == 404:
            self.stdout.write(self.style.ERROR(f"  404 — {quoi} introuvable : identifiant ou zone erronés."))
        elif code == 0:
            self.stdout.write(self.style.ERROR(f"  Injoignable — {quoi} : réseau, ou nom de zone erroné."))
        else:
            self.stdout.write(self.style.WARNING(f"  {code} — {quoi}."))

    def _diagnostiquer_signature(self, backend, zone, identifiant, expiration, adresse_ip) -> None:
        """
        Le manifeste est refusé alors que l'URL suit le format Bunny actuel.

        On éprouve aussi le fichier sans jeton pour distinguer une zone non
        protégée d'une restriction ou d'une clé incorrecte.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nDiagnostic — configuration Bunny"))
        url_sans_jeton = f"{zone}{backend._chemin(identifiant)}"
        code_sans_jeton, _ = _statut(url_sans_jeton)
        self.stdout.write(f"  {code_sans_jeton or '---'}  manifeste sans jeton")

        if code_sans_jeton == 200:
            self.stdout.write(
                self.style.WARNING(
                    "  Le manifeste est public alors que l'adresse signée est refusée.\n"
                    "  Vérifiez que l'authentification avancée par jeton est activée\n"
                    "  sur la zone de diffusion correspondant à cette clé."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "  L'URL utilise HMAC-SHA256 et un jeton de chemin, le format Bunny\n"
                    "  requis pour HLS. Vérifiez dans Stream > Bibliothèque > Sécurité :\n"
                    "    · la clé copiée est bien celle de cette zone ;\n"
                    "    · l'identifiant de la vidéo existe et son encodage est terminé ;\n"
                    "    · le domaine de SITE_URL figure dans « Allowed domains », sans\n"
                    "      https://, si « Block Direct URL File Access » est activé ;\n"
                    "    · aucune restriction d'IP, de pays ou de référent ne s'ajoute."
                )
            )
