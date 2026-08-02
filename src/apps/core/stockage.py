"""Stockage des fichiers statiques de production.

Le manifeste est ce qui fait échouer bruyamment une référence cassée (ADR-004) :
en production, tout `{% static %}` doit désigner un fichier réellement collecté,
sinon la page lève une erreur au lieu de servir un lien mort. C'est voulu, et
cela doit le rester.

Une bibliothèque tierce contredit pourtant cette règle sans être fautive.
`jazzmin`, le thème de l'administration Django, écrit dans son gabarit :

    data-theme-base="{% static 'vendor/bootswatch' %}"

`vendor/bootswatch` est un **répertoire**. Son script y ajoute côté client le
nom du thème choisi. Un répertoire n'entre jamais dans un manifeste, qui ne
recense que des fichiers : la référence était donc introuvable, et **toutes**
les pages de `/django-admin/` répondaient 500 en production — jamais en
développement, où aucun manifeste n'est consulté.

Plutôt que de désarmer le manifeste pour tout le projet — ce qui rendrait
silencieuse la prochaine référence réellement cassée —, les chemins tolérés
sont énumérés ici, un par un, avec leur raison. Comme la dette d'architecture,
cette liste ne devrait que diminuer.
"""

from whitenoise.storage import CompressedManifestStaticFilesStorage

# Chemins que le manifeste ne peut pas recenser, et qui ne sont pas des défauts.
CHEMINS_HORS_MANIFESTE = frozenset(
    {
        # jazzmin ≥ 3.0 — base des thèmes bootswatch, complétée côté client.
        "vendor/bootswatch",
    }
)


class StockageStatiquesITEAG(CompressedManifestStaticFilesStorage):
    """Manifeste strict, sauf pour les chemins déclarés ci-dessus."""

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            if name in CHEMINS_HORS_MANIFESTE:
                # Servi tel quel : WhiteNoise conserve les fichiers d'origine à
                # côté de leurs copies empreintes. Le répertoire reste donc
                # atteignable, sans cache de longue durée — ce qui est sans
                # conséquence pour une poignée de feuilles de l'administration.
                return name
            raise
