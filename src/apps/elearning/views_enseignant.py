"""
Portail enseignant — production du contenu vidéo.

L'enseignant ne voit et ne modifie que les modules dont il est responsable :
la restriction est portée par les jeux de requêtes, pas par des vérifications
dispersées dans les gabarits.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Max, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.text import slugify
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from apps.core.mixins import TeacherRoleRequiredMixin
from apps.core.services.audit import journaliser
from apps.elearning.diffusion import fournisseur
from apps.elearning.forms import (
    ChapitreForm,
    LeconForm,
    ModuleForm,
    SousTitreForm,
    VideoExterneForm,
)
from apps.elearning.models import (
    Chapitre,
    InscriptionModule,
    Lecon,
    ModuleFormation,
    ProgressionLecon,
    VideoAsset,
)


class ProfesseurMixin(TeacherRoleRequiredMixin):
    """Restreint l'accès aux modules dont l'utilisateur est responsable."""

    @property
    def professeur(self):
        return getattr(self.request.user, "profil_professeur", None)

    def mes_modules(self):
        if self.professeur is None:
            return ModuleFormation.objects.none()
        return ModuleFormation.objects.filter(responsable=self.professeur)

    def module_ou_404(self, slug) -> ModuleFormation:
        return get_object_or_404(self.mes_modules(), slug=slug)


# ══════════════════════════════════════════════
# Modules
# ══════════════════════════════════════════════


class MesModulesView(ProfesseurMixin, ListView):
    template_name = "elearning/enseignant/modules.html"
    context_object_name = "modules"

    def get_queryset(self):
        return (
            self.mes_modules()
            .select_related("discipline")
            .annotate(nb_inscrits=Count("inscriptions", distinct=True))
            .order_by("statut", "titre")
        )

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["professeur"] = self.professeur
        return contexte


class ModuleCreateView(ProfesseurMixin, CreateView):
    model = ModuleFormation
    form_class = ModuleForm
    template_name = "elearning/enseignant/module_form.html"

    def form_valid(self, form):
        module = form.save(commit=False)
        module.responsable = self.professeur
        module.slug = ModuleForm._slug_libre(module.titre)
        module.save()
        form.save_m2m()
        journaliser("creation", request=self.request, objet=module)
        messages.success(self.request, "Module créé. Ajoutez-y des chapitres et des leçons.")
        return redirect(reverse("elearning:enseignant_structure", kwargs={"slug": module.slug}))


class ModuleUpdateView(ProfesseurMixin, UpdateView):
    model = ModuleFormation
    form_class = ModuleForm
    template_name = "elearning/enseignant/module_form.html"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return self.mes_modules()

    def form_valid(self, form):
        module = form.save()
        journaliser("modification", request=self.request, objet=module)
        messages.success(self.request, "Module mis à jour.")
        return redirect(reverse("elearning:enseignant_structure", kwargs={"slug": module.slug}))


class ModuleStructureView(ProfesseurMixin, DetailView):
    """Vue d'assemblage : chapitres, leçons, état de publication."""

    template_name = "elearning/enseignant/structure.html"
    context_object_name = "module"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return self.mes_modules().prefetch_related("chapitres__lecons__video")

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        publiable, motif = self.object.peut_etre_publie()
        lecons = list(self.object.lecons())
        contexte.update(
            {
                "chapitres": self.object.chapitres.prefetch_related("lecons__video"),
                "publiable": publiable,
                "motif_blocage": motif,
                # Un aperçu s'ouvre à tous. Coché leçon par leçon, on perd de
                # vue combien du module est devenu gratuit : le total est donc
                # affiché, et l'alerte se déclenche quand il ne reste plus rien
                # à protéger.
                "nombre_lecons": len(lecons),
                "nombre_apercus": sum(1 for lecon in lecons if lecon.apercu_gratuit),
                "apercu_integral": self.object.acces_est_restreint and self.object.apercus_couvrent_tout(),
                "videos": VideoAsset.objects.filter(uploade_par=self.request.user).order_by("-created_at")[:20],
                "form_chapitre": ChapitreForm(module=self.object),
            }
        )
        return contexte


class ModulePublierView(ProfesseurMixin, View):
    """Publication contrôlée : refusée si une vidéo n'est pas prête."""

    http_method_names = ["post"]

    def post(self, request, slug):
        module = self.module_ou_404(slug)
        try:
            module.publier()
        except ValidationError as erreur:
            messages.error(request, f"Publication impossible — {erreur.messages[0]}")
        else:
            journaliser("modification", request=request, objet=module, objet_libelle=f"Publication : {module.titre}")
            messages.success(request, "Module publié. Il est désormais visible au catalogue.")
        return redirect(reverse("elearning:enseignant_structure", kwargs={"slug": slug}))


