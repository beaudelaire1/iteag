"""
Garde-fou commun aux suppressions du portail administratif.

Le défaut : les écrans de suppression demandaient « Êtes-vous sûr ? » sans
jamais dire de quoi. Or plusieurs clés étrangères sont en cascade. Supprimer un
compte utilisateur emportait le profil étudiant, et avec lui ses inscriptions,
ses notes, ses crédits ECTS et l'historique de ses paiements — en deux clics,
sans le moindre avertissement. Supprimer une session académique emportait tous
ses cours programmés et tout ce qui s'y rattachait.

Deux mécanismes, à ne pas confondre :

- **le refus** : certaines suppressions n'ont pas lieu d'être, parce qu'une
  désactivation fait le même travail sans perdre l'historique. Elles sont
  bloquées, avec le geste de remplacement énoncé ;
- **l'inventaire** : pour celles qui restent, l'écran de confirmation énumère
  ce qui disparaîtra, compté par Django lui-même plutôt que deviné.
"""

from django.contrib import messages
from django.db.models.deletion import Collector, ProtectedError
from django.shortcuts import redirect


def inventaire_des_pertes(objet) -> list[tuple[str, int]]:
    """Ce que la suppression emporterait, par type d'objet.

    Le calcul est délégué au collecteur de Django : c'est lui qui décide en
    réalité, et toute autre estimation finirait par diverger de son verdict.
    """
    collecteur = Collector(using=objet._state.db)
    try:
        collecteur.collect([objet])
    except ProtectedError:
        # Une clé en PROTECT rend la suppression impossible : il n'y a donc
        # aucune perte à inventorier. C'est « raison_de_bloquer » qui l'explique.
        return []

    pertes: dict[str, int] = {}
    for modele, instances in collecteur.data.items():
        nombre = len(instances)
        if modele is type(objet):
            nombre -= 1  # l'objet lui-même n'est pas un dommage collatéral
        if nombre > 0:
            pertes[modele._meta.verbose_name_plural.capitalize()] = nombre
    return sorted(pertes.items(), key=lambda ligne: -ligne[1])


class SuppressionProtegee:
    """À combiner avec une « DeleteView ».

    Une sous-classe déclare `url_retour`, `libelle()` et, si la suppression
    peut être illégitime, `raison_de_bloquer()`.
    """

    url_retour = "administration:dashboard"

    def libelle(self) -> str:
        return f"« {self.object} »"

    def raison_de_bloquer(self) -> str:
        """Message expliquant pourquoi refuser — vide si la suppression est licite."""
        return ""

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.setdefault("object_label", self.libelle())
        contexte["pertes"] = inventaire_des_pertes(self.object)
        contexte["raison_de_bloquer"] = self.raison_de_bloquer()
        contexte["cancel_url"] = self.retour()
        return contexte

    def retour(self) -> str:
        from django.urls import reverse

        return reverse(self.url_retour)

    def form_valid(self, form):
        raison = self.raison_de_bloquer()
        if raison:
            messages.error(self.request, raison)
            return redirect(self.retour())
        messages.success(self.request, f"Suppression effectuée : {self.libelle()}.")
        return super().form_valid(form)
