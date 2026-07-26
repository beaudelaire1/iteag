"""
Compteurs d'attente de la navigation du personnel.

Ce processeur vit dans « administration » et non dans « core » : il interroge
trois domaines à la fois, et « core » ne doit dépendre d'aucun (le test
d'architecture le vérifie). « administration » est un agrégateur déclaré,
c'est son rôle.
"""


def taches_en_attente(request):
    """Ce qui appelle une décision, visible depuis n'importe quel écran.

    Chaque compteur est paresseux : un gabarit qui n'affiche pas la pastille ne
    déclenche aucune requête, et les pages publiques n'en paient aucune.
    """
    utilisateur = getattr(request, "user", None)
    if utilisateur is None or not utilisateur.is_authenticated:
        return {}
    if not (getattr(utilisateur, "is_admin", False) or getattr(utilisateur, "is_secretariat", False)):
        return {}

    def candidatures():
        from apps.admissions.models import DossierCandidature

        return DossierCandidature.objects.filter(
            statut__in=[
                DossierCandidature.Statut.SOUMIS,
                DossierCandidature.Statut.EN_EXAMEN,
                DossierCandidature.Statut.INCOMPLET,
            ]
        ).count()

    def inscriptions():
        from apps.academics.models import DemandeInscriptionCours

        return DemandeInscriptionCours.objects.filter(
            statut__in=[
                DemandeInscriptionCours.Statut.SOUMISE,
                DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
            ]
        ).count()

    def acces_video():
        from apps.elearning.models import InscriptionModule

        return InscriptionModule.objects.filter(statut=InscriptionModule.StatutAcces.DEMANDE).count()

    def paiements():
        from apps.academics.models import Paiement

        return Paiement.objects.filter(statut=Paiement.StatutPaiement.EN_ATTENTE).count()

    return {
        "candidatures_a_traiter": candidatures,
        "demandes_inscription_a_traiter": inscriptions,
        "demandes_acces_video": acces_video,
        "paiements_en_attente": paiements,
    }
