"""
Vues de la formation vidéo.

Règle absolue : aucune adresse de fichier n'est rendue dans un gabarit. Le
lecteur la demande par un appel authentifié distinct, et le droit est
revérifié à chaque demande (ADR-001).
"""

import json
import uuid

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.generic import DetailView, ListView, TemplateView

from apps.elearning.models import (
    AttestationModule,
    InscriptionModule,
    Lecon,
    ModuleFormation,
    ProgressionLecon,
)
from apps.elearning.services import progression as service_progression
from apps.elearning.services.acces import journaliser_acces, verifier_acces
from apps.elearning.storage import LocalStockageVideo, stockage_video

TTL_LECTURE = 300


# ══════════════════════════════════════════════
# Catalogue public
# ══════════════════════════════════════════════


class CataloguePublicView(ListView):
    """Vitrine des modules publiés — PUB, conversion."""

    template_name = "elearning/catalogue.html"
    context_object_name = "modules"
    paginate_by = 12

    def get_queryset(self):
        queryset = (
            ModuleFormation.objects.filter(statut=ModuleFormation.StatutPublication.PUBLIE)
            .select_related("discipline", "responsable")
            .prefetch_related("chapitres__lecons")
        )
        discipline = self.request.GET.get("discipline")
        niveau = self.request.GET.get("niveau")
        if discipline:
            queryset = queryset.filter(discipline__slug=discipline)
        if niveau:
            queryset = queryset.filter(niveau=niveau)
        return queryset

    def get_context_data(self, **kwargs):
        from apps.formations.models import Discipline

        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "disciplines": Discipline.objects.all(),
                "niveaux": ModuleFormation.Niveau.choices,
                "discipline_courante": self.request.GET.get("discipline", ""),
                "niveau_courant": self.request.GET.get("niveau", ""),
            }
        )
        return contexte


class ModuleDetailView(DetailView):
    """Fiche d'un module : sommaire, progression, appel à l'action."""

    model = ModuleFormation
    template_name = "elearning/module_detail.html"
    context_object_name = "module"

    def get_queryset(self):
        return ModuleFormation.objects.select_related("discipline", "responsable", "cours").prefetch_related(
            "chapitres__lecons__video", "prerequis"
        )

    def get_object(self, queryset=None):
        module = super().get_object(queryset)
        if not module.est_publie:
            from apps.elearning.services.acces import _est_gestionnaire

            if not _est_gestionnaire(self.request.user, module):
                raise Http404
        return module

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        module = self.object
        inscription = self._inscription(module)

        faites = set()
        if inscription:
            faites = set(
                ProgressionLecon.objects.filter(inscription=inscription, termine=True).values_list(
                    "lecon_id", flat=True
                )
            )

        contexte.update(
            {
                "inscription": inscription,
                "chapitres": module.chapitres.prefetch_related("lecons__video"),
                "lecons_terminees": faites,
                "lecon_suivante": service_progression.lecon_suivante(inscription) if inscription else None,
                "attestation": getattr(inscription, "attestation", None) if inscription else None,
            }
        )
        return contexte

    def _inscription(self, module) -> InscriptionModule | None:
        profil = getattr(self.request.user, "profil_etudiant", None)
        if profil is None:
            return None
        return InscriptionModule.objects.filter(etudiant=profil, module=module).first()


# ══════════════════════════════════════════════
# Espace étudiant
# ══════════════════════════════════════════════


class MesFormationsView(LoginRequiredMixin, TemplateView):
    """Modules auxquels l'étudiant a accès, avec l'état de chacun."""

    template_name = "elearning/mes_formations.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        profil = getattr(self.request.user, "profil_etudiant", None)

        inscriptions = []
        if profil is not None:
            inscriptions = (
                InscriptionModule.objects.filter(etudiant=profil)
                .select_related("module", "module__discipline", "module__responsable")
                .order_by("statut", "module__ordre")
            )

        contexte.update(
            {
                "profil": profil,
                "inscriptions": inscriptions,
                "en_cours": [i for i in inscriptions if i.statut == InscriptionModule.StatutAcces.ACTIF],
                "terminees": [i for i in inscriptions if i.statut == InscriptionModule.StatutAcces.TERMINE],
                "indisponibles": [
                    i
                    for i in inscriptions
                    if i.statut
                    in (
                        InscriptionModule.StatutAcces.SUSPENDU,
                        InscriptionModule.StatutAcces.EXPIRE,
                        InscriptionModule.StatutAcces.REVOQUE,
                    )
                ],
            }
        )
        return contexte


