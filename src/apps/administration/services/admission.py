"""
Orchestration de l'acceptation d'une candidature.

Ce service traverse plusieurs domaines — admissions, comptes, vie académique,
formation vidéo. Il vit donc dans le portail administratif, seule couche
autorisée à les connaître tous (voir docs/architecture/uml.md §2.2).
"""

from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.admissions.models import DossierCandidature
from apps.admissions.services import transition_dossier
from apps.core.models import Notification
from apps.core.services.audit import journaliser
from apps.core.services.emails import envoyer_email
from apps.core.services.notifications import notifier
from apps.elearning.services.octroi import octroyer_modules_du_parcours


def numero_etudiant_suivant(annee: int) -> str:
    prefixe = f"ETU-{annee}-"
    dernier = (
        ProfilEtudiant.objects.filter(numero_etudiant__startswith=prefixe)
        .order_by("-numero_etudiant")
        .values_list("numero_etudiant", flat=True)
        .first()
    )
    rang = int(dernier.rsplit("-", 1)[1]) + 1 if dernier else 1
    return f"{prefixe}{rang:03d}"


@transaction.atomic
def accepter_dossier(
    dossier: DossierCandidature,
    *,
    promotion: Promotion,
    par=None,
    request=None,
) -> ProfilEtudiant:
    """Accepte une candidature et ouvre tout ce qui en découle.

    Le compte est créé sans mot de passe utilisable : le candidat le définit
    lui-même par le lien envoyé, ce qui évite qu'un mot de passe transite.
    """
    from django.utils import timezone

    if dossier.utilisateur_cree is not None:
        return dossier.utilisateur_cree.profil_etudiant

    utilisateur = User.objects.create(
        username=_nom_utilisateur_libre(dossier),
        email=dossier.email,
        first_name=dossier.prenom,
        last_name=dossier.nom,
        phone=dossier.telephone,
        role=User.Role.ETUDIANT,
    )
    utilisateur.set_unusable_password()
    utilisateur.save(update_fields=["password"])

    profil = ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=dossier.parcours_souhaite,
        promotion=promotion,
        numero_etudiant=numero_etudiant_suivant(timezone.now().year),
        statut_inscription=ProfilEtudiant.StatutInscription.PRE_INSCRIT,
        eglise_fondatrice=dossier.eglise_fondatrice,
    )

    # La transition passe par la machine à états d'admissions : l'acceptation
    # n'est pas un cas particulier qui la contournerait. Une transition
    # interdite lève ici, et la transaction annule la création du compte.
    transition_dossier(
        dossier=dossier,
        new_status=DossierCandidature.Statut.ACCEPTE,
        changed_by=par,
        comment="Acceptation : compte étudiant créé et accès ouverts.",
    )
    dossier.refresh_from_db()
    dossier.utilisateur_cree = utilisateur
    dossier.save(update_fields=["utilisateur_cree", "date_derniere_maj"])

    # Octroi automatique des modules obligatoires du parcours : sans cela, le
    # secrétariat devrait ouvrir chaque accès à la main.
    inscriptions = octroyer_modules_du_parcours(profil, octroye_par=par)

    journaliser(
        "changement_statut",
        utilisateur=par,
        request=request,
        objet=dossier,
        objet_libelle=f"Candidature acceptée — {dossier.nom_complet}",
        modules_ouverts=len(inscriptions),
    )

    notifier(
        utilisateur,
        "Bienvenue à l'ITEAG",
        type_notification=Notification.Type.CANDIDATURE,
        message="Votre candidature est acceptée. Votre espace étudiant est ouvert.",
        envoyer_par_email=False,
    )
    _envoyer_bienvenue(utilisateur, dossier, request)

    return profil


def _nom_utilisateur_libre(dossier: DossierCandidature) -> str:
    base = f"{dossier.prenom}.{dossier.nom}".lower().replace(" ", "-")[:140]
    candidat, suffixe = base, 1
    while User.objects.filter(username=candidat).exists():
        suffixe += 1
        candidat = f"{base}{suffixe}"
    return candidat


def _envoyer_bienvenue(utilisateur, dossier, request) -> None:
    """Courriel de bienvenue portant le lien de définition du mot de passe."""
    identifiant = urlsafe_base64_encode(force_bytes(utilisateur.pk))
    jeton = default_token_generator.make_token(utilisateur)
    chemin = f"/mot-de-passe/confirmer/{identifiant}/{jeton}/"
    lien = request.build_absolute_uri(chemin) if request is not None else chemin

    envoyer_email(
        sujet="Bienvenue à l'ITEAG — activez votre compte",
        gabarit="administration/emails/bienvenue_etudiant.html",
        contexte={
            "prenom": dossier.prenom,
            "parcours": dossier.parcours_souhaite.nom,
            "lien_activation": lien,
        },
        destinataires=[utilisateur.email],
    )
