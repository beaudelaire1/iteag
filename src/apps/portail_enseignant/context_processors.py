"""Pastille des propositions en attente, visible depuis tout l'espace enseignant.

Sans elle, une proposition n'existe que sur son propre écran : l'enseignant
devrait deviner qu'il faut aller y regarder. Le compteur est paresseux — un
appelable, résolu par le gabarit — pour qu'aucune page qui n'affiche pas la
barre ne paie la requête.
"""


def propositions_en_attente(request):
    utilisateur = getattr(request, "user", None)
    if utilisateur is None or not utilisateur.is_authenticated:
        return {}
    if not getattr(utilisateur, "is_enseignant", False):
        return {}

    def compteur():
        if not hasattr(request, "_propositions_en_attente"):
            from apps.academics.models import PropositionEnseignement

            professeur = getattr(utilisateur, "profil_professeur", None)
            request._propositions_en_attente = (
                0
                if professeur is None
                else PropositionEnseignement.objects.filter(
                    professeur=professeur,
                    statut=PropositionEnseignement.Statut.PROPOSEE,
                ).count()
            )
        return request._propositions_en_attente

    return {"propositions_en_attente": compteur}
