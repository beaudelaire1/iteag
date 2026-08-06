from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from apps.core.mixins import StaffRoleRequiredMixin
from apps.library import services
from apps.library.models import SuspensionBibliotheque


class LeverSuspensionView(StaffRoleRequiredMixin, View):
    """Levée exceptionnelle d'une suspension, avec motif obligatoire."""

    http_method_names = ["post"]

    def post(self, request, pk):
        suspension = get_object_or_404(
            SuspensionBibliotheque.objects.select_related("emprunteur", "emprunt__notice"),
            pk=pk,
        )
        try:
            services.lever_suspension(
                suspension,
                par=request.user,
                motif=request.POST.get("motif", ""),
            )
        except ValidationError as erreur:
            messages.error(request, erreur.messages[0])
        else:
            messages.success(
                request,
                f"La suspension de {suspension.emprunteur} a été levée.",
            )
        return redirect("library:gestion_emprunts")
