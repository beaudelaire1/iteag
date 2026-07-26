"""
Éprouve la signature Bunny contre le compte réel.

Pourquoi cette commande existe : la signature est la seule partie du dispositif
vidéo qui ne peut pas être vérifiée hors ligne. Nos tests confirment que le
jeton est *formé* comme nous l'avons décidé — ils ne peuvent pas confirmer que
le CDN l'*accepte*. Seul un aller-retour avec le compte le dit.

Elle vérifie les deux étapes, car la première réussit souvent quand la seconde
échoue : le manifeste se charge, puis chaque segment est refusé, et la lecture
s'arrête après quelques secondes en paraissant d'abord fonctionner. C'est le
défaut qu'un jeton de fichier, au lieu d'un jeton de répertoire, produit.

Aucun secret n'est affiché : ni la clé, ni le jeton complet.
"""

import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.elearning.diffusion import BunnyStreamVideo, base_a_signer, condenser

DELAI = 15


def _statut(url: str) -> tuple[int, str]:
    """Code de réponse pour `url`, et un extrait du corps en cas d'échec."""
    # Adresse construite ici même, jamais reçue de l'extérieur.
    requete = urllib.request.Request(url, headers={"User-Agent": "ITEAG-verification/1.0"})  # noqa: S310
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
    help = "Vérifie la signature Bunny sur une vidéo réelle : manifeste puis segment."

    def add_arguments(self, analyseur):
        analyseur.add_argument("identifiant", help="Identifiant de la vidéo dans la bibliothèque Bunny")
        analyseur.add_argument("--ip", default="", help="Adresse à lier, si la liaison est activée")
        analyseur.add_argument("--ttl", type=int, default=300, help="Durée de validité du jeton, en secondes")

    def handle(self, *args, **options):
        zone = getattr(settings, "BUNNY_ZONE_DIFFUSION", "").rstrip("/")
        cle = getattr(settings, "BUNNY_CLE_SIGNATURE", "")
        if not zone or not cle:
            raise CommandError(
                "BUNNY_ZONE_DIFFUSION et BUNNY_CLE_SIGNATURE doivent être renseignés.\n"
                "La zone ressemble à « https://vz-xxxx.b-cdn.net » ; la clé est celle\n"
                "de l'authentification par jeton de la zone de diffusion."
            )

        identifiant = options["identifiant"]
        backend = BunnyStreamVideo()
        expiration = int(time.time()) + options["ttl"]
        adresse_ip = options["ip"]

        self.stdout.write(self.style.MIGRATE_HEADING("\nConfiguration"))
        self.stdout.write(f"  Zone de diffusion   {zone}")
        self.stdout.write(f"  Clé de signature    {'renseignée (' + str(len(cle)) + ' caractères)'}")
        self.stdout.write(f"  Liaison d'adresse   {'oui — ' + adresse_ip if adresse_ip else 'non'}")
        self.stdout.write(f"  Vidéo               {identifiant}")

        # ── 1. Le manifeste ──────────────────────────────────────────
        requete = backend.requete_signee(identifiant, expiration, adresse_ip)
        url_manifeste = f"{zone}{backend.repertoire(identifiant)}playlist.m3u8?{requete}"

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

        base_manifeste = f"{zone}{backend.repertoire(identifiant)}playlist.m3u8"
        url_segment = urljoin(base_manifeste, segment)

        if "?" in segment:
            self.stdout.write("  Le manifeste porte déjà un jeton sur ses segments.")
            code_segment, _ = _statut(url_segment)
        else:
            code_nu, _ = _statut(url_segment)
            code_segment, _ = _statut(f"{url_segment}?{requete}")
            if code_nu == 200:
                self.stdout.write(self.style.WARNING("  Le segment répond sans jeton : la zone n'est pas protégée."))
        self._dire(code_segment, "segment")

        # ── 3. Verdict ───────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING("\nVerdict"))
        if code_segment == 200:
            self.stdout.write(self.style.SUCCESS("  Manifeste et segment acceptés : la lecture protégée fonctionne."))
        else:
            self.stdout.write(
                self.style.ERROR(
                    "  Le manifeste passe mais pas le segment. C'est la signature de\n"
                    "  répertoire qui est en cause : vérifiez que « Token Authentication »\n"
                    "  est bien activée sur la zone, et qu'aucune autre restriction\n"
                    "  (pays, référent) ne s'y ajoute."
                )
            )

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
        Le manifeste est refusé : on essaie les variantes documentées.

        La composition exacte de la chaîne signée varie d'une version à l'autre
        de la documentation Bunny — notamment la place de l'adresse IP et la
        présence du jeton de répertoire. Plutôt que de trancher au jugé, on
        demande au CDN laquelle il accepte.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nDiagnostic — variantes de signature"))
        repertoire = backend.repertoire(identifiant)
        chemin_fichier = f"{repertoire}playlist.m3u8"
        cle = settings.BUNNY_CLE_SIGNATURE

        variantes = {
            "répertoire, IP avant les paramètres": (
                repertoire,
                {"token_path": repertoire},
                adresse_ip,
                True,
            ),
            "répertoire, IP après les paramètres": (
                repertoire,
                {"token_path": repertoire},
                adresse_ip,
                False,
            ),
            "fichier seul (sans token_path)": (chemin_fichier, {}, adresse_ip, True),
        }

        gagnante = None
        for libelle, (chemin, parametres, ip, ip_avant) in variantes.items():
            if ip_avant:
                base = base_a_signer(cle, chemin, expiration, parametres, ip)
            else:
                donnees = "&".join(f"{n}={parametres[n]}" for n in sorted(parametres))
                base = f"{cle}{chemin}{expiration}{donnees}{ip}"
            jeton = condenser(base)
            requete = f"token={jeton}&expires={expiration}"
            if parametres:
                from urllib.parse import quote

                requete += f"&token_path={quote(repertoire, safe='')}"
            code, _ = _statut(f"{zone}{chemin_fichier}?{requete}")
            marque = "✓" if code == 200 else " "
            self.stdout.write(f"  {marque} {code or '---'}  {libelle}")
            if code == 200 and gagnante is None:
                gagnante = libelle

        self.stdout.write("")
        if gagnante:
            self.stdout.write(
                self.style.WARNING(
                    f"  La variante « {gagnante} » est acceptée alors que la nôtre ne l'est pas.\n"
                    "  Signalez-le : la composition de la chaîne signée doit être ajustée."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "  Aucune variante acceptée. Vérifiez d'abord, dans la console Bunny :\n"
                    "    · « Token Authentication » activée sur la zone de diffusion ;\n"
                    "    · la clé copiée est bien celle de cette zone ;\n"
                    "    · l'identifiant de la vidéo existe et son encodage est terminé ;\n"
                    "    · aucun blocage par pays ou par référent."
                )
            )
