"""
Pilotage des accès à la formation vidéo — secrétariat et administration.

Le droit d'accès est une donnée administrable : ces vues en sont l'interface
métier, afin que l'ouverture, la prolongation et la révocation ne demandent
jamais l'intervention d'un développeur.
"""

import csv
from datetime import timedelta

from django.contrib import messages
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.academics.models import ProfilEtudiant
from apps.core.mixins import StaffRoleRequiredMixin
from apps.core.services.audit import journaliser
from apps.elearning.models import (
    InscriptionModule,
    JournalAccesVideo,
    ModuleFormation,
    ProgressionLecon,
)
from apps.elearning.services import octroi


def _cellule_csv(valeur):
    """Neutralise les cellules interprétables comme formules par les tableurs."""
    texte = str(valeur or "")
    return f"'{texte}" if texte.lstrip().startswith(("=", "+", "-", "@")) else texte


class AccesListView(StaffRoleRequiredMixin, ListView):
    """Qui a accès à quoi — avec les leviers pour le changer."""

    template_name = "administration/elearning/acces.html"
    context_object_name = "acces"
    paginate_by = 40

    def get_queryset(self):
        requete = InscriptionModule.objects.select_related(
            "module", "etudiant__utilisateur", "etudiant__parcours", "etudiant__promotion"
        )

        module = self.request.GET.get("module")
        statut = self.request.GET.get("statut")
        promotion = self.request.GET.get("promotion")
        recherche = self.request.GET.get("q", "").strip()

        if module:
            requete = requete.filter(module__slug=module)
        if statut:
            requete = requete.filter(statut=statut)
        if promotion:
            requete = requete.filter(etudiant__promotion_id=promotion)
        if recherche:
            requete = requete.filter(
                Q(etudiant__utilisateur__last_name__icontains=recherche)
                | Q(etudiant__utilisateur__first_name__icontains=recherche)
                | Q(etudiant__numero_etudiant__icontains=recherche)
                | Q(module__titre__icontains=recherche)
            )
        return requete.order_by("etudiant__utilisateur__last_name", "module__titre")

    def get_context_data(self, **kwargs):
        from apps.academics.models import Promotion

        contexte = super().get_context_data(**kwargs)
        contexte.update(
            {
                "modules": ModuleFormation.objects.order_by("titre"),
                "promotions": Promotion.objects.filter(actif=True).order_by("-annee_debut"),
                "statuts": InscriptionModule.StatutAcces.choices,
                "module_courant": self.request.GET.get("module", ""),
                "statut_courant": self.request.GET.get("statut", ""),
                "promotion_courante": self.request.GET.get("promotion", ""),
                "recherche": self.request.GET.get("q", ""),
                "compteurs": {
                    valeur: InscriptionModule.objects.filter(statut=valeur).count()
                    for valeur, _ in InscriptionModule.StatutAcces.choices
                },
                # Les demandes attendent une décision : elles sont mises en tête
                # d'écran plutôt que noyées parmi les autres statuts.
                "demandes_en_attente": InscriptionModule.objects.filter(
                    statut=InscriptionModule.StatutAcces.DEMANDE
                ).count(),
            }
        )
        return contexte


