from pathlib import Path

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.views.generic import TemplateView

from apps.academics.models import Paiement, ProfilEtudiant
from apps.core.mixins import StudentRoleRequiredMixin

from .models import DocumentAdministratif


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
        context.update(
            {
                "profil": profil,
                "documents": self.request.user.documents_administratifs.all(),
                "document_options": _document_options(profil),
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

        try:
            from weasyprint import HTML
        except ImportError:
            messages.error(request, "WeasyPrint n'est pas disponible dans cet environnement.")
            return redirect("documents:list")

        profil = request.user.profil_etudiant
        option = next((item for item in _document_options(profil) if item["value"] == document_type), None)
        if option is None or not option["available"]:
            messages.error(request, option["reason"] if option else "Ce document n'est pas disponible.")
            return redirect("documents:list")

        evaluations = profil.evaluations.filter(statut="publie").select_related(
            "cours_session__cours",
            "cours_session__session",
        )
        paiements = profil.paiements.filter(statut=Paiement.StatutPaiement.CONFIRME).select_related("session")
        # Le relevé est porté par les crédits, pas par les évaluations : c'est
        # le dossier académique qui fait foi, et lui seul contient les acquis
        # hors cours — stage validé, VAE accordée, équivalences FLTE. Totaliser
        # les crédits en ne listant que les évaluations ferait diverger le
        # total de ses lignes.
        credits = profil.credits_ects.select_related("cours", "session", "stage", "vae").order_by("date_validation")

        from apps.core.services.pdf import contexte_marque

        html = render_to_string(
            "documents/pdf/document.html",
            contexte_marque(
                user=request.user,
                profil=profil,
                document_type=document_type,
                document_label=dict(DocumentAdministratif.TypeDocument.choices)[document_type],
                generated_at=timezone.now(),
                evaluations=evaluations,
                paiements=paiements,
                credits=credits,
            ),
            request=request,
        )
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()

        identite = slugify(request.user.get_full_name() or request.user.username)
        filename = f"{document_type}-{identite}-{timezone.now():%Y%m%d%H%M%S}.pdf"
        document = DocumentAdministratif(etudiant=request.user, type_document=document_type)
        document.fichier_pdf.save(filename, ContentFile(pdf_bytes), save=False)
        document.save()
        return FileResponse(document.fichier_pdf.open("rb"), as_attachment=True, filename=Path(filename).name)


class DownloadStudentDocumentView(StudentRoleRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(DocumentAdministratif, pk=pk, etudiant=request.user)
        if not document.fichier_pdf:
            raise Http404("Document indisponible.")
        return FileResponse(
            document.fichier_pdf.open("rb"), as_attachment=True, filename=Path(document.fichier_pdf.name).name
        )
