from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.models import User
from apps.core.mixins import AdminRoleRequiredMixin, StudentRoleRequiredMixin
from apps.core.models import JournalAudit, Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier, notifier_plusieurs
from apps.core.services.redaction import en_texte
from apps.website.formulaires_temoignages import TemoignageEtudiantForm
from apps.website.models_publications import TemoignageEtudiant


class TemoignagePublicView(DetailView):
    """Lecture publique d'un témoignage déjà validé par la direction.

    La grille d'accueil ne doit pas devenir une zone de lecture longue : elle
    présente un extrait stable, puis cette page porte le texte complet dans un
    espace dédié. Un identifiant connu ne suffit jamais à exposer un brouillon,
    un refus ou un témoignage dont le consentement a été retiré.
    """

    template_name = "website/temoignages/detail_public.html"
    context_object_name = "temoignage"

    def get_queryset(self):
        return TemoignageEtudiant.objects.filter(
            statut=TemoignageEtudiant.Statut.PUBLIE,
            consentement_publication=True,
        ).select_related("etudiant")


class TemoignageEtudiantView(StudentRoleRequiredMixin, TemplateView):
    template_name = "etudiant/temoignage.html"

    def _temoignage(self):
        return TemoignageEtudiant.objects.filter(etudiant=self.request.user).first()

    def _promotion(self):
        profil = self.request.user.profil_etudiant
        if profil.promotion_id:
            return str(profil.promotion)
        if profil.parcours_id:
            return str(profil.parcours)
        return "Étudiant ITEAG"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        temoignage = self._temoignage()
        contexte.update(
            {
                "nav": "temoignage",
                "temoignage": temoignage,
                "form": kwargs.get("form")
                or TemoignageEtudiantForm(
                    initial={
                        "texte": temoignage.texte if temoignage else "",
                        "consentement_publication": temoignage.consentement_publication if temoignage else False,
                    }
                ),
            }
        )
        return contexte

    def post(self, request, *args, **kwargs):
        formulaire = TemoignageEtudiantForm(request.POST, request.FILES)
        if not formulaire.is_valid():
            return self.render_to_response(self.get_context_data(form=formulaire))

        nom = request.user.get_full_name().strip() or request.user.username
        temoignage, creation = TemoignageEtudiant.objects.get_or_create(
            etudiant=request.user,
            defaults={"nom_affiche": nom, "promotion": self._promotion()},
        )
        temoignage.nom_affiche = nom
        temoignage.promotion = self._promotion()
        temoignage.texte = formulaire.cleaned_data["texte"]
        temoignage.consentement_publication = formulaire.cleaned_data["consentement_publication"]

        nouvelle_photo = formulaire.cleaned_data.get("photo")
        supprimer_photo = formulaire.cleaned_data.get("supprimer_photo")
        if nouvelle_photo:
            if temoignage.photo:
                temoignage.photo.delete(save=False)
            temoignage.photo = nouvelle_photo
        elif supprimer_photo and temoignage.photo:
            temoignage.photo.delete(save=False)

        # Toute modification repasse devant la direction : une version publiée
        # ne peut jamais être modifiée publiquement sans nouvelle validation.
        temoignage.statut = TemoignageEtudiant.Statut.EN_ATTENTE
        temoignage.motif_refus = ""
        temoignage.valide_le = None
        temoignage.valide_par = None
        temoignage.save()

        notifier_plusieurs(
            User.objects.filter(is_active=True, role=User.Role.ADMIN),
            f"Témoignage à valider — {temoignage.nom_affiche}",
            type_notification=Notification.Type.SYSTEME,
            message=(
                f"{temoignage.nom_affiche} a {'soumis' if creation else 'modifié'} un témoignage. "
                "Il reste hors ligne jusqu'à la décision de la direction."
            ),
            details=[
                {"libelle": "Étudiant", "valeur": temoignage.nom_affiche},
                {"libelle": "Promotion", "valeur": temoignage.promotion or "—"},
                {"libelle": "Extrait", "valeur": en_texte(temoignage.texte, limite=220)},
                {"libelle": "Photo", "valeur": "Oui" if temoignage.photo else "Non"},
            ],
            url_cible=reverse("website:temoignages_gestion"),
        )

        messages.success(request, "Votre témoignage a été transmis à la direction pour validation.")
        return redirect("website:temoignage_etudiant")


