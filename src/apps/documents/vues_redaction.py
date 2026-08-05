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
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services.audit import journaliser
from apps.documents.fiches import FICHES, fiche
from apps.documents.formulaires import DocumentRedigeForm
from apps.documents.models import DocumentRedige
from apps.documents.tasks import planifier_document_redige


def _saisie_avec_corps(donnees):
    """Garantit que le corps est déclaré, fût-ce comme vide.

    Un StreamBlock lit « corps-count » sans filet : la clé absente lève une
    « MultiValueDictKeyError » avant toute validation, et la vue rend un 500 là
    où elle devrait afficher un formulaire. Or la clé manque dès que le widget
    ne s'est pas amorcé — script absent, page envoyée avant la fin du
    chargement, requête forgée.

    Un envoi sans corps signifie « rien à écrire », ce qu'un brouillon a le
    droit d'être. C'est « finaliser() » qui exige un corps, au moment où le
    document devient un acte.
    """
    if "corps-count" in donnees:
        return donnees
    complete = donnees.copy()
    complete["corps-count"] = "0"
    return complete


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

    **Deux formulaires, pas un.** Le premier porte ce que tout document a — un
    objet, une date, un corps, une signature. Le second est la fiche du genre :
    la date, l'heure et le lieu d'une convocation, les participants d'un compte
    rendu. Les fondre en un seul afficherait tous les champs de tous les genres,
    et l'on demanderait ses participants à un courrier.
    """

    template_name = "documents/redaction/formulaire.html"

    def _document(self):
        if "pk" not in self.kwargs:
            return None
        return get_object_or_404(DocumentRedige, pk=self.kwargs["pk"])

    def _genre(self, document):
        """Le genre vient du document, ou du choix fait à la création.

        Il ne se change plus ensuite : la fiche déjà remplie n'aurait plus de
        sens sous un autre genre.
        """
        if document is not None:
            return document.genre
        demande = self.request.POST.get("genre") or self.request.GET.get("genre") or ""
        return demande if demande in FICHES else ""

    def get(self, request, *args, **kwargs):
        # Créer sans avoir dit quoi n'a pas de sens : la fiche à remplir dépend
        # du genre. L'écran de choix vient donc avant le formulaire.
        if "pk" not in kwargs and not self._genre(None):
            return render(
                request,
                "documents/redaction/choix_genre.html",
                {"nav": "documents_rediges", "fiches": FICHES.items()},
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        document = self._document()
        genre = self._genre(document)
        fiche_du_genre = fiche(genre)
        return {
            **super().get_context_data(**kwargs),
            "nav": "documents_rediges",
            "document": document,
            "genre": genre,
            "fiche": fiche_du_genre,
            "form": kwargs.get("form") or DocumentRedigeForm(instance=document, fiche=fiche_du_genre),
            "form_fiche": kwargs.get("form_fiche")
            or fiche_du_genre.formulaire(initial=(document.donnees if document else None) or {}),
            "verrouille": document is not None and not document.est_modifiable,
        }

    def post(self, request, *args, **kwargs):
        document = self._document()
        if document is not None and not document.est_modifiable:
            messages.error(request, "Rouvrez le document avant de le modifier.")
            return redirect("redaction:documents")

        genre = self._genre(document)
        fiche_du_genre = fiche(genre)
        formulaire = DocumentRedigeForm(_saisie_avec_corps(request.POST), instance=document, fiche=fiche_du_genre)
        formulaire_fiche = fiche_du_genre.formulaire(request.POST)

        # La fiche est validée mais n'arrête pas l'enregistrement : un brouillon
        # a le droit d'être incomplet. C'est « finaliser() » qui exige qu'elle
        # soit entière, au moment où le document devient un acte.
        formulaire_fiche.is_valid()
        if not formulaire.is_valid():
            return self.render_to_response(self.get_context_data(form=formulaire, form_fiche=formulaire_fiche))

        creation = document is None
        document = formulaire.save(commit=False)
        document.genre = genre or DocumentRedige.Genre.COURRIER
        document.donnees = {
            nom: valeur for nom, valeur in formulaire_fiche.cleaned_data.items() if valeur not in (None, "")
        }
        if document.redige_par_id is None:
            document.redige_par = request.user
        document.save()
        if not creation:
            # Un aperçu déjà prêt ou encore en vol décrit désormais une
            # ancienne version du texte.
            document.invalider_generation()

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
                if planifier_document_redige(document):
                    avis = f"« {document.reference} » est finalisé. Son PDF est généré en arrière-plan."
                else:
                    avis = f"« {document.reference} » est finalisé, mais le service PDF est indisponible."
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
    """Télécharge un PDF prêt ou planifie son rendu sans bloquer la page."""

    def get(self, request, pk):
        document = get_object_or_404(DocumentRedige, pk=pk)

        if document.fichier_pdf:
            journaliser(
                JournalAudit.Action.CONSULTATION_SENSIBLE,
                utilisateur=request.user,
                request=request,
                objet=document,
                objet_libelle=f"PDF du document « {document.titre} »",
            )
            return FileResponse(
                document.fichier_pdf.open("rb"),
                as_attachment=True,
                filename=Path(document.fichier_pdf.name).name,
            )

        if document.generation_active:
            messages.info(request, "Le PDF est déjà en cours de préparation.")
        elif planifier_document_redige(document):
            messages.success(request, "Le PDF est préparé en arrière-plan. Cette page se mettra à jour.")
        else:
            messages.error(request, "Le service de génération PDF est momentanément indisponible.")
        if document.est_modifiable:
            return redirect("redaction:document_edition", pk=document.pk)
        return redirect("redaction:documents")


class DocumentRedigeEtatView(StaffRoleRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(DocumentRedige, pk=pk)
        return render(request, "documents/redaction/_etat_pdf.html", {"document": document})
