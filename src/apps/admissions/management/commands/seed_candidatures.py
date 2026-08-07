"""
Peuple les dossiers de candidature.

Usage : python manage.py seed_candidatures
"""

import secrets
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.admissions.models import DemandePieces, DossierCandidature, HistoriqueStatut, PieceDemandee
from apps.formations.models import Parcours

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

        pieces = self._seed_pieces()
        self.stdout.write(
            self.style.SUCCESS(
                f"Admissions : {crees} dossier(s) créé(s), {DossierCandidature.objects.count()} au total, "
                f"{pieces} pièce(s) répartie(s) dans des demandes groupées."
            )
        )

    def _seed_pieces(self) -> int:
        """Crée un exemple cohérent par état de demande, jamais un lot mixte."""
        from django.core.files.base import ContentFile

        total = 0
        maintenant = timezone.now()
        echeance = timezone.localdate() + timedelta(days=21)

        for dossier in DossierCandidature.objects.filter(statut=DossierCandidature.Statut.ACCEPTE):
            if dossier.demandes_pieces.exists() or dossier.pieces_demandees.exists():
                continue

            scenarios = [
                (
                    DemandePieces.Statut.VALIDEE,
                    "Les pièces d'état civil ont été vérifiées.",
                    [
                        (
                            "Acte de naissance",
                            "Copie intégrale de moins de trois mois.",
                            PieceDemandee.Statut.VALIDEE,
                            "",
                        )
                    ],
                ),
                (
                    DemandePieces.Statut.A_VERIFIER,
                    "Merci de transmettre les justificatifs de formation dans un seul envoi.",
                    [
                        (
                            "Copie du dernier diplôme",
                            "Avec relevé de notes si disponible.",
                            PieceDemandee.Statut.DEPOSEE,
                            "",
                        ),
                        (
                            "Photo d'identité",
                            "Format identité, sur fond clair.",
                            PieceDemandee.Statut.DEPOSEE,
                            "",
                        ),
                    ],
                ),
                (
                    DemandePieces.Statut.A_CORRIGER,
                    "Le justificatif doit être récent et parfaitement lisible.",
                    [
                        (
                            "Justificatif de domicile",
                            "De moins de trois mois : facture, quittance ou attestation.",
                            PieceDemandee.Statut.REFUSEE,
                            "Le document date de plus de trois mois.",
                        )
                    ],
                ),
                (
                    DemandePieces.Statut.A_FOURNIR,
                    "Ces documents complètent le dossier administratif.",
                    [
                        (
                            "Lettre de recommandation pastorale",
                            "Rédigée par le responsable de votre Église locale.",
                            PieceDemandee.Statut.DEMANDEE,
                            "",
                        ),
                        (
                            "Curriculum vitæ",
                            "Parcours de formation et expérience de service.",
                            PieceDemandee.Statut.DEMANDEE,
                            "",
                        ),
                    ],
                ),
            ]

            for statut_demande, message, pieces in scenarios:
                demande = DemandePieces.objects.create(
                    dossier=dossier,
                    message=message,
                    date_limite=echeance,
                    statut=statut_demande,
                    date_soumission=maintenant if statut_demande == DemandePieces.Statut.A_VERIFIER else None,
                    date_decision=(
                        maintenant
                        if statut_demande in (DemandePieces.Statut.VALIDEE, DemandePieces.Statut.A_CORRIGER)
                        else None
                    ),
                )
                for libelle, precisions, statut_piece, motif in pieces:
                    piece = PieceDemandee(
                        dossier=dossier,
                        demande=demande,
                        libelle=libelle,
                        precisions=precisions,
                        statut=statut_piece,
                        date_limite=echeance,
                        motif_refus=motif,
                        date_depot=(maintenant if statut_piece != PieceDemandee.Statut.DEMANDEE else None),
                        date_decision=(
                            maintenant
                            if statut_piece in (PieceDemandee.Statut.VALIDEE, PieceDemandee.Statut.REFUSEE)
                            else None
                        ),
                    )
                    if statut_piece != PieceDemandee.Statut.DEMANDEE:
                        piece.fichier.save(
                            f"{dossier.pk}-{libelle[:20].lower().replace(' ', '-')}.pdf",
                            ContentFile(b"%PDF-1.4 piece de demonstration\n%%EOF\n"),
                            save=False,
                        )
                    piece.save()
                    total += 1
        return total