class ModuleDepublierView(ProfesseurMixin, View):
    http_method_names = ["post"]

    def post(self, request, slug):
        module = self.module_ou_404(slug)
        module.statut = ModuleFormation.StatutPublication.BROUILLON
        module.save(update_fields=["statut", "updated_at"])
        journaliser("modification", request=request, objet=module, objet_libelle=f"Dépublication : {module.titre}")
        messages.success(request, "Module repassé en brouillon.")
        return redirect(reverse("elearning:enseignant_structure", kwargs={"slug": slug}))


# ══════════════════════════════════════════════
# Chapitres et leçons
# ══════════════════════════════════════════════


class ChapitreCreateView(ProfesseurMixin, View):
    http_method_names = ["post"]

    def post(self, request, slug):
        module = self.module_ou_404(slug)
        formulaire = ChapitreForm(request.POST, module=module)
        if formulaire.is_valid():
            try:
                with transaction.atomic():
                    module = ModuleFormation.objects.select_for_update().get(pk=module.pk)
                    chapitre = formulaire.save(commit=False)
                    chapitre.module = module
                    if not chapitre.ordre:
                        dernier_ordre = module.chapitres.aggregate(maximum=Max("ordre"))["maximum"] or 0
                        chapitre.ordre = dernier_ordre + 1
                    chapitre.save()
            except IntegrityError:
                messages.error(request, "Cette position vient d'être utilisée. Réessayez avec une autre position.")
            else:
                messages.success(request, "Chapitre ajouté.")
        else:
            messages.error(request, " ".join(erreur for erreurs in formulaire.errors.values() for erreur in erreurs))
        return redirect(reverse("elearning:enseignant_structure", kwargs={"slug": slug}))


class ChapitreDeleteView(ProfesseurMixin, DeleteView):
    model = Chapitre
    template_name = "elearning/enseignant/confirmer_suppression.html"

    def get_queryset(self):
        return Chapitre.objects.filter(module__in=self.mes_modules())

    def get_success_url(self):
        return reverse("elearning:enseignant_structure", kwargs={"slug": self.object.module.slug})

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "objet": self.object,
                "libelle": f"le chapitre « {self.object.titre} »",
                "consequence": f"Ses {self.object.lecons.count()} leçon(s) seront également supprimées.",
                "annuler_url": self.get_success_url(),
            }
        )
        return contexte


class LeconFormMixin(ProfesseurMixin):
    form_class = LeconForm
    template_name = "elearning/enseignant/lecon_form.html"

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "enseignant": self.request.user,
            "chapitre": self.chapitre,
        }

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "chapitre": self.chapitre}

    def get_success_url(self):
        return reverse("elearning:enseignant_structure", kwargs={"slug": self.chapitre.module.slug})


class LeconCreateView(LeconFormMixin, CreateView):
    model = Lecon

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.chapitre = get_object_or_404(
                Chapitre.objects.filter(module__in=self.mes_modules()), pk=kwargs["chapitre_pk"]
            )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.chapitre = Chapitre.objects.select_for_update().select_related("module").get(pk=self.chapitre.pk)
                lecon = form.save(commit=False)
                lecon.chapitre = self.chapitre
                if not lecon.ordre:
                    dernier_ordre = self.chapitre.lecons.aggregate(maximum=Max("ordre"))["maximum"] or 0
                    lecon.ordre = dernier_ordre + 1
                lecon.slug = self._slug_unique(lecon.titre)
                lecon.full_clean()
                lecon.save()
        except ValidationError as erreur:
            self._ajouter_erreurs_validation(form, erreur)
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error("ordre", "Cette position vient d'être utilisée. Choisissez-en une autre.")
            return self.form_invalid(form)
        self.chapitre.module.recalculer_duree()
        messages.success(self.request, "Leçon ajoutée.")
        return redirect(self.get_success_url())

    def _slug_unique(self, titre):
        base = slugify(titre)[:240] or "lecon"
        slug = base
        suffixe = 2
        while self.chapitre.lecons.filter(slug=slug).exists():
            terminaison = f"-{suffixe}"
            slug = f"{base[: 250 - len(terminaison)]}{terminaison}"
            suffixe += 1
        return slug

    @staticmethod
    def _ajouter_erreurs_validation(form, erreur):
        if hasattr(erreur, "error_dict"):
            for champ, erreurs in erreur.error_dict.items():
                cible = champ if champ in form.fields else None
                for detail in erreurs:
                    form.add_error(cible, detail)
            return
        for detail in erreur.error_list:
            form.add_error(None, detail)


