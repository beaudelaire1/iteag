from pathlib import Path

from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import StudentRoleRequiredMixin

from .models import DocumentAdministratif


class StudentDocumentListView(StudentRoleRequiredMixin, TemplateView):
    template_name = "documents/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profil = self.request.user.profil_etudiant
        context.update(
            {
                "profil": profil,
                "documents": self.request.user.documents_administratifs.all(),
                "document_types": DocumentAdministratif.TypeDocument.choices,
            }
        )
        return context


class GenerateStudentDocumentView(StudentRoleRequiredMixin, View):
    def get(self, request, document_type):
        allowed_types = {choice[0] for choice in DocumentAdministratif.TypeDocument.choices}
        if document_type not in allowed_types:
            raise Http404("Type de document inconnu.")

        try:
            from weasyprint import HTML
        except ImportError:
            messages.error(request, "WeasyPrint n'est pas disponible dans cet environnement.")
            return redirect("documents:list")

        profil = request.user.profil_etudiant
        credits = profil.credits_ects.select_related("cours", "session")[:12]
        paiements = profil.paiements.select_related("session")[:10]

        html = render_to_string(
            "documents/pdf/document.html",
            {
                "user": request.user,
                "profil": profil,
                "document_type": document_type,
                "document_label": dict(DocumentAdministratif.TypeDocument.choices)[document_type],
                "generated_at": timezone.now(),
                "credits": credits,
                "paiements": paiements,
            },
            request=request,
        )
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()

        filename = f"{document_type}-{slugify(request.user.get_full_name() or request.user.username)}-{timezone.now():%Y%m%d%H%M%S}.pdf"
        document = DocumentAdministratif(etudiant=request.user, type_document=document_type)
        document.fichier_pdf.save(filename, ContentFile(pdf_bytes), save=False)
        document.save()
        return FileResponse(document.fichier_pdf.open("rb"), as_attachment=True, filename=Path(filename).name)


class DownloadStudentDocumentView(StudentRoleRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(DocumentAdministratif, pk=pk, etudiant=request.user)
        if not document.fichier_pdf:
            raise Http404("Document indisponible.")
        return FileResponse(document.fichier_pdf.open("rb"), as_attachment=True, filename=Path(document.fichier_pdf.name).name)