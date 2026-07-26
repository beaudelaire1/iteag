"""
Import du catalogue de la bibliothèque — CDC BIB-004.

L'export fourni par l'ITEAG n'a pas de format garanti : les en-têtes varient,
l'encodage aussi. La commande s'adapte plutôt que d'exiger un gabarit exact,
et refuse clairement ce qu'elle ne sait pas interpréter.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.formations.models import Discipline
from apps.library.models import NoticeBibliographique

# Chaque champ accepte plusieurs intitulés : on rencontre « titre », « Titre »,
# « TITLE », « intitulé »… selon l'outil qui a produit l'export.
CORRESPONDANCES = {
    "titre": ["titre", "title", "intitule", "intitulé", "ouvrage", "livre"],
    "auteur": ["auteur", "auteurs", "author", "authors", "redacteur"],
    "editeur": ["editeur", "éditeur", "publisher", "edition", "édition"],
    "date_publication": ["date_publication", "date", "annee", "année", "year", "publication"],
    "isbn": ["isbn", "ean", "issn"],
    "mots_cles": ["mots_cles", "mots-clés", "mots cles", "keywords", "sujets", "themes", "thèmes"],
    "cote": ["cote", "cotation", "reference", "référence", "call_number"],
    "description": ["description", "resume", "résumé", "abstract", "note", "notes"],
    "discipline": ["discipline", "matiere", "matière", "domaine", "categorie", "catégorie"],
}

ENCODAGES = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]


def normaliser(entete: str) -> str:
    return entete.strip().lower().replace("’", "'")


class Command(BaseCommand):
    help = "Importe les notices bibliographiques depuis un fichier CSV."

    def add_arguments(self, parseur):
        parseur.add_argument("fichier", type=str, help="Chemin du fichier CSV à importer.")
        parseur.add_argument(
            "--separateur",
            default=None,
            help="Séparateur de colonnes. Détecté automatiquement si absent.",
        )
        parseur.add_argument(
            "--simulation",
            action="store_true",
            help="Analyse le fichier et affiche le résultat sans rien écrire.",
        )
        parseur.add_argument(
            "--vider",
            action="store_true",
            help="Supprime les notices existantes avant l'import.",
        )

    def handle(self, *args, **options):
        chemin = Path(options["fichier"])
        if not chemin.exists():
            raise CommandError(f"Fichier introuvable : {chemin}")

        texte = self._lire(chemin)
        separateur = options["separateur"] or self._detecter_separateur(texte)
        lecteur = csv.DictReader(texte.splitlines(), delimiter=separateur)

        if not lecteur.fieldnames:
            raise CommandError("Le fichier ne comporte pas de ligne d'en-tête exploitable.")

        colonnes = self._associer_colonnes(lecteur.fieldnames)
        if "titre" not in colonnes:
            raise CommandError(
                "Aucune colonne de titre reconnue. En-têtes trouvés : "
                + ", ".join(lecteur.fieldnames)
                + ". Renommez la colonne du titre ou précisez --separateur."
            )

        self.stdout.write(f"Séparateur : « {separateur} »")
        self.stdout.write("Colonnes reconnues : " + ", ".join(f"{k} ← {v}" for k, v in colonnes.items()))

        lignes = list(lecteur)
        importees, ignorees, erreurs = self._importer(lignes, colonnes, options)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"{importees} notice(s) importée(s)"))
        if ignorees:
            self.stdout.write(self.style.WARNING(f"{ignorees} ligne(s) sans titre, ignorée(s)"))
        for message in erreurs[:10]:
            self.stdout.write(self.style.ERROR(message))
        if len(erreurs) > 10:
            self.stdout.write(self.style.ERROR(f"… et {len(erreurs) - 10} autre(s) erreur(s)"))
        if options["simulation"]:
            self.stdout.write(self.style.WARNING("Simulation : aucune écriture effectuée."))

    # ── Lecture ────────────────────────────────

    def _lire(self, chemin: Path) -> str:
        """Lit le fichier en essayant les encodages courants d'un export bureautique."""
        for encodage in ENCODAGES:
            try:
                return chemin.read_text(encoding=encodage)
            except UnicodeDecodeError:
                continue
        raise CommandError(f"Encodage non reconnu. Essayés : {', '.join(ENCODAGES)}.")

    @staticmethod
    def _detecter_separateur(texte: str) -> str:
        premiere = texte.splitlines()[0] if texte.splitlines() else ""
        candidats = {sep: premiere.count(sep) for sep in (";", ",", "\t", "|")}
        meilleur = max(candidats, key=candidats.get)
        return meilleur if candidats[meilleur] else ","

    @staticmethod
    def _associer_colonnes(entetes: list[str]) -> dict[str, str]:
        """Associe chaque champ du modèle à la colonne du fichier qui lui correspond."""
        trouvees = {}
        normalises = {normaliser(e): e for e in entetes if e}
        for champ, variantes in CORRESPONDANCES.items():
            for variante in variantes:
                if variante in normalises:
                    trouvees[champ] = normalises[variante]
                    break
        return trouvees

    # ── Écriture ───────────────────────────────

    def _importer(self, lignes, colonnes, options):
        importees = ignorees = 0
        erreurs = []
        disciplines = {}

        with transaction.atomic():
            if options["vider"] and not options["simulation"]:
                nombre, _ = NoticeBibliographique.objects.all().delete()
                self.stdout.write(self.style.WARNING(f"{nombre} notice(s) existante(s) supprimée(s)"))

            for numero, ligne in enumerate(lignes, start=2):
                valeurs = {champ: (ligne.get(colonne) or "").strip() for champ, colonne in colonnes.items()}

                if not valeurs.get("titre"):
                    ignorees += 1
                    continue

                discipline = None
                nom_discipline = valeurs.pop("discipline", "")
                if nom_discipline:
                    discipline = self._discipline(nom_discipline, disciplines, options["simulation"])

                try:
                    if not options["simulation"]:
                        NoticeBibliographique.objects.create(
                            titre=valeurs["titre"][:500],
                            auteur=valeurs.get("auteur", "")[:300],
                            editeur=valeurs.get("editeur", "")[:200],
                            date_publication=valeurs.get("date_publication", "")[:50],
                            isbn=valeurs.get("isbn", "")[:20],
                            mots_cles=valeurs.get("mots_cles", ""),
                            cote=valeurs.get("cote", "")[:50],
                            description=valeurs.get("description", ""),
                            discipline=discipline,
                        )
                    importees += 1
                except Exception as erreur:  # noqa: BLE001 — une ligne fautive n'arrête pas l'import
                    erreurs.append(f"Ligne {numero} : {erreur}")

            if options["simulation"]:
                transaction.set_rollback(True)

        return importees, ignorees, erreurs

    @staticmethod
    def _discipline(nom: str, cache: dict, simulation: bool):
        """Rattache à une discipline existante, ou la crée à la volée."""
        cle = nom.lower()
        if cle in cache:
            return cache[cle]

        discipline = Discipline.objects.filter(nom__iexact=nom).first()
        if discipline is None and not simulation:
            discipline = Discipline.objects.create(nom=nom[:120], slug=slugify(nom)[:120])
        cache[cle] = discipline
        return discipline