class LeconUpdateView(LeconFormMixin, UpdateView):
    model = Lecon

    def get_queryset(self):
        return Lecon.objects.filter(chapitre__module__in=self.mes_modules())

    @property
    def chapitre(self):
        return self.object.chapitre

    def form_valid(self, form):
        lecon = form.save()
        lecon.chapitre.module.recalculer_duree()
        messages.success(self.request, "Leçon mise à jour.")
        return redirect(self.get_success_url())


class LeconDeleteView(ProfesseurMixin, DeleteView):
    model = Lecon
    template_name = "elearning/enseignant/confirmer_suppression.html"

    def get_queryset(self):
        return Lecon.objects.filter(chapitre__module__in=self.mes_modules())

    def get_success_url(self):
        return reverse("elearning:enseignant_structure", kwargs={"slug": self.object.chapitre.module.slug})

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        vues = ProgressionLecon.objects.filter(lecon=self.object).count()
        contexte.update(
            {
                "objet": self.object,
                "libelle": f"la leçon « {self.object.titre} »",
                "consequence": (
                    f"{vues} progression(s) d'étudiant seront perdues." if vues else "Aucun étudiant ne l'a encore vue."
                ),
                "annuler_url": self.get_success_url(),
            }
        )
        return contexte


class ReordonnerLeconsView(ProfesseurMixin, View):
    """Persiste un nouvel ordre de leçons au sein d'un chapitre."""

    http_method_names = ["post"]

    def post(self, request, chapitre_pk):
        chapitre = get_object_or_404(Chapitre.objects.filter(module__in=self.mes_modules()), pk=chapitre_pk)
        identifiants = request.POST.getlist("lecon")
        lecons = {str(lecon.pk): lecon for lecon in chapitre.lecons.all()}

        # L'ordre transitoire évite de heurter la contrainte d'unicité en cours
        # de réécriture : deux leçons ne peuvent pas porter le même rang.
        for décalage, identifiant in enumerate(identifiants, start=1000):
            lecon = lecons.get(identifiant)
            if lecon is not None:
                Lecon.objects.filter(pk=lecon.pk).update(ordre=décalage)
        for rang, identifiant in enumerate(identifiants, start=1):
            lecon = lecons.get(identifiant)
            if lecon is not None:
                Lecon.objects.filter(pk=lecon.pk).update(ordre=rang)

        if request.headers.get("HX-Request"):
            return JsonResponse({"ordre": "enregistré"})
        messages.success(request, "Ordre des leçons enregistré.")
        return redirect(reverse("elearning:enseignant_structure", kwargs={"slug": chapitre.module.slug}))


# ══════════════════════════════════════════════
# Vidéos et sous-titres
# ══════════════════════════════════════════════


class VideoUploadView(ProfesseurMixin, TemplateView):
    """Référence une vidéo externe sans jamais recevoir son fichier."""

    template_name = "elearning/enseignant/video_form.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.setdefault("form", VideoExterneForm())
        contexte["videos"] = VideoAsset.objects.filter(uploade_par=self.request.user).order_by("-created_at")[:30]
        return contexte

    def post(self, request, *args, **kwargs):
        return self._referencer(request)

    def _referencer(self, request):
        """La vidéo vit chez le fournisseur : on n'enregistre que sa référence."""
        formulaire = VideoExterneForm(request.POST)
        if not formulaire.is_valid():
            return self.render_to_response(self.get_context_data(form=formulaire))

        video = VideoAsset.objects.create(
            titre=formulaire.cleaned_data["titre"],
            cle_stockage=formulaire.cleaned_data["identifiant"],
            fournisseur=formulaire.cleaned_data["fournisseur"],
            duree_secondes=formulaire.cleaned_data.get("duree_secondes") or 0,
            transcription=formulaire.cleaned_data["transcription"],
            uploade_par=request.user,
            # Rien à préparer de notre côté : l'encodage est fait chez le
            # fournisseur avant que l'identifiant ne soit communiqué.
            statut_traitement=VideoAsset.StatutTraitement.PRET,
        )
        journaliser("creation", request=request, objet=video)
        messages.success(request, "Vidéo référencée. Elle peut être rattachée à une leçon.")
        return redirect(reverse("elearning:enseignant_videos"))