class AccesActionView(StaffRoleRequiredMixin, View):
    """Action de masse sur une sélection d'accès."""

    http_method_names = ["post"]

    def post(self, request):
        identifiants = request.POST.getlist("acces")
        action = request.POST.get("action")
        retour = request.POST.get("retour") or reverse("administration:acces")

        if not identifiants:
            messages.warning(request, "Sélectionnez au moins un accès.")
            return redirect(retour)

        selection = InscriptionModule.objects.filter(pk__in=identifiants)
        nombre = selection.count()

        if action == "accorder":
            # Une demande accordée devient un accès ordinaire : c'est « octroyer »
            # qui décide, afin qu'un octroi manuel et une demande acceptée
            # produisent exactement le même objet.
            try:
                jours = int(request.POST.get("jours") or 0) or None
            except (TypeError, ValueError):
                jours = None
            for inscription in selection.select_related("etudiant", "module"):
                octroi.octroyer(
                    inscription.etudiant,
                    inscription.module,
                    source=InscriptionModule.SourceAcces.OCTROI_MANUEL,
                    duree_jours=jours,
                    octroye_par=request.user,
                )
            messages.success(request, f"{nombre} demande(s) accordée(s).")

        elif action == "refuser":
            motif = request.POST.get("motif", "").strip()
            if not motif:
                messages.error(request, "Précisez le motif du refus.")
                return redirect(retour)
            refusees = 0
            for inscription in selection.select_related("etudiant__utilisateur", "module"):
                if inscription.statut == InscriptionModule.StatutAcces.DEMANDE:
                    octroi.refuser_demande(inscription, motif=motif, par=request.user)
                    refusees += 1
            messages.success(request, f"{refusees} demande(s) refusée(s).")

        elif action == "suspendre":
            for inscription in selection.select_related("etudiant__utilisateur", "module"):
                octroi.suspendre(inscription, par=request.user)
            messages.success(request, f"{nombre} accès suspendu(s).")

        elif action == "reactiver":
            for inscription in selection.select_related("etudiant__utilisateur", "module"):
                octroi.reactiver(inscription, par=request.user)
            messages.success(request, f"{nombre} accès réactivé(s).")

        elif action == "revoquer":
            motif = request.POST.get("motif", "Révocation depuis le portail")
            for inscription in selection:
                octroi.revoquer(inscription, motif=motif, par=request.user)
            messages.success(request, f"{nombre} accès révoqué(s).")

        elif action == "prolonger":
            try:
                jours = max(1, min(int(request.POST.get("jours", 90)), 3650))
            except (TypeError, ValueError):
                jours = 90
            for inscription in selection:
                octroi.prolonger(inscription, jours=jours, par=request.user)
            messages.success(request, f"{nombre} accès prolongé(s) de {jours} jours.")

        else:
            messages.error(request, "Action inconnue.")

        return redirect(retour)


class OctroiEnMasseView(StaffRoleRequiredMixin, View):
    """Ouvre un module à toute une promotion, en une fois."""

    http_method_names = ["post"]

    def post(self, request):
        module = get_object_or_404(ModuleFormation, pk=request.POST.get("module"))
        promotion_id = request.POST.get("promotion")
        try:
            duree = int(request.POST.get("duree_jours") or 0) or None
        except (TypeError, ValueError):
            duree = None

        etudiants = ProfilEtudiant.objects.filter(promotion_id=promotion_id).exclude(
            statut_inscription__in=[
                ProfilEtudiant.StatutInscription.INACTIF,
                ProfilEtudiant.StatutInscription.SUSPENDU,
            ]
        )

        ouverts = sum(
            1
            for profil in etudiants
            if octroi.octroyer(
                profil,
                module,
                source=InscriptionModule.SourceAcces.OCTROI_MANUEL,
                duree_jours=duree,
                octroye_par=request.user,
            )
        )
        messages.success(request, f"« {module.titre} » ouvert à {ouverts} étudiant(s).")
        return redirect(reverse("administration:acces"))


class StatistiquesVideoView(StaffRoleRequiredMixin, TemplateView):
    """Ce que la plateforme vidéo produit réellement."""

    template_name = "administration/elearning/statistiques.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)

        inscriptions = InscriptionModule.objects.all()
        secondes_vues = ProgressionLecon.objects.aggregate(total=Sum("temps_visionnage_cumule"))["total"] or 0

        modules = (
            ModuleFormation.objects.annotate(
                nb_inscrits=Count("inscriptions", distinct=True),
                nb_termines=Count(
                    "inscriptions",
                    filter=Q(inscriptions__statut=InscriptionModule.StatutAcces.TERMINE),
                    distinct=True,
                ),
                avancement=Avg("inscriptions__progression_percent"),
            )
            .filter(nb_inscrits__gt=0)
            .order_by("-nb_inscrits")
        )

        contexte.update(
            {
                "total_acces": inscriptions.count(),
                "actifs": inscriptions.filter(statut=InscriptionModule.StatutAcces.ACTIF).count(),
                "termines": inscriptions.filter(statut=InscriptionModule.StatutAcces.TERMINE).count(),
                "heures_vues": round(secondes_vues / 3600, 1),
                "attestations": sum(1 for i in inscriptions if hasattr(i, "attestation")),
                "modules": modules,
                "modules_publies": ModuleFormation.objects.filter(
                    statut=ModuleFormation.StatutPublication.PUBLIE
                ).count(),
            }
        )
        return contexte