class TemoignageListView(AdminRoleRequiredMixin, ListView):
    template_name = "administration/temoignages.html"
    context_object_name = "temoignages"

    def get_queryset(self):
        return TemoignageEtudiant.objects.select_related("etudiant", "valide_par").order_by("statut", "-soumis_le")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        base = TemoignageEtudiant.objects.all()
        contexte.update(
            {
                "nav": "temoignages",
                "en_attente": base.filter(statut=TemoignageEtudiant.Statut.EN_ATTENTE).count(),
                "publies": base.filter(statut=TemoignageEtudiant.Statut.PUBLIE).count(),
                "refuses": base.filter(statut=TemoignageEtudiant.Statut.REFUSE).count(),
                "retires": base.filter(statut=TemoignageEtudiant.Statut.RETIRE).count(),
            }
        )
        return contexte


class TemoignageDecisionView(AdminRoleRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        temoignage = get_object_or_404(TemoignageEtudiant, pk=request.POST.get("temoignage_id"))
        action = request.POST.get("action")
        details = [{"libelle": "Témoignage", "valeur": en_texte(temoignage.texte, limite=220)}]

        if action == "publier":
            if not temoignage.consentement_publication:
                messages.error(request, "Ce témoignage ne peut pas être publié sans consentement explicite.")
                return redirect("website:temoignages_gestion")
            temoignage.statut = TemoignageEtudiant.Statut.PUBLIE
            temoignage.motif_refus = ""
            temoignage.valide_le = timezone.now()
            temoignage.valide_par = request.user
            avis = f"Le témoignage de {temoignage.nom_affiche} est publié."
            titre_notification = "Votre témoignage ITEAG est publié"
            message_notification = (
                "La direction a validé votre témoignage. Il est maintenant visible sur le site de l'ITEAG."
            )
        elif action == "refuser":
            if temoignage.statut == TemoignageEtudiant.Statut.PUBLIE:
                messages.error(request, "Retirez d'abord du site un témoignage déjà publié.")
                return redirect("website:temoignages_gestion")
            motif = (request.POST.get("motif") or "").strip()
            if not motif:
                messages.error(request, "Indiquez le motif du refus pour que l'étudiant puisse corriger son texte.")
                return redirect("website:temoignages_gestion")
            temoignage.statut = TemoignageEtudiant.Statut.REFUSE
            temoignage.motif_refus = motif
            temoignage.valide_le = None
            temoignage.valide_par = request.user
            avis = f"Le témoignage de {temoignage.nom_affiche} a été refusé."
            titre_notification = "Votre témoignage ITEAG est à reprendre"
            message_notification = (
                "La direction vous demande de reprendre votre témoignage avant une éventuelle publication."
            )
            details.append({"libelle": "Motif", "valeur": motif})
        elif action == "retirer":
            if temoignage.statut != TemoignageEtudiant.Statut.PUBLIE:
                messages.error(request, "Seul un témoignage actuellement publié peut être retiré du site.")
                return redirect("website:temoignages_gestion")
            temoignage.statut = TemoignageEtudiant.Statut.RETIRE
            avis = f"Le témoignage de {temoignage.nom_affiche} a été retiré du site."
            titre_notification = "Votre témoignage ITEAG a été retiré du site"
            message_notification = (
                "La direction a retiré votre témoignage de l'affichage public. "
                "Il reste enregistré dans votre espace et pourra être republié ultérieurement."
            )
        else:
            messages.error(request, "Action inconnue.")
            return redirect("website:temoignages_gestion")

        temoignage.save(update_fields=["statut", "motif_refus", "valide_le", "valide_par", "modifie_le", "texte"])
        journaliser(
            JournalAudit.Action.CHANGEMENT_STATUT,
            utilisateur=request.user,
            request=request,
            objet=temoignage,
            objet_libelle=f"Témoignage « {temoignage.nom_affiche} » → {temoignage.get_statut_display()}",
        )
        notifier(
            temoignage.etudiant,
            titre_notification,
            type_notification=Notification.Type.SYSTEME,
            message=message_notification,
            details=details,
            url_cible=reverse("website:temoignage_etudiant"),
        )
        messages.success(request, avis)
        return redirect("website:temoignages_gestion")
