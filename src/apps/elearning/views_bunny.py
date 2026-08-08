"""Métadonnées Bunny destinées au lecteur propriétaire ITEAG."""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.services.audit import adresse_ip
from apps.elearning.bunny_metadata import chapitres_video
from apps.elearning.models import Lecon
from apps.elearning.services.acces import verifier_acces

TTL_APERCU_SECONDES = 300


class VideoMetadataView(View):
    """Retourne uniquement les métadonnées nécessaires à l'interface vidéo.

    Comme pour l'URL de lecture, le droit est revérifié à chaque appel. Le
    navigateur reçoit un préfixe de sprites signé et temporaire ; la clé API
    Bunny et la clé de signature ne quittent jamais le serveur.
    """

    http_method_names = ["get"]

    def get(self, request, slug, lecon_slug):
        lecon = get_object_or_404(
            Lecon.objects.select_related("chapitre__module", "video"),
            chapitre__module__slug=slug,
            slug=lecon_slug,
        )
        decision = verifier_acces(request.user, lecon)
        if not decision.autorise:
            return JsonResponse({"erreur": decision.message}, status=403)

        video = lecon.video
        if video is None or video.fournisseur != "bunny" or not video.est_prete:
            return JsonResponse({"chapitres": [], "seek_url_prefix": "", "intervalle_apercu": 2})

        lecture = video.lecture(ttl=TTL_APERCU_SECONDES, adresse_ip=adresse_ip(request))
        # Le jeton Bunny ouvre le répertoire de la vidéo. Le manifeste HLS et
        # les sprites seek héritent donc de la même autorisation éphémère.
        repertoire_signe = lecture.url.rsplit("/", 1)[0] + "/"
        intervalle = 1 if 0 < video.duree_secondes < 10 else 2

        return JsonResponse(
            {
                "chapitres": chapitres_video(video.cle_stockage),
                "seek_url_prefix": f"{repertoire_signe}seek/",
                "intervalle_apercu": intervalle,
            }
        )