class JournalAccesView(StaffRoleRequiredMixin, ListView):
    """Journal des demandes de lecture, et détection de comptes partagés."""

    template_name = "administration/elearning/journal.html"
    context_object_name = "entrees"
    paginate_by = 50

    def get_queryset(self):
        requete = JournalAccesVideo.objects.select_related("utilisateur", "lecon__chapitre__module")
        resultat = self.request.GET.get("resultat")
        if resultat:
            requete = requete.filter(resultat=resultat)
        return requete

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        depuis = timezone.now() - timedelta(hours=24)

        # Un même compte vu depuis de nombreuses adresses en 24 h : indice de partage.
        seuil = 4
        suspects = (
            JournalAccesVideo.objects.filter(created_at__gte=depuis, utilisateur__isnull=False)
            .values("utilisateur", "utilisateur__first_name", "utilisateur__last_name", "utilisateur__email")
            .annotate(adresses=Count("adresse_ip", distinct=True), lectures=Count("id"))
            .filter(adresses__gte=seuil)
            .order_by("-adresses")
        )

        contexte.update(
            {
                "resultats": JournalAccesVideo.Resultat.choices,
                "resultat_courant": self.request.GET.get("resultat", ""),
                "suspects": suspects,
                "seuil_adresses": seuil,
                "refus_24h": JournalAccesVideo.objects.filter(created_at__gte=depuis)
                .exclude(resultat=JournalAccesVideo.Resultat.AUTORISE)
                .count(),
            }
        )
        return contexte


class ExportAccesView(StaffRoleRequiredMixin, View):
    """Export CSV des accès, pour reprise en tableur."""

    def get(self, request):
        reponse = HttpResponse(content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = 'attachment; filename="acces-modules.csv"'

        redacteur = csv.writer(reponse)
        redacteur.writerow(
            [
                "Numéro étudiant",
                "Nom",
                "Prénom",
                "Email",
                "Parcours",
                "Promotion",
                "Module",
                "Statut",
                "Source",
                "Progression (%)",
                "Début d'accès",
                "Fin d'accès",
            ]
        )

        acces = InscriptionModule.objects.select_related(
            "module", "etudiant__utilisateur", "etudiant__parcours", "etudiant__promotion"
        ).order_by("etudiant__utilisateur__last_name")

        for inscription in acces:
            utilisateur = inscription.etudiant.utilisateur
            redacteur.writerow(
                [
                    _cellule_csv(inscription.etudiant.numero_etudiant),
                    _cellule_csv(utilisateur.last_name),
                    _cellule_csv(utilisateur.first_name),
                    _cellule_csv(utilisateur.email),
                    _cellule_csv(inscription.etudiant.parcours),
                    _cellule_csv(inscription.etudiant.promotion),
                    _cellule_csv(inscription.module.titre),
                    inscription.get_statut_display(),
                    inscription.get_source_display(),
                    inscription.progression_percent,
                    inscription.date_debut_acces.strftime("%d/%m/%Y") if inscription.date_debut_acces else "",
                    inscription.date_fin_acces.strftime("%d/%m/%Y") if inscription.date_fin_acces else "",
                ]
            )

        journaliser("export", request=request, objet_type="InscriptionModule", nombre=acces.count())
        return reponse
