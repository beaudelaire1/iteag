"""
Peuple les dossiers de candidature.

Usage : python manage.py seed_candidatures

C'est la porte d'entrée du travail du secrétariat, et l'écran le plus visité du
portail. Les dossiers couvrent les cinq états du workflow d'admission, avec une
majorité en attente de décision : une file où tout est déjà tranché ne montre
pas à quoi sert l'écran.

L'historique de statut est écrit aussi. Sans lui, le détail d'un dossier
accepté affiche une décision sans trace de la manière dont elle a été prise,
alors que la traçabilité est précisément ce que cet écran promet.
"""

import secrets
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.admissions.models import DossierCandidature, HistoriqueStatut
from apps.formations.models import Parcours

# (prénom, nom, ville, église, fondatrice, statut, jours d'ancienneté)
CANDIDATS = [
    ("Roselyne", "Édouard", "Le Moule", "Église évangélique du Moule", True, "soumis", 2),
    ("Frantz", "Bélizaire", "Cayenne", "Assemblée de Dieu de Cayenne", False, "soumis", 4),
    ("Micheline", "Ranguin", "Sainte-Anne", "Église baptiste de Sainte-Anne", False, "soumis", 6),
    ("Olivier", "Tacita", "Schoelcher", "Mission évangélique de Schoelcher", False, "en_examen", 9),
    ("Huguette", "Sylvestre", "Petit-Bourg", "Église du Plein Évangile", True, "en_examen", 12),
    ("Dominique", "Anselme", "Kourou", "Église protestante de Kourou", False, "incomplet", 15),
    ("Yolande", "Mardaye", "Saint-Laurent-du-Maroni", "Église évangélique du Maroni", False, "incomplet", 18),
    ("Serge", "Placide", "Basse-Terre", "Église baptiste de Basse-Terre", True, "accepte", 30),
    ("Aline", "Coridon", "Rivière-Salée", "Église évangélique de Rivière-Salée", False, "accepte", 34),
    ("Bertrand", "Nabajoth", "Lamentin", "Communauté chrétienne du Lamentin", False, "refuse", 45),
]

MOTIVATION = (
    "Engagé depuis plusieurs années dans le service au sein de mon Église locale, je souhaite "
    "asseoir ma pratique sur une formation théologique structurée. L'accompagnement des jeunes "
    "et la prédication occupent l'essentiel de mon ministère actuel, et je mesure le besoin "
    "d'outils exégétiques que je ne possède pas encore. La formule des sessions de l'ITEAG me "
    "permet de me former sans quitter mes responsabilités."
)

MANQUANTS = "Copie de la pièce d'identité illisible. Relevé du dernier diplôme non joint."


class Command(BaseCommand):
    help = "Insère des dossiers de candidature couvrant les cinq états du workflow d'admission."

    @transaction.atomic
    def handle(self, *args, **options):
        parcours = list(Parcours.objects.all())
        if not parcours:
            self.stdout.write(self.style.ERROR("Aucun parcours — lancez d'abord « manage.py seed_formations »."))
            return

        maintenant = timezone.now()
        crees = 0

        for index, (prenom, nom, ville, eglise, fondatrice, statut, anciennete) in enumerate(CANDIDATS):
            email = f"{prenom}.{nom}@example.org".lower().replace(" ", "")
            if DossierCandidature.objects.filter(email=email).exists():
                continue

            soumission = maintenant - timedelta(days=anciennete)
            dossier = DossierCandidature.objects.create(
                nom=nom,
                prenom=prenom,
                email=email,
                telephone="0690 12 34 56",
                date_naissance=timezone.localdate().replace(year=1988 + index % 12),
                parcours_souhaite=parcours[index % len(parcours)],
                motivations=MOTIVATION,
                eglise=eglise,
                eglise_fondatrice=fondatrice,
                statut=statut,
                date_soumission=soumission,
                motif_refus=(
                    "Le dossier ne satisfait pas au niveau d'entrée requis pour ce parcours. "
                    "Une candidature au parcours d'initiation reste possible."
                    if statut == "refuse"
                    else ""
                ),
                elements_manquants=MANQUANTS if statut == "incomplet" else "",
                notes_internes=(
                    f"Candidat de {ville}. Recommandé par le pasteur de son Église."
                    if index % 3 == 0
                    else f"Candidat de {ville}."
                ),
                token_suivi=secrets.token_urlsafe(24)[:32],
            )
            crees += 1

            # Un dossier tranché sans historique afficherait une décision sortie
            # de nulle part, alors que l'écran promet la traçabilité.
            if statut != "soumis":
                HistoriqueStatut.objects.create(
                    dossier=dossier,
                    ancien_statut="soumis",
                    nouveau_statut="en_examen",
                    commentaire="Dossier pris en charge par le secrétariat.",
                )
            if statut in ("accepte", "refuse", "incomplet"):
                HistoriqueStatut.objects.create(
                    dossier=dossier,
                    ancien_statut="en_examen",
                    nouveau_statut=statut,
                    commentaire={
                        "accepte": "Admis. Convocation à la prochaine session à envoyer.",
                        "refuse": "Niveau d'entrée non atteint pour le parcours demandé.",
                        "incomplet": "Pièces manquantes réclamées au candidat par courriel.",
                    }[statut],
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Admissions : {crees} dossier(s) créé(s), {DossierCandidature.objects.count()} au total."
            )
        )
