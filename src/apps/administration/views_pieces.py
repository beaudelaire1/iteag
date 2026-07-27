"""
Réclamation de pièces justificatives à un candidat.

Le formulaire public ne recueille que trois pièces génériques. Une fois le
dossier tranché, il en faut d'autres — variables selon le parcours et le
profil — et jusqu'ici la seule voie était d'écrire une liste en prose dans
« éléments manquants », puis d'attendre un courriel. Rien n'était suivi : ni ce
qui avait été demandé, ni ce qui était revenu, ni ce qui manquait encore.

Ces vues font de chaque pièce un objet avec un état. Le candidat dépose depuis
la page de suivi qu'il possède déjà ; le secrétariat valide ou refuse, et un
refus dit pourquoi.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import FormView

from apps.admissions.emails import envoyer_demande_de_pieces
from apps.admissions.formulaires import PIECES_COURANTES, DemandePiecesForm
from apps.admissions.models import DossierCandidature, PieceDemandee
from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser

PRECISIONS_PAR_DEFAUT = dict(PIECES_COURANTES)


class DemanderPiecesView(StaffRoleRequiredMixin, FormView):
    """Réclame une ou plusieurs pièces, et prévient le candidat une seule fois."""

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
                "deja_demandees": self.dossier.pieces_demandees.all(),
            }
        )
        return contexte

    def form_valid(self, form):
        precisions = form.cleaned_data.get("precisions", "")
        date_limite = form.cleaned_data.get("date_limite")

        creees = []
        for libelle in form.libelles():
            # La précision propre à la pièce sert de repli : elle explique le
            # format attendu, ce qu'une consigne générale ne dit pas.
            detail = precisions or PRECISIONS_PAR_DEFAUT.get(libelle, "")
            piece, cree = PieceDemandee.objects.get_or_create(
                dossier=self.dossier,
                libelle=libelle,
                defaults={
                    "precisions": detail,
                    "date_limite": date_limite,
                    "demandee_par": self.request.user,
                },
            )
            if cree:
                creees.append(piece)

        if not creees:
            messages.info(self.request, "Ces pièces avaient déjà été réclamées.")
            return redirect(self.get_success_url())

        # Un seul courriel pour l'ensemble : en envoyer un par pièce ferait
        # passer le secrétariat pour un robot, et noierait la demande.
        envoyer_demande_de_pieces(self.dossier, creees)
        journaliser(
            JournalAudit.Action.MODIFICATION,
            utilisateur=self.request.user,
            request=self.request,
            objet=self.dossier,
            objet_libelle=f"Pièces réclamées à {self.dossier.prenom} {self.dossier.nom}",
            pieces=", ".join(piece.libelle for piece in creees),
        )
        messages.success(
            self.request,
            f"{len(creees)} pièce(s) réclamée(s). {self.dossier.prenom} en est informé(e) par courriel.",
        )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("administration:candidature_detail", kwargs={"pk": self.dossier.pk})


class PieceDecisionView(StaffRoleRequiredMixin, View):
    """Valide ou refuse une pièce déposée."""

    http_method_names = ["post"]

    def post(self, request, pk):
        piece = get_object_or_404(PieceDemandee.objects.select_related("dossier"), pk=pk)
        action = request.POST.get("action")
        # Retenu avant toute suppression : après « delete », l'objet n'a plus de
        # clé et la redirection n'aurait plus où aller.
        dossier_id = piece.dossier_id

        if action == "valider":
            piece.valider()
            messages.success(request, f"« {piece.libelle} » validée.")
        elif action == "refuser":
            try:
                piece.refuser(request.POST.get("motif", ""))
            except ValidationError as erreur:
                messages.error(request, erreur.messages[0])
            else:
                from apps.admissions.emails import envoyer_refus_de_piece

                envoyer_refus_de_piece(piece)
                messages.success(request, f"« {piece.libelle} » refusée, le candidat est prévenu.")
        elif action == "retirer":
            libelle = piece.libelle
            piece.delete()
            messages.success(request, f"« {libelle} » retirée de la liste des pièces à fournir.")
        else:
            messages.error(request, "Action inconnue.")

        return redirect("administration:candidature_detail", pk=dossier_id)


class PieceTelechargementView(StaffRoleRequiredMixin, View):
    """Sert le fichier déposé par le candidat."""

    def get(self, request, pk):
        piece = get_object_or_404(PieceDemandee, pk=pk)
        if not piece.fichier:
            raise Http404
        return FileResponse(piece.fichier.open("rb"), as_attachment=True, filename=piece.fichier.name.split("/")[-1])
