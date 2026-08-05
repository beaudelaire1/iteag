"""Rédaction des documents officiels de l'institut.

Le pendant du module voisin : là où « views.py » **dérive** un document du
dossier d'un étudiant, ces écrans laissent quelqu'un en **composer** un.

Le PDF est un artefact, pas le document. Le document, ce sont les champs en
base ; le PDF s'en déduit et se regénère à volonté. La distinction compte le
jour où le moteur de rendu manque : la finalisation reste possible, elle
n'attend pas WeasyPrint pour être un acte.
"""

from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.core.services.pdf import MoteurPDFIndisponible, contexte_marque, rendre_pdf
from apps.documents.formulaires import DocumentRedigeForm
from apps.documents.models import DocumentRedige

GABARIT_PDF = "documents/pdf/document_redige.html"


def _fabriquer_pdf(document: DocumentRedige, request=None) -> bytes:
    return rendre_pdf(
        GABARIT_PDF,
        contexte_marque(profil_polices="document_administratif", document=document, edite_le=timezone.now()),
        request=request,
    )


def _archiver_le_pdf(document: DocumentRedige, request=None) -> bool:
    """Fabrique le PDF et l'attache. Retourne False si le moteur manque.

    L'échec n'est pas silencieux mais il n'est pas fatal : le document reste
    finalisé, et le PDF se refabrique depuis la liste quand le moteur revient.
    """
    try:
        contenu = _fabriquer_pdf(document, request=request)
    except MoteurPDFIndisponible:
        return False

    nom = f"{slugify(document.reference or document.titre)}-{timezone.now():%Y%m%d%H%M%S}.pdf"
    document.fichier_pdf.save(nom, ContentFile(contenu), save=True)
    return True


class DocumentsRedigesView(StaffRoleRequiredMixin, ListView):
    template_name = "documents/redaction/liste.html"
    context_object_name = "documents"
    paginate_by = 25

    def get_queryset(self):
        requete = DocumentRedige.objects.select_related("redige_par")
        genre = self.request.GET.get("genre", "")
        if genre in DocumentRedige.Genre.values:
            requete = requete.filter(genre=genre)
        return requete

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["nav"] = "documents_rediges"
        contexte["brouillons"] = [d for d in contexte["documents"] if d.est_modifiable]
        contexte["finalises"] = [d for d in contexte["documents"] if d.est_finalise]
        contexte["genres"] = DocumentRedige.Genre.choices
        contexte["genre_actif"] = self.request.GET.get("genre", "")
        return contexte


