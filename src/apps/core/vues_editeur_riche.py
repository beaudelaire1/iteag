"""Petites vues auxiliaires de Draftail dans les portails privés."""

from django.contrib.auth.mixins import LoginRequiredMixin
from wagtail.admin.forms.choosers import ExternalLinkChooserForm
from wagtail.admin.views.chooser import BaseLinkFormView


class LienExterneEditeurView(LoginRequiredMixin, BaseLinkFormView):
    """Dialogue de lien Wagtail, sans exiger un compte d'administrateur.

    Il ne parcourt ni pages ni documents : il recueille seulement une adresse
    web. Le résultat est ensuite converti et assaini comme le reste du texte.
    """

    form_prefix = "external-link-chooser"
    form_class = ExternalLinkChooserForm
    template_name = "core/editeur_riche/lien_externe.html"
    step_name = "external_link"
    link_url_field_name = "url"
