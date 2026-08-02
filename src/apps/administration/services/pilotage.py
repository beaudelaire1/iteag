"""
Chiffres de pilotage de l'institut.

Règle qui gouverne tout ce fichier : **aucun indicateur inventé**. Chaque
montant, chaque échéance, chaque alerte se déduit d'une donnée réellement
saisie. Un indicateur qu'on ne sait pas calculer proprement n'apparaît pas —
un tableau de bord dont on doute d'un chiffre ne sert plus à rien.

Le calcul vit ici plutôt que dans la vue : ce sont des règles de gestion
(qu'est-ce qui est « encaissé », qu'est-ce qui « reste dû »), et elles doivent
être testables sans passer par une requête HTTP.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    Paiement,
    ProfilEtudiant,
    SessionAcademique,
)
from apps.admissions.models import DossierCandidature
from apps.elearning.models import InscriptionModule, ModuleFormation, VideoAsset
from apps.lms.models import Evaluation

ZERO = Decimal("0.00")


# ══════════════════════════════════════════════
# Finances
# ══════════════════════════════════════════════


def finances(session_en_cours=None) -> dict:
    """Ce que l'institut a encaissé, attend et doit encore recouvrer.

    Les trois montants proviennent de deux sources distinctes, et il ne faut pas
    les confondre :

    - « encaissé » et « annoncé » viennent des paiements saisis ;
    - « restant dû » vient des demandes d'inscription non soldées. Une demande
      confirmée ne s'y trouve pas : elle a été réglée ou exonérée, c'est ce que
      la confirmation atteste.
    """
    confirme = Q(statut=Paiement.StatutPaiement.CONFIRME)
    en_attente = Q(statut=Paiement.StatutPaiement.EN_ATTENTE)
    agregats_paiements = {
        "encaisse_total": Sum("montant", filter=confirme, default=ZERO),
        "encaisse_nombre": Count("id", filter=confirme),
        "annonce_total": Sum("montant", filter=en_attente, default=ZERO),
        "annonce_nombre": Count("id", filter=en_attente),
    }
    if session_en_cours is not None:
        agregats_paiements["encaisse_session"] = Sum(
            "montant",
            filter=confirme & Q(session=session_en_cours),
            default=ZERO,
        )
    paiements = Paiement.objects.aggregate(**agregats_paiements)

    a_recouvrer = Q(
        statut__in=[
            DemandeInscriptionCours.Statut.SOUMISE,
            DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
        ]
    )
    relance = Q(statut=DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE)
    demandes = DemandeInscriptionCours.objects.aggregate(
        restant_du_total=Sum("montant_du", filter=a_recouvrer, default=ZERO),
        restant_du_nombre=Count("id", filter=a_recouvrer),
        relance_total=Sum("montant_du", filter=relance, default=ZERO),
    )

    resultat = {**paiements, **demandes}
    if session_en_cours is not None:
        resultat["session_finances"] = session_en_cours
    return resultat


# ══════════════════════════════════════════════
# Échéances
# ══════════════════════════════════════════════


@dataclass(frozen=True)
class Echeance:
    libelle: str
    date: object
    detail: str
    url: str

    @property
    def jours_restants(self) -> int:
        return (self.date - timezone.localdate()).days


def echeances(horizon_jours: int = 60, limite: int = 6) -> list[Echeance]:
    """Les dates qui approchent et qui demandent une décision.

    Deux natures seulement, parce que ce sont les deux que le modèle porte :
    la clôture des inscriptions d'un cours, et l'ouverture d'une session.
    """
    aujourd_hui = timezone.localdate()
    fin = aujourd_hui + timedelta(days=horizon_jours)
    trouvees: list[Echeance] = []

    limites = (
        CoursDeSession.objects.filter(
            inscriptions_ouvertes=True,
            statut=CoursDeSession.StatutCours.PROGRAMME,
            date_limite_inscription__gte=aujourd_hui,
            date_limite_inscription__lte=fin,
        )
        .select_related("cours", "session")
        .annotate(inscrits=Count("inscriptions"))
        .order_by("date_limite_inscription")[:limite]
    )
    for offre in limites:
        trouvees.append(
            Echeance(
                libelle=f"Clôture des inscriptions — {offre.cours.titre}",
                date=offre.date_limite_inscription,
                detail=f"{offre.inscrits} inscrit{'s' if offre.inscrits > 1 else ''} sur {offre.capacite} places",
                url=reverse("administration:course_offering_update", args=[offre.pk]),
            )
        )

    sessions = SessionAcademique.objects.filter(date_debut__gte=aujourd_hui, date_debut__lte=fin).order_by(
        "date_debut"
    )[:limite]
    for session in sessions:
        trouvees.append(
            Echeance(
                libelle=f"Ouverture de la session — {session.nom}",
                date=session.date_debut,
                detail=f"jusqu'au {session.date_fin.strftime('%d/%m/%Y')}",
                url=reverse("administration:session_update", args=[session.pk]),
            )
        )

    return sorted(trouvees, key=lambda echeance: echeance.date)[:limite]


# ══════════════════════════════════════════════
# Activité pédagogique
# ══════════════════════════════════════════════


def formations() -> dict:
    """Ce qui se déroule, ce qui vient, ce qui est achevé."""
    aujourd_hui = timezone.localdate()
    compteurs = CoursDeSession.objects.aggregate(
        cours_en_cours=Count(
            "id",
            filter=Q(
                session__date_debut__lte=aujourd_hui,
                session__date_fin__gte=aujourd_hui,
            ),
        ),
        cours_a_venir=Count("id", filter=Q(session__date_debut__gt=aujourd_hui)),
        cours_termines=Count("id", filter=Q(statut=CoursDeSession.StatutCours.TERMINE)),
    )
    return {
        **compteurs,
        "inscriptions_actives": ProfilEtudiant.objects.filter(
            inscriptions__cours_session__session__date_fin__gte=aujourd_hui
        )
        .distinct()
        .count(),
    }


def resultats() -> dict:
    """Notes publiées et corrections en attente.

    La moyenne ne porte que sur les notes publiées : une note en cours de
    correction n'est pas un résultat, et la faire entrer dans la moyenne
    donnerait un chiffre qui bouge sans qu'aucun étudiant n'ait rien passé.
    """
    publiee = Q(statut=Evaluation.StatutEvaluation.PUBLIE, note__isnull=False)
    agrege = Evaluation.objects.aggregate(
        moyenne=Avg("note", filter=publiee),
        nombre=Count("id", filter=publiee),
        reussite_nombre=Count("id", filter=publiee & Q(note__gte=10)),
        copies_a_corriger=Count(
            "id",
            filter=Q(
                statut__in=[
                    Evaluation.StatutEvaluation.SOUMIS,
                    Evaluation.StatutEvaluation.EN_CORRECTION,
                ]
            ),
        ),
    )

    return {
        "notes_publiees": agrege["nombre"] or 0,
        # Aucune note publiée : on ne montre pas « 0/20 », qui se lirait comme un
        # résultat catastrophique alors qu'il n'y a simplement rien à afficher.
        "note_moyenne": round(agrege["moyenne"], 2) if agrege["moyenne"] is not None else None,
        "reussite_nombre": agrege["reussite_nombre"],
        "copies_a_corriger": agrege["copies_a_corriger"],
    }


# ══════════════════════════════════════════════
# Alertes
# ══════════════════════════════════════════════


@dataclass(frozen=True)
class Alerte:
    libelle: str
    nombre: int
    url: str
    urgent: bool = False


def alertes(
    *,
    candidatures: int | None = None,
    inscriptions: int | None = None,
    acces: int | None = None,
    paiements: int | None = None,
    relecture: int | None = None,
) -> list[Alerte]:
    """Ce qui attend une décision, du plus urgent au moins pressant.

    Une alerte à zéro n'est pas affichée : un tableau de bord constellé de
    compteurs vides cesse d'être lu.
    """
    aujourd_hui = timezone.localdate()

    if candidatures is None:
        candidatures = DossierCandidature.objects.filter(
            statut__in=[
                DossierCandidature.Statut.SOUMIS,
                DossierCandidature.Statut.EN_EXAMEN,
                DossierCandidature.Statut.INCOMPLET,
            ]
        ).count()
    if inscriptions is None:
        inscriptions = DemandeInscriptionCours.objects.filter(
            statut__in=[
                DemandeInscriptionCours.Statut.SOUMISE,
                DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
            ]
        ).count()
    if acces is None:
        acces = InscriptionModule.objects.filter(statut=InscriptionModule.StatutAcces.DEMANDE).count()
    if paiements is None:
        paiements = Paiement.objects.filter(statut=Paiement.StatutPaiement.EN_ATTENTE).count()
    if relecture is None:
        relecture = ModuleFormation.objects.filter(statut=ModuleFormation.StatutPublication.RELECTURE).count()
    # Une vidéo non prête empêche la publication de son module : c'est le
    # premier incident du manuel d'exploitation.
    videos = VideoAsset.objects.filter(
        statut_traitement__in=[
            VideoAsset.StatutTraitement.EN_ATTENTE,
            VideoAsset.StatutTraitement.EN_COURS,
            VideoAsset.StatutTraitement.ERREUR,
        ]
    ).count()
    acces_echus = InscriptionModule.objects.filter(
        statut=InscriptionModule.StatutAcces.ACTIF, date_fin_acces__lt=aujourd_hui
    ).count()
    # Un cours affiché comme ouvert alors qu'il est plein renvoie l'étudiant sur
    # un refus : c'est au secrétariat de clore ou d'augmenter la capacité.
    complets = (
        CoursDeSession.objects.filter(
            inscriptions_ouvertes=True,
            statut=CoursDeSession.StatutCours.PROGRAMME,
            session__date_fin__gte=aujourd_hui,
        )
        .annotate(inscrits=Count("inscriptions"))
        .filter(inscrits__gte=F("capacite"))
        .count()
    )

    candidates = [
        Alerte("candidature(s) à instruire", candidatures, reverse("administration:candidatures"), urgent=True),
        Alerte(
            "demande(s) d'inscription à traiter",
            inscriptions,
            reverse("administration:enrollment_requests"),
            urgent=True,
        ),
        Alerte(
            "demande(s) d'accès à un module",
            acces,
            f"{reverse('administration:acces')}?statut={InscriptionModule.StatutAcces.DEMANDE}",
            urgent=True,
        ),
        Alerte("paiement(s) à vérifier", paiements, reverse("administration:payments")),
        Alerte("module(s) vidéo en relecture", relecture, reverse("administration:video_statistiques")),
        Alerte("vidéo(s) non prêtes", videos, reverse("administration:video_journal")),
        Alerte(
            "accès vidéo échus à régulariser",
            acces_echus,
            f"{reverse('administration:acces')}?statut={InscriptionModule.StatutAcces.ACTIF}",
        ),
        Alerte("cours complet(s) encore ouverts", complets, reverse("administration:course_offerings")),
    ]
    return [alerte for alerte in candidates if alerte.nombre]