class DocumentRedigeEditionView(StaffRoleRequiredMixin, TemplateView):
    """Création et correction, sur le même écran.

    Un document finalisé n'est pas modifiable : il faut le rouvrir d'abord. Le
    changer en place ferait dire autre chose à une référence déjà inscrite au
    registre, et peut-être déjà citée dans un courrier reçu.
    """

    template_name = "documents/redaction/formulaire.html"

    def _document(self):
        if "pk" not in self.kwargs:
            return None
        return get_object_or_404(DocumentRedige, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        document = self._document()
        return {
            **super().get_context_data(**kwargs),
            "nav": "documents_rediges",
            "document": document,
            "form": kwargs.get("form") or DocumentRedigeForm(instance=document),
            "verrouille": document is not None and not document.est_modifiable,
        }

    def post(self, request, *args, **kwargs):
        document = self._document()
        if document is not None and not document.est_modifiable:
            messages.error(request, "Rouvrez le document avant de le modifier.")
            return redirect("redaction:documents")

        formulaire = DocumentRedigeForm(request.POST, instance=document)
        if not formulaire.is_valid():
            return self.render_to_response(self.get_context_data(form=formulaire))

        creation = document is None
        document = formulaire.save(commit=False)
        if document.redige_par_id is None:
            document.redige_par = request.user
        document.save()

        journaliser(
            JournalAudit.Action.CREATION if creation else JournalAudit.Action.MODIFICATION,
            utilisateur=request.user,
            request=request,
            objet=document,
            objet_libelle=f"Document « {document.titre} »",
        )
        messages.success(
            request,
            "Document enregistré. Il reste en brouillon tant que vous ne l'avez pas finalisé.",
        )
        return redirect("redaction:document_edition", pk=document.pk)


class DocumentRedigeDecisionView(StaffRoleRequiredMixin, View):
    """Finaliser, rouvrir, supprimer."""

    http_method_names = ["post"]

    def post(self, request, pk):
        document = get_object_or_404(DocumentRedige, pk=pk)
        action = request.POST.get("action")
        titre = document.titre

        try:
            if action == "finaliser":
                document.finaliser(par=request.user)
                if _archiver_le_pdf(document, request=request):
                    avis = f"« {document.reference} » est finalisé et son PDF est archivé."
                else:
                    avis = (
                        f"« {document.reference} » est finalisé. Le PDF n'a pas pu être fabriqué "
                        "— WeasyPrint est absent de cet environnement — et se regénérera depuis la liste."
                    )
                trace = JournalAudit.Action.CHANGEMENT_STATUT
            elif action == "rouvrir":
                document.revenir_en_brouillon()
                avis = f"« {titre} » est revenu en brouillon. Son PDF a été retiré, sa référence conservée."
                trace = JournalAudit.Action.CHANGEMENT_STATUT
            elif action == "supprimer":
                # Un document finalisé a un numéro au registre : le détruire
                # laisserait un trou que personne ne saurait expliquer.
                if document.est_finalise:
                    raise ValidationError(
                        "Un document finalisé ne se supprime pas : rouvrez-le d'abord si c'est une erreur."
                    )
                trace = JournalAudit.Action.SUPPRESSION
                avis = f"« {titre} » a été supprimé."
            else:
                raise ValidationError("Action inconnue.")
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
            return redirect("redaction:documents")

        if action == "supprimer":
            identifiant = str(document.pk)
            document.delete()
            journaliser(
                trace,
                utilisateur=request.user,
                request=request,
                objet_type="DocumentRedige",
                objet_id=identifiant,
                objet_libelle=f"Document « {titre} »",
            )
        else:
            journaliser(
                trace,
                utilisateur=request.user,
                request=request,
                objet=document,
                objet_libelle=f"Document « {titre} » → {document.get_statut_display()}",
            )

        messages.success(request, avis)
        return redirect("redaction:documents")


class DocumentRedigePdfView(StaffRoleRequiredMixin, View):
    """Sert le PDF archivé, ou le refabrique s'il manque.

    Un brouillon a droit à son aperçu, mais celui-ci n'est pas archivé : ce
    serait faire croire à une pièce arrêtée alors que le texte peut encore
    changer. Le filigrane du gabarit le dit à l'impression.
    """

    def get(self, request, pk):
        document = get_object_or_404(DocumentRedige, pk=pk)

        if document.est_finalise and document.fichier_pdf:
            return FileResponse(
                document.fichier_pdf.open("rb"),
                as_attachment=True,
                filename=Path(document.fichier_pdf.name).name,
            )

        try:
            contenu = _fabriquer_pdf(document, request=request)
        except MoteurPDFIndisponible:
            messages.error(request, "WeasyPrint n'est pas disponible dans cet environnement.")
            return redirect("redaction:documents")

        if document.est_finalise:
            # Finalisé sans PDF : le moteur manquait au moment de l'acte. On
            # rattrape l'archivage maintenant plutôt qu'à chaque téléchargement.
            _archiver_le_pdf(document, request=request)
            if document.fichier_pdf:
                return FileResponse(
                    document.fichier_pdf.open("rb"),
                    as_attachment=True,
                    filename=Path(document.fichier_pdf.name).name,
                )

        journaliser(
            JournalAudit.Action.CONSULTATION_SENSIBLE,
            utilisateur=request.user,
            request=request,
            objet=document,
            objet_libelle=f"Aperçu du document « {document.titre} »",
        )
        nom = f"apercu-{slugify(document.titre) or 'document'}.pdf"
        return FileResponse(ContentFile(contenu), as_attachment=True, filename=nom)
