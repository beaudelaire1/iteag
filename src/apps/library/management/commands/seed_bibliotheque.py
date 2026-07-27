"""
Peuple le catalogue de la bibliothèque.

Usage : python manage.py seed_bibliotheque

Les notices couvrent les cinq disciplines afin que la recherche par discipline
ait quelque chose à filtrer : un catalogue concentré sur une seule matière
donne l'illusion de fonctionner tant qu'on ne touche pas aux filtres.
"""

from django.core.management.base import BaseCommand

from apps.formations.models import Discipline
from apps.library.models import NoticeBibliographique

# (titre, auteur, éditeur, année, isbn, cote, discipline, mots-clés, disponible)
NOTICES = [
    (
        "Introduction à l'Ancien Testament",
        "Thomas Römer",
        "Labor et Fides",
        "2009",
        "9782830913682",
        "AT-101",
        "Ancien Testament",
        "pentateuque, exégèse, histoire d'Israël",
        True,
    ),
    (
        "Le Pentateuque en question",
        "Albert de Pury",
        "Labor et Fides",
        "2002",
        "9782830910339",
        "AT-114",
        "Ancien Testament",
        "pentateuque, sources, critique littéraire",
        True,
    ),
    (
        "Les Prophètes d'Israël",
        "Jacques Vermeylen",
        "Cerf",
        "2013",
        "9782204100236",
        "AT-207",
        "Ancien Testament",
        "prophétisme, Ésaïe, Jérémie",
        False,
    ),
    (
        "Introduction au Nouveau Testament",
        "Daniel Marguerat",
        "Labor et Fides",
        "2008",
        "9782830913804",
        "NT-101",
        "Nouveau Testament",
        "évangiles, épîtres, contexte gréco-romain",
        True,
    ),
    (
        "L'Évangile selon Jean",
        "Jean Zumstein",
        "Labor et Fides",
        "2014",
        "9782830915297",
        "NT-142",
        "Nouveau Testament",
        "johannique, christologie, commentaire",
        True,
    ),
    (
        "Paul, une théologie en construction",
        "Andreas Dettwiler",
        "Labor et Fides",
        "2004",
        "9782830911237",
        "NT-233",
        "Nouveau Testament",
        "paulinisme, justification, ecclésiologie",
        True,
    ),
    (
        "Théologie systématique",
        "Wayne Grudem",
        "Excelsis",
        "2010",
        "9782755001570",
        "TS-100",
        "Théologie systématique",
        "doctrine, dogmatique, christologie",
        True,
    ),
    (
        "Institution de la religion chrétienne",
        "Jean Calvin",
        "Kerygma",
        "2009",
        "9782903184308",
        "TS-115",
        "Théologie systématique",
        "réforme, calvinisme, dogmatique",
        True,
    ),
    (
        "Dogmatique pour la prédication de l'Évangile",
        "Karl Barth",
        "Labor et Fides",
        "1985",
        "9782830900187",
        "TS-260",
        "Théologie systématique",
        "barth, révélation, prédication",
        False,
    ),
    (
        "Histoire du christianisme",
        "Jean Comby",
        "Cerf",
        "2003",
        "9782204070232",
        "HE-100",
        "Histoire de l'Église",
        "patristique, réforme, missions",
        True,
    ),
    (
        "Les Pères de l'Église",
        "Adalbert Hamman",
        "Desclée",
        "1998",
        "9782718906201",
        "HE-118",
        "Histoire de l'Église",
        "patristique, antiquité chrétienne",
        True,
    ),
    (
        "Le christianisme dans la Caraïbe",
        "Laënnec Hurbon",
        "Karthala",
        "2000",
        "9782845860742",
        "HE-305",
        "Histoire de l'Église",
        "caraïbe, antilles, syncrétisme, mission",
        True,
    ),
    (
        "Théologie pratique et ministère pastoral",
        "Bernard Kaempf",
        "Presses universitaires de Strasbourg",
        "1997",
        "9782868201317",
        "TP-101",
        "Théologie pratique",
        "pastorale, homilétique, accompagnement",
        True,
    ),
    (
        "L'art de prêcher",
        "Haddon Robinson",
        "Sator",
        "1992",
        "9782853001281",
        "TP-140",
        "Théologie pratique",
        "homilétique, prédication expositive",
        True,
    ),
    (
        "Conduire une Église locale",
        "Alfred Kuen",
        "Emmaüs",
        "2004",
        "9782828700683",
        "TP-222",
        "Théologie pratique",
        "ecclésiologie, gouvernance, diaconat",
        True,
    ),
]


class Command(BaseCommand):
    help = "Insère un catalogue de notices bibliographiques couvrant toutes les disciplines."

    def handle(self, *args, **options):
        disciplines = {d.nom: d for d in Discipline.objects.all()}
        if not disciplines:
            self.stdout.write(
                self.style.WARNING("Aucune discipline en base — lancez d'abord « manage.py seed_formations ».")
            )

        crees = 0
        for titre, auteur, editeur, annee, isbn, cote, discipline, mots, dispo in NOTICES:
            _notice, cree = NoticeBibliographique.objects.update_or_create(
                cote=cote,
                defaults={
                    "titre": titre,
                    "auteur": auteur,
                    "editeur": editeur,
                    "date_publication": annee,
                    "isbn": isbn,
                    "mots_cles": mots,
                    "discipline": disciplines.get(discipline),
                    "description": f"{titre} — {auteur}, {editeur}, {annee}.",
                    "disponible": dispo,
                },
            )
            crees += int(cree)

        total = NoticeBibliographique.objects.count()
        self.stdout.write(self.style.SUCCESS(f"Bibliothèque : {crees} notice(s) créée(s), {total} au catalogue."))