class LeconDetailView(DetailView):
    """Page du lecteur. Ne contient aucune adresse de fichier."""

    model = Lecon
    template_name = "elearning/lecon_detail.html"
    context_object_name = "lecon"
    slug_field = "slug"
    slug_url_kwarg = "lecon_slug"

    def get_object(self, queryset=None):
        return get_object_or_404(
            Lecon.objects.select_related("chapitre__module", "video").prefetch_related("video__sous_titres"),
            chapitre__module__slug=self.kwargs["slug"],
            slug=self.kwargs["lecon_slug"],
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        decision = verifier_acces(request.user, self.object)

        if not decision.autorise:
            journaliser_acces(decision, utilisateur=request.user, lecon=self.object, request=request)
            return render(
                request,
                "elearning/acces_requis.html",
                {
                    "lecon": self.object,
                    "module": self.object.chapitre.module,
                    "motif": decision.motif,
                    "message": decision.message,
                },
                status=403,
            )

        return self.render_to_response(self.get_context_data(object=self.object, decision=decision))

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        lecon = self.object
        module = lecon.chapitre.module
        inscription = kwargs.get("decision").inscription if kwargs.get("decision") else None

        avancement = None
        if inscription:
            avancement = ProgressionLecon.objects.filter(inscription=inscription, lecon=lecon).first()

        contexte.update(
            {
                "module": module,
                "inscription": inscription,
                "progression": avancement,
                "position_reprise": avancement.position_secondes if avancement else 0,
                "chapitres": module.chapitres.prefetch_related("lecons"),
                "sous_titres": lecon.video.sous_titres.all() if lecon.video else [],
                "intervalle_signal": getattr(settings, "ELEARNING_INTERVALLE_SIGNAL", 15),
            }
        )
        return contexte


class PlaybackUrlView(View):
    """Délivre une adresse de lecture éphémère.

    Le droit est revérifié ici : on ne fait jamais confiance au fait que la page
    ait été servie, car elle a pu l'être avant une révocation.
    """

    http_method_names = ["post"]

    def post(self, request, slug, lecon_slug):
        lecon = get_object_or_404(
            Lecon.objects.select_related("chapitre__module", "video"),
            chapitre__module__slug=slug,
            slug=lecon_slug,
        )

        if lecon.video is None or not lecon.video.est_prete:
            return JsonResponse({"erreur": "La vidéo n'est pas disponible."}, status=409)

        identifiant_flux = request.session.get("elearning_flux")
        if not identifiant_flux:
            identifiant_flux = uuid.uuid4().hex
            request.session["elearning_flux"] = identifiant_flux

        decision = verifier_acces(
            request.user,
            lecon,
            verifier_quota=True,
            identifiant_flux=identifiant_flux,
        )
        journaliser_acces(
            decision,
            utilisateur=request.user,
            lecon=lecon,
            request=request,
            ttl=TTL_LECTURE if decision.autorise else 0,
        )

        if not decision.autorise:
            statut = 429 if decision.motif == "refuse_quota" else 403
            return JsonResponse({"erreur": decision.message, "motif": decision.motif}, status=statut)

        return JsonResponse(
            {
                "url": lecon.video.url_lecture_signee(ttl=TTL_LECTURE),
                "expire_dans": TTL_LECTURE,
                "poster": lecon.video.poster.url if lecon.video.poster else "",
            }
        )


class ProgressionView(LoginRequiredMixin, View):
    """Signal périodique de progression. L'incrément est plafonné côté serveur."""

    http_method_names = ["post"]

    def post(self, request, slug, lecon_slug):
        lecon = get_object_or_404(
            Lecon.objects.select_related("chapitre__module"),
            chapitre__module__slug=slug,
            slug=lecon_slug,
        )
        decision = verifier_acces(request.user, lecon)
        if not decision.autorise or decision.inscription is None:
            return JsonResponse({"erreur": "Accès refusé."}, status=403)

        try:
            charge = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            charge = request.POST

        avancement = service_progression.enregistrer_progression(
            decision.inscription,
            lecon,
            position_secondes=int(charge.get("position", 0) or 0),
            delta_secondes=int(charge.get("delta", 0) or 0),
        )
        decision.inscription.refresh_from_db()

        return JsonResponse(
            {
                "pourcentage_lecon": avancement.pourcentage_vu,
                "lecon_terminee": avancement.termine,
                "pourcentage_module": decision.inscription.progression_percent,
                "module_termine": decision.inscription.statut == InscriptionModule.StatutAcces.TERMINE,
            }
        )


class FichierVideoView(View):
    """
    Sert un fichier vidéo à partir d'un jeton signé — stockage local seulement.

    En production, le fichier est servi directement par le stockage objet via
    une adresse présignée : cette vue n'est jamais sollicitée.
    """

    def get(self, request, jeton):
        stockage = stockage_video()
        if not isinstance(stockage, LocalStockageVideo):
            raise Http404

        cle = LocalStockageVideo.cle_depuis_jeton(jeton, ttl=TTL_LECTURE)
        if cle is None or not stockage.existe(cle):
            raise Http404

        reponse = FileResponse(stockage.ouvrir(cle), content_type="video/mp4")
        reponse["Accept-Ranges"] = "bytes"
        reponse["Cache-Control"] = "private, max-age=0, no-store"
        return reponse


# ══════════════════════════════════════════════
# Attestations
# ══════════════════════════════════════════════


class AttestationTelechargementView(LoginRequiredMixin, View):
    def get(self, request, pk):
        attestation = get_object_or_404(
            AttestationModule.objects.select_related("inscription__etudiant__utilisateur"),
            pk=pk,
        )
        proprietaire = attestation.inscription.etudiant.utilisateur == request.user
        if not (proprietaire or request.user.is_staff or getattr(request.user, "is_secretariat", False)):
            raise Http404
        if not attestation.fichier_pdf:
            raise Http404
        return FileResponse(
            attestation.fichier_pdf.open("rb"),
            as_attachment=True,
            filename=f"{attestation.numero}.pdf",
        )


class VerifierAttestationView(View):
    """Page publique de vérification d'une attestation par son code."""

    def get(self, request, code):
        attestation = (
            AttestationModule.objects.select_related("inscription__module", "inscription__etudiant__utilisateur")
            .filter(code_verification=code)
            .first()
        )
        return render(
            request,
            "elearning/verifier_attestation.html",
            {"attestation": attestation, "code": code},
            status=200 if attestation else 404,
        )


playback_url = csrf_protect(PlaybackUrlView.as_view())
