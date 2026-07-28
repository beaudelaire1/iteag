"""
Vues de la formation vidéo.

Règle absolue : aucune adresse de fichier n'est rendue dans un gabarit. Le
lecteur la demande par un appel authentifié distinct, et le droit est
revérifié à chaque demande (ADR-001, ADR-005).
"""

import json
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.services.audit import adresse_ip
from apps.elearning.csp import CspLectureVideoMixin
from apps.elearning.diffusion import LocalStockageVideo
from apps.elearning.models import (
    AttestationModule,
    InscriptionModule,
    Lecon,
    ModuleFormation,
    ProgressionLecon,
    RessourceLecon,
)
from apps.elearning.services import octroi
from apps.elearning.services import progression as service_progression
from apps.elearning.services.acces import journaliser_acces, verifier_acces

TTL_LECTURE = 300


def acces_integral_module(utilisateur, module) -> bool:
    """
    Ce visiteur peut-il ouvrir les leçons *hors aperçu* de ce module ?

    Sert aux sommaires, pour verrouiller visuellement ce qui le sera au clic.
    La décision n'est pas recalculée ici : elle est demandée à `verifier_acces`
    sur une leçon témoin — toutes les leçons hors aperçu d'un module partagent
    la même réponse, puisque le droit est porté par le module.
    """
    temoin = next((lecon for lecon in module.lecons() if not lecon.apercu_gratuit), None)
    if temoin is None:
        return True
    return verifier_acces(utilisateur, temoin).autorise


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


class ModuleDetailView(CspLectureVideoMixin, DetailView):
    """Fiche d'un module : sommaire, progression, appel à l'action.

    La CSP y est élargie pour l'aperçu gratuit, qui peut être hébergé chez un
    fournisseur public.
    """

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
        profil = getattr(self.request.user, "profil_etudiant", None)
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
                "lecon_apercu": module.lecons().filter(apercu_gratuit=True).first(),
                "acces_integral": acces_integral_module(self.request.user, module),
                # Un étudiant déjà inscrit demande l'accès en un clic ; seul un
                # visiteur sans dossier est invité à déposer une candidature.
                "profil_etudiant": profil,
                "acces_actif": bool(inscription and inscription.est_active()),
                "demande_en_attente": bool(inscription and inscription.statut == InscriptionModule.StatutAcces.DEMANDE),
                "motif_refus_demande": (octroi.motif_refus_demande(profil, module) if profil is not None else ""),
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
                "demandes": [i for i in inscriptions if i.statut == InscriptionModule.StatutAcces.DEMANDE],
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


class DemandeAccesModuleView(LoginRequiredMixin, View):
    """Demande d'accès à un module, par un étudiant déjà connu de l'institut.

    Un clic, aucun formulaire : l'ITEAG détient déjà l'identité et les
    coordonnées de cet étudiant. Redemander une candidature complète — ce que
    faisait le seul appel à l'action disponible ici — revenait à ignorer son
    dossier.
    """

    http_method_names = ["post"]

    def post(self, request, slug):
        module = get_object_or_404(ModuleFormation, slug=slug)
        profil = getattr(request.user, "profil_etudiant", None)
        try:
            octroi.demander(profil, module, request=request)
        except ValidationError as exception:
            messages.error(request, exception.messages[0])
        else:
            messages.success(
                request,
                f"Votre demande d'accès à « {module.titre} » a été transmise au secrétariat.",
            )
        return redirect(module.get_absolute_url())


class LeconDetailView(CspLectureVideoMixin, DetailView):
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
            module = self.object.chapitre.module
            profil = getattr(request.user, "profil_etudiant", None)
            return render(
                request,
                "elearning/acces_requis.html",
                {
                    "lecon": self.object,
                    "module": module,
                    "motif": decision.motif,
                    "message": decision.message,
                    # Un refus doit proposer la voie de sortie la plus courte.
                    # Pour un étudiant déjà inscrit, c'est une demande en un
                    # clic — pas une nouvelle candidature.
                    "profil_etudiant": profil,
                    "peut_demander": profil is not None and not octroi.motif_refus_demande(profil, module),
                    "demande_en_attente": profil is not None
                    and InscriptionModule.objects.filter(
                        etudiant=profil,
                        module=module,
                        statut=InscriptionModule.StatutAcces.DEMANDE,
                    ).exists(),
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
                "acces_integral": acces_integral_module(self.request.user, module),
                "ressources": lecon.ressources.all(),
                "sous_titres": lecon.video.sous_titres.all() if lecon.video else [],
                "intervalle_signal": getattr(settings, "ELEARNING_INTERVALLE_SIGNAL", 15),
                # Un fournisseur en cadre n'a rien à signer : son adresse peut
                # figurer dans la page, puisqu'elle ne protège rien de toute
                # façon. Le modèle garantit qu'on n'arrive ici que sur du
                # contenu public.
                "lecture_publique": (
                    lecon.video.lecture() if lecon.video and lecon.video.mode_lecture == "iframe" else None
                ),
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

        lecture = lecon.video.lecture(ttl=TTL_LECTURE, adresse_ip=adresse_ip(request))
        return JsonResponse(
            {
                "url": lecture.url,
                "mode": lecture.mode,
                "expire_dans": lecture.expire_dans,
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


class RessourceTelechargementView(View):
    """
    Remet un support pédagogique de leçon, après revérification du droit.

    La même autorité décide pour la vidéo et pour ses supports : un module
    vendu dont les PDF seraient en accès libre n'aurait de protégé que la
    vidéo. L'adresse de stockage du fichier n'apparaît donc jamais dans une
    page — seule cette vue, qui revérifie à chaque demande, sait le servir.
    """

    def get(self, request, slug, lecon_slug, pk):
        ressource = get_object_or_404(
            RessourceLecon.objects.select_related("lecon__chapitre__module"),
            pk=pk,
            lecon__chapitre__module__slug=slug,
            lecon__slug=lecon_slug,
        )
        lecon = ressource.lecon
        decision = verifier_acces(request.user, lecon)
        if not decision.autorise:
            # Le refus détaillé — et sa voie de sortie — s'affichent sur la
            # page de la leçon : on y renvoie plutôt que de dupliquer l'écran.
            return redirect(
                "elearning:lecon_detail",
                slug=lecon.chapitre.module.slug,
                lecon_slug=lecon.slug,
            )

        if not ressource.est_fichier:
            return redirect(ressource.lien_externe)

        try:
            contenu = ressource.fichier.open("rb")
        except (FileNotFoundError, ValueError) as erreur:
            raise Http404 from erreur
        return FileResponse(contenu, as_attachment=True, filename=ressource.nom_fichier)


class FichierVideoView(View):
    """
    Sert un fichier vidéo à partir d'un jeton signé — stockage local seulement.

    En production, le fichier est servi directement par le stockage objet via
    une adresse présignée : cette vue n'est jamais sollicitée.
    """

    def get(self, request, jeton):
        # Compatibilité de lecture uniquement pour les anciennes références
        # locales. Aucun écran ne permet désormais d'en créer de nouvelles.
        stockage = LocalStockageVideo()
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
