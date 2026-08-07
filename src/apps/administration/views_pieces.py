"""Demandes groupées de pièces justificatives à un candidat."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import FormView

from apps.admissions.emails import (
    envoyer_decision_pieces,
    envoyer_demande_de_pieces,
    envoyer_refus_de_piece,
)
from apps.admissions.formulaires import PIECES_COURANTES, DemandePiecesForm
from apps.admissions.models import DemandePieces, DossierCandidature, PieceDemandee
from apps.admissions.services_pieces import synchroniser_statut_demande
from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser

PRECISIONS_PAR_DEFAUT = dict(PIECES_COURANTES)


class DemanderPiecesView(StaffRoleRequiredMixin, FormView):
    """Crée une seule demande contenant toutes les pièces sélectionnées."""

    template_name = "administration/demander_pieces.html"
    form_class = DemandePiecesForm

    def dispatch(self, request, *args, **kwargs):
        self.dossier = get_object_or_404(DossierCandidature, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["dossier"] = self.dossier
        return kwargs

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "dossier": self.dossier,
                "nav": "candidatures",
                "deja_demandees": self.dossier.demandes_pieces.prefetch_related("pieces"),
            }
        )
        return contexte

    def form_valid(self, form):
        message_commun = form.cleaned_data.get("precisions", "").strip()
        date_limite = form.cleaned_data.get("date_limite")
        existantes = {
            libelle.casefold()
            for libelle in self.dossier.pieces_demandees.values_list("libelle", flat=True)
        }
        libelles = [libelle for libelle in form.libelles() if libelle.casefold() not in existantes]

        if not libelles:
            messages.info(self.request, "Ces pièces avaient déjà été réclamées.")
            return redirect(self.get_success_url())

        with transaction.atomic():
            demande = DemandePieces.objects.create(
                dossier=self.dossier,
                message=message_commun,
                date_limite=date_limite,
                demandee_par=self.request.user,
            )
            pieces = [
                PieceDemandee.objects.create(
                    dossier=self.dossier,
                    demande=demande,
                    libelle=libelle,
                    precisions=PRECISIONS_PAR_DEFAUT.get(libelle, ""),
                    date_limite=date_limite,
                    demandee_par=self.request.user,
                )
                for libelle in libelles
            ]

        envoyer_demande_de_pieces(demande)
        journaliser(
            JournalAudit.Action.MODIFICATION,
            utilisateur=self.request.user,
            request=self.request,
            objet=self.dossier,
            objet_libelle=f"Demande de pièces à {self.dossier.nom_complet}",
            pieces=", ".join(piece.libelle for piece in pieces),
            demande_id=demande.pk,
        )
        messages.success(
            self.request,
            f"Demande envoyée : {len(pieces)} document(s), un seul courriel et un seul dépôt attendu.",
        )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("administration:candidature_detail", kwargs={"pk": self.dossier.pk})


class PieceDecisionView(StaffRoleRequiredMixin, View):
    """Traite en une seule opération toutes les pièces déposées d'une demande."""

    http_method_names = ["post"]

    def post(self, request, pk):
        demande = (
            DemandePieces.objects.select_related("dossier")
            .prefetch_related("pieces")
            .filter(pk=pk)
            .first()
        )
        if demande is not None:
            return self._traiter_demande(request, demande)

        piece = get_object_or_404(PieceDemandee.objects.select_related("dossier"), pk=pk, demande__isnull=True)
        return self._traiter_piece_legacy(request, piece)

    def _traiter_demande(self, request, demande):
        dossier_id = demande.dossier_id
        pieces = [piece for piece in demande.pieces.all() if piece.statut == PieceDemandee.Statut.DEPOSEE]
        if not pieces:
            messages.info(request, "Aucun document de cette demande n'attend de décision.")
            return redirect("administration:candidature_detail", pk=dossier_id)

        decisions = []
        erreurs = []
        for piece in pieces:
            action = request.POST.get(f"decision_{piece.pk}")
            motif = request.POST.get(f"motif_{piece.pk}", "").strip()
            if action not in {"valider", "refuser"}:
                erreurs.append(f"Choisissez une décision pour « {piece.libelle} ».")
            elif action == "refuser" and not motif:
                erreurs.append(f"Indiquez le motif du refus pour « {piece.libelle} ».")
            decisions.append((piece, action, motif))

        if erreurs:
            for erreur in erreurs:
                messages.error(request, erreur)
            return redirect("administration:candidature_detail", pk=dossier_id)

        validees = []
        refusees = []
        with transaction.atomic():
            demande_verrouillee = DemandePieces.objects.select_for_update().get(pk=demande.pk)
            for piece, action, motif in decisions:
                if action == "valider":
                    piece.valider()
                    validees.append(piece)
                else:
                    piece.refuser(motif)
                    refusees.append(piece)
            synchroniser_statut_demande(demande_verrouillee)

        envoyer_decision_pieces(demande, validees, refusees)
        journaliser(
            JournalAudit.Action.MODIFICATION,
            utilisateur=request.user,
            request=request,
            objet=demande.dossier,
            objet_libelle=f"Décision groupée sur les pièces de {demande.dossier.nom_complet}",
            validees=[piece.libelle for piece in validees],
            refusees=[{"piece": piece.libelle, "motif": piece.motif_refus} for piece in refusees],
        )
        if refusees:
            messages.success(
                request,
                f"Décision enregistrée en une fois : {len(validees)} validée(s), "
                f"{len(refusees)} à refournir. Un seul courriel a été envoyé.",
            )
        else:
            messages.success(request, f"Les {len(validees)} document(s) de la demande sont validés.")
        return redirect("administration:candidature_detail", pk=dossier_id)

    def _traiter_piece_legacy(self, request, piece):
        dossier_id = piece.dossier_id
        action = request.POST.get("action")
        if action == "valider":
            piece.valider()
            messages.success(request, f"« {piece.libelle} » validée.")
        elif action == "refuser":
            try:
                piece.refuser(request.POST.get("motif", ""))
            except ValidationError as erreur:
                messages.error(request, erreur.messages[0])
            else:
                envoyer_refus_de_piece(piece)
                messages.success(request, f"« {piece.libelle} » refusée.")
        elif action == "retirer":
            libelle = piece.libelle
            piece.delete()
            messages.success(request, f"« {libelle} » retirée.")
        else:
            messages.error(request, "Action inconnue.")
        return redirect("administration:candidature_detail", pk=dossier_id)


class PieceTelechargementView(StaffRoleRequiredMixin, View):
    def get(self, request, pk):
        piece = get_object_or_404(PieceDemandee, pk=pk)
        if not piece.fichier:
            raise Http404
        return FileResponse(piece.fichier.open("rb"), as_attachment=True, filename=piece.fichier.name.split("/")[-1])
