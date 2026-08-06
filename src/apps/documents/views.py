from pathlib import Path

from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from apps.academics.models import Paiement, ProfilEtudiant
from apps.core.mixins import StudentRoleRequiredMixin

from .models import DocumentAdministratif
from .tasks import planifier_document_administratif


def _document_options(profil):
    enrolled = profil.statut_inscription in {
        ProfilEtudiant.StatutInscription.INSCRIT,
        ProfilEtudiant.StatutInscription.ACTIF,
    }
    has_published_grades = profil.evaluations.filter(statut="publie").exists()
    has_confirmed_payment = profil.paiements.filter(statut=Paiement.StatutPaiement.CONFIRME).exists()
    eligibility = {
        DocumentAdministratif.TypeDocument.ATTESTATION: (
            enrolled,
            "Disponible après validation de votre inscription.",
        ),
        DocumentAdministratif.TypeDocument.CERTIFICAT: (
            enrolled,
            "Disponible pour les étudiants inscrits ou actifs.",
        ),
        DocumentAdministratif.TypeDocument.RELEVE_NOTES: (
            has_published_grades,
            "Disponible dès qu'au moins une note est publiée.",
        ),
        DocumentAdministratif.TypeDocument.RECU: (
            has_confirmed_payment,
            "Disponible après confirmation d'un paiement.",
        ),
    }
    return [
        {
            "value": value,
            "label": label,
            "available": eligibility[value][0],
            "reason": eligibility[value][1],
        }
        for value, label in DocumentAdministratif.TypeDocument.choices
    ]


class StudentDocumentListView(StudentRoleRequiredMixin, TemplateView):
    template_name = "documents/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        # Les notes se lisent ici, avant de décider d'éditer le relevé : il
        # fallait jusqu'ici générer un PDF pour savoir ce qu'il contiendrait,
        # ou changer d'écran. Seules les notes publiées paraissent — une note
        # posée mais non publiée n'est pas un résultat arrêté.
        notes = (
            profil.evaluations.filter(statut="publie", note__isnull=False)
            .select_related("cours_session__cours", "cours_session__session")
            .order_by("-date_notation", "-created_at")
        )
        context.update(
            {
                "profil": profil,
                "documents": self.request.user.documents_administratifs.all(),
                "document_options": _document_options(profil),
                "notes_publiees": notes,
                "total_ects_acquis": profil.total_ects_acquis,
            }
        )
        return context


class GenerateStudentDocumentView(StudentRoleRequiredMixin, View):
    def get(self, request, document_type):
        allowed_types = {choice[0] for choice in DocumentAdministratif.TypeDocument.choices}
        if document_type not in allowed_types:
            raise Http404("Type de document inconnu.")
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, document_type):
        allowed_types = {choice[0] for choice in DocumentAdministratif.TypeDocument.choices}
        if document_type not in allowed_types:
            raise Http404("Type de document inconnu.")

        profil = request.user.profil_etudiant
        option = next((item for item in _document_options(profil) if item["value"] == document_type), None)
        if option is None or not option["available"]:
            messages.error(request, option["reason"] if option else "Ce document n'est pas disponible.")
            return redirect("documents:list")

        document = DocumentAdministratif.objects.create(etudiant=request.user, type_document=document_type)
        if planifier_document_administratif(document):
            messages.success(
                request,
                "La génération a démarré en arrière-plan. Le téléchargement apparaîtra automatiquement ici.",
            )
        else:
            messages.error(request, "Le service de génération est momentanément indisponible. Réessayez plus tard.")
        return redirect("documents:list")


class StudentDocumentStatusView(StudentRoleRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(DocumentAdministratif, pk=pk, etudiant=request.user)
        return render(request, "documents/partials/document_ligne.html", {"doc": document})


class DownloadStudentDocumentView(StudentRoleRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(DocumentAdministratif, pk=pk, etudiant=request.user)
        if not document.fichier_pdf:
            raise Http404("Document indisponible.")
        return FileResponse(
            document.fichier_pdf.open("rb"), as_attachment=True, filename=Path(document.fichier_pdf.name).name
        )


class DeleteStudentDocumentView(StudentRoleRequiredMixin, View):
    """Permet à un étudiant de supprimer un document administratif généré de sa liste."""

    http_method_names = ["post"]

    def post(self, request, pk):
        document = get_object_or_404(DocumentAdministratif, pk=pk, etudiant=request.user)
        label = document.get_type_document_display()
        if document.fichier_pdf:
            document.fichier_pdf.delete(save=False)
        document.delete()

        if request.headers.get("HX-Request"):
            return HttpResponse("")

        messages.success(request, f"Le document « {label} » a été supprimé.")
        return redirect("documents:list")
