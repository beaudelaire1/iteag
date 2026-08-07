from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.core.models import Notification
from apps.core.services.emails import envoyer_notification_email
from apps.core.services.notifications import notifier_plusieurs
from apps.core.services.turnstile import MESSAGE_ECHEC, valider_requete
from apps.formations.models import Parcours

from .emails import envoyer_confirmation_depot_pieces, send_candidature_confirmation
from .forms import CandidatureForm
from .formulaires import DepotPieceForm, DepotPiecesGroupeForm
from .models import DemandePieces, DossierCandidature, PieceDemandee
from .services_pieces import synchroniser_statut_demande


def candidature_form(request):
    """Vue publique : formulaire de candidature (PUB-011)."""
    if request.method == "POST":
        form = CandidatureForm(request.POST, request.FILES)
        if form.is_valid():
            if valider_requete(request, action="candidature"):
                dossier = form.save()
                send_candidature_confirmation(dossier)
                notifier_plusieurs(
                    User.objects.filter(
                        is_active=True,
                        role__in=[User.Role.ADMIN, User.Role.SECRETARIAT],
                    ),
                    f"Nouvelle candidature — {dossier.nom_complet}",
                    type_notification=Notification.Type.CANDIDATURE,
                    message=(
                        f"{dossier.nom_complet} a déposé une candidature pour le parcours "
                        f"« {dossier.parcours_souhaite} ». Le dossier attend un premier examen."
                    ),
                    details=[
                        {"libelle": "Candidat", "valeur": dossier.nom_complet},
                        {"libelle": "Parcours demandé", "valeur": str(dossier.parcours_souhaite)},
                        {"libelle": "Courriel", "valeur": dossier.email},
                    ],
                    url_cible=reverse("administration:candidature_detail", kwargs={"pk": dossier.pk}),
                )
                messages.success(request, "Votre candidature a bien été enregistrée.")
                return redirect("admissions:candidature_confirmation", token=dossier.token_suivi)
            form.add_error(None, MESSAGE_ECHEC)
    else:
        form = CandidatureForm()
    return render(request, "admissions/candidature_form.html", {"form": form})


def candidature_confirmation(request, token):
    dossier = get_object_or_404(DossierCandidature, token_suivi=token)
    return render(request, "admissions/candidature_confirmation.html", {"dossier": dossier})


def candidature_suivi(request, token):
    """Suivi public : les pièces sont présentées et déposées par demande."""
    dossier = get_object_or_404(DossierCandidature, token_suivi=token)
    demandes = []
    for demande in dossier.demandes_pieces.prefetch_related("pieces").all():
        pieces = list(demande.pieces.all())
        a_transmettre = [
            piece for piece in pieces if piece.statut in (PieceDemandee.Statut.DEMANDEE, PieceDemandee.Statut.REFUSEE)
        ]
        demandes.append({"demande": demande, "pieces": pieces, "a_transmettre": a_transmettre})
    return render(
        request,
        "admissions/candidature_suivi.html",
        {
            "dossier": dossier,
            "demandes_pieces": demandes,
            "pieces_legacy": dossier.pieces_demandees.filter(demande__isnull=True),
            "formulaire_depot": DepotPieceForm(),
        },
    )


def _notifier_depot_groupe(dossier, pieces):
    noms = ", ".join(piece.libelle for piece in pieces)
    notifier_plusieurs(
        User.objects.filter(
            is_active=True,
            role__in=[User.Role.ADMIN, User.Role.SECRETARIAT],
        ),
        f"Documents déposés — {dossier.nom_complet}",
        type_notification=Notification.Type.CANDIDATURE,
        message=(
            f"{dossier.nom_complet} a transmis {len(pieces)} document(s) en une seule fois. "
            "L'ensemble de la demande attend une vérification."
        ),
        details=[
            {"libelle": "Candidat", "valeur": dossier.nom_complet},
            {"libelle": "Documents", "valeur": noms},
        ],
        url_cible=reverse("administration:candidature_detail", kwargs={"pk": dossier.pk}),
    )


@require_POST
def deposer_piece(request, token, piece_id):
    """Dépose un lot complet ; conserve une compatibilité pour les anciennes pièces."""
    dossier = get_object_or_404(DossierCandidature, token_suivi=token)
    demande = dossier.demandes_pieces.filter(pk=piece_id).prefetch_related("pieces").first()

    if demande is not None:
        if demande.statut not in (DemandePieces.Statut.A_FOURNIR, DemandePieces.Statut.A_CORRIGER):
            messages.info(request, "Cette demande a déjà été transmise ou validée.")
            return redirect("admissions:candidature_suivi", token=token)

        formulaire = DepotPiecesGroupeForm(request.POST, request.FILES, demande=demande)
        if formulaire.is_valid():
            fichiers = formulaire.fichiers()
            with transaction.atomic():
                demande_verrouillee = DemandePieces.objects.select_for_update().get(
                    pk=demande.pk,
                    dossier=dossier,
                )
                pieces_deposees = []
                for piece, fichier in fichiers:
                    piece.deposer(fichier)
                    pieces_deposees.append(piece)
                synchroniser_statut_demande(demande_verrouillee)

            envoyer_confirmation_depot_pieces(demande, pieces_deposees)
            _notifier_depot_groupe(dossier, pieces_deposees)
            messages.success(
                request,
                f"{len(pieces_deposees)} document(s) transmis en une seule fois. "
                "Le secrétariat vérifiera l'ensemble de la demande.",
            )
        else:
            for erreurs in formulaire.errors.values():
                messages.error(request, erreurs[0])
        return redirect("admissions:candidature_suivi", token=token)

    piece = get_object_or_404(dossier.pieces_demandees.filter(demande__isnull=True), pk=piece_id)
    formulaire = DepotPieceForm(request.POST, request.FILES, instance=piece)
    if formulaire.is_valid():
        piece.deposer(formulaire.cleaned_data["fichier"])
        suivi_url = request.build_absolute_uri(
            reverse("admissions:candidature_suivi", kwargs={"token": dossier.token_suivi})
        )
        envoyer_notification_email(
            sujet=f"Document reçu — {piece.libelle}",
            titre="Votre document a bien été reçu",
            message=(
                f"Bonjour {dossier.prenom},\n\n"
                f"Le document « {piece.libelle} » a bien été transmis. "
                "Le secrétariat va maintenant le vérifier."
            ),
            lien=suivi_url,
            libelle_lien="Suivre mon dossier",
            destinataires=[dossier.email],
        )
        _notifier_depot_groupe(dossier, [piece])
        messages.success(request, f"« {piece.libelle} » a bien été transmis.")
    else:
        for erreurs in formulaire.errors.values():
            messages.error(request, erreurs[0])
    return redirect("admissions:candidature_suivi", token=token)


def parcours_preview(request):
    parcours_id = request.GET.get("parcours")
    parcours = None
    if parcours_id:
        parcours = get_object_or_404(Parcours.objects.filter(actif=True), pk=parcours_id)
    return render(request, "admissions/partials/parcours_preview.html", {"parcours": parcours})
