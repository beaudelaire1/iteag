"""Import et export des fichiers du secrétariat.

Un même écran par entité : le gabarit à télécharger, l'export des données
actuelles, et le dépôt d'un fichier. Les trois au même endroit, parce qu'un
import se prépare presque toujours à partir d'un export.
"""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView, View

from apps.administration.services.tableurs import SCHEMAS
from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.models import JournalAudit
from apps.core.services import tableur
from apps.core.services.audit import journaliser
from apps.core.services.import_tableur import executer

FORMATS = {"csv", "xlsx"}


def _schema(cle: str):
    schema = SCHEMAS.get(cle)
    if schema is None:
        raise Http404("Jeu de données inconnu.")
    return schema


class TableursView(StaffRoleRequiredMixin, TemplateView):
    """La liste des jeux de données, et ce qu'on peut en faire."""

    template_name = "administration/tableurs.html"

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "nav": "tableurs",
            "schemas": list(SCHEMAS.values()),
        }


class TableurDetailView(StaffRoleRequiredMixin, TemplateView):
    template_name = "administration/tableur_detail.html"

    def get_context_data(self, **kwargs):
        schema = _schema(self.kwargs["cle"])
        return {
            **super().get_context_data(**kwargs),
            "nav": "tableurs",
            "schema": schema,
            "colonnes": schema.colonnes,
        }


class GabaritView(StaffRoleRequiredMixin, View):
    """Le fichier vide à remplir, en-têtes et ligne d'exemple."""

    def get(self, request, cle, format_fichier):
        if format_fichier not in FORMATS:
            raise Http404("Format inconnu.")
        schema = _schema(cle)
        return tableur.gabarit(f"gabarit-{cle}.{format_fichier}", schema.colonnes, format_fichier)


class ExportView(StaffRoleRequiredMixin, View):
    def get(self, request, cle, format_fichier):
        if format_fichier not in FORMATS:
            raise Http404("Format inconnu.")
        schema = _schema(cle)
        lignes = list(schema.exporter())
        # Un export sort des données nominatives du système : il se journalise
        # au même titre qu'une modification.
        journaliser(
            JournalAudit.Action.EXPORT,
            utilisateur=request.user,
            request=request,
            objet_libelle=f"Export {schema.libelle} ({len(lignes)} ligne(s))",
        )
        nom = f"iteag-{cle}.{format_fichier}"
        if format_fichier == "csv":
            return tableur.ecrire_csv(nom, schema.entetes, lignes)
        return tableur.ecrire_xlsx(nom, schema.entetes, lignes)


class ImportView(StaffRoleRequiredMixin, TemplateView):
    """Dépôt d'un fichier. Tout passe, ou rien n'est enregistré."""

    template_name = "administration/tableur_detail.html"
    http_method_names = ["post"]

    def post(self, request, cle):
        schema = _schema(cle)
        fichier = request.FILES.get("fichier")
        if fichier is None:
            messages.error(request, "Choisissez un fichier à importer.")
            return redirect("administration:tableur_detail", cle=cle)

        rapport = executer(schema, fichier)

        if rapport.est_en_echec:
            messages.error(request, f"{schema.libelle} — {rapport.resume()}")
            return self.render_to_response(
                {
                    "nav": "tableurs",
                    "schema": schema,
                    "colonnes": schema.colonnes,
                    "rapport": rapport,
                }
            )

        journaliser(
            JournalAudit.Action.MODIFICATION,
            utilisateur=request.user,
            request=request,
            objet_libelle=f"Import {schema.libelle}",
            creations=rapport.crees,
            mises_a_jour=rapport.mis_a_jour,
        )
        messages.success(request, f"{schema.libelle} — {rapport.resume()}")
        return redirect("administration:tableur_detail", cle=cle)


def _url_export(cle: str, format_fichier: str) -> str:
    return reverse("administration:tableur_export", kwargs={"cle": cle, "format_fichier": format_fichier})