class SousTitreCreateView(ProfesseurMixin, CreateView):
    form_class = SousTitreForm
    template_name = "elearning/enseignant/soustitre_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.video = get_object_or_404(VideoAsset, pk=kwargs["video_pk"], uploade_par=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "video": self.video}

    def form_valid(self, form):
        piste = form.save(commit=False)
        piste.video = self.video
        piste.save()
        messages.success(self.request, "Sous-titres associés à la vidéo.")
        return redirect(reverse("elearning:enseignant_videos"))


class VideoDeleteView(ProfesseurMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        video = get_object_or_404(VideoAsset, pk=pk, uploade_par=request.user)
        if video.lecons.exists():
            messages.error(request, "Cette vidéo est utilisée par une leçon : retirez-la d'abord.")
            return redirect(reverse("elearning:enseignant_videos"))

        fournisseur_video = fournisseur(video.fournisseur)
        fournisseur_video.supprimer(video.cle_stockage)
        journaliser("suppression", request=request, objet=video)
        video.delete()
        if fournisseur_video.accepte_televersement:
            messages.success(request, "Ancienne vidéo locale supprimée.")
        else:
            messages.success(
                request,
                "Référence retirée de l'institut. Le média reste disponible chez le fournisseur externe.",
            )
        return redirect(reverse("elearning:enseignant_videos"))


# ══════════════════════════════════════════════
# Audience
# ══════════════════════════════════════════════


class AudienceView(ProfesseurMixin, DetailView):
    """Ce que les étudiants font réellement du module."""

    template_name = "elearning/enseignant/audience.html"
    context_object_name = "module"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return self.mes_modules()

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        module = self.object

        inscriptions = InscriptionModule.objects.filter(module=module)
        lecons = list(module.lecons())

        # Taux d'achèvement leçon par leçon : là où la courbe s'effondre se
        # trouve la leçon à retravailler.
        detail = []
        total_inscrits = inscriptions.count()
        for lecon in lecons:
            progressions = ProgressionLecon.objects.filter(lecon=lecon, inscription__module=module)
            terminees = progressions.filter(termine=True).count()
            detail.append(
                {
                    "lecon": lecon,
                    "commencees": progressions.count(),
                    "terminees": terminees,
                    "taux": round(terminees / total_inscrits * 100) if total_inscrits else 0,
                    "avancement_moyen": round(progressions.aggregate(m=Avg("pourcentage_vu"))["m"] or 0),
                }
            )

        contexte.update(
            {
                "total_inscrits": total_inscrits,
                "actifs": inscriptions.filter(statut=InscriptionModule.StatutAcces.ACTIF).count(),
                "termines": inscriptions.filter(statut=InscriptionModule.StatutAcces.TERMINE).count(),
                "progression_moyenne": round(inscriptions.aggregate(m=Avg("progression_percent"))["m"] or 0),
                "jamais_commence": inscriptions.filter(
                    Q(progression_percent=0) & ~Q(statut=InscriptionModule.StatutAcces.TERMINE)
                ).count(),
                "detail_lecons": detail,
                "inscriptions": inscriptions.select_related("etudiant__utilisateur").order_by("-progression_percent")[
                    :50
                ],
            }
        )
        return contexte


class TableauDeBordVideoView(ProfesseurMixin, TemplateView):
    """Point d'entrée du portail vidéo enseignant."""

    template_name = "elearning/enseignant/tableau_de_bord.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        modules = self.mes_modules()
        if self.professeur is None:
            raise Http404("Aucune fiche enseignant n'est rattachée à ce compte.")

        contexte.update(
            {
                "professeur": self.professeur,
                "modules": modules.select_related("discipline").order_by("statut", "titre"),
                "nb_publies": modules.filter(statut=ModuleFormation.StatutPublication.PUBLIE).count(),
                "nb_brouillons": modules.filter(statut=ModuleFormation.StatutPublication.BROUILLON).count(),
                "nb_inscrits": InscriptionModule.objects.filter(module__in=modules).count(),
                "videos_en_attente": VideoAsset.objects.filter(
                    uploade_par=self.request.user,
                    statut_traitement__in=[
                        VideoAsset.StatutTraitement.EN_ATTENTE,
                        VideoAsset.StatutTraitement.EN_COURS,
                    ],
                ).count(),
            }
        )
        return contexte
