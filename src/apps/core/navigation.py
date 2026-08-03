"""Navigation publique — déclarée une fois, rendue deux fois.

La barre du site et le menu mobile listaient les mêmes entrées, écrites deux
fois dans le même gabarit. Elles avaient déjà divergé : « Bibliothèque » était
une rubrique de premier niveau en haut de page, et une sous-entrée d'un groupe
« Ressources » sur mobile. Toute entrée ajoutée d'un côté manquait de l'autre,
et rien ne le signalait.

Les rubriques sont donc décrites ici, en un seul endroit, et les deux rendus
les parcourent. C'est aussi ce qui permet de dire où l'on se trouve : chaque
rubrique connaît les chemins qui lui appartiennent, ce sont ceux de ses propres
liens. Rien à tenir à jour en double, donc rien à oublier.
"""

from dataclasses import dataclass, replace

from django.urls import reverse


@dataclass(frozen=True)
class Entree:
    """Une destination, sous l'intitulé d'une rubrique."""

    libelle: str
    url: str
    detail: str = ""


@dataclass(frozen=True)
class Rubrique:
    """Un intitulé de premier niveau. Toujours un lien, jamais un simple déclencheur."""

    cle: str
    libelle: str
    url: str
    entrees: tuple[Entree, ...] = ()
    active: bool = False

    @property
    def chemins(self) -> tuple[str, ...]:
        """Chemins que la rubrique revendique : le sien et ceux de ses entrées.

        « / » est écarté : il préfixe tout, et rendrait la rubrique active
        partout.
        """
        candidats = (self.url, *(entree.url for entree in self.entrees))
        return tuple(dict.fromkeys(chemin for chemin in candidats if chemin != "/"))


def rubriques() -> list[Rubrique]:
    """Les rubriques publiques, dans l'ordre de la barre.

    Les adresses sont résolues à l'appel, pas à l'import : un gabarit d'erreur
    rendu avant le chargement complet des routes ne doit pas échouer ici.
    """
    return [
        Rubrique(
            cle="formations",
            libelle="Formations",
            url=reverse("formations:parcours_list"),
            entrees=(
                Entree(
                    libelle="Parcours et cours",
                    url=reverse("formations:parcours_list"),
                    detail="Diplômant, Bachelor FLTE, libre, ITEAG Pro",
                ),
                Entree(
                    libelle="E-Learning",
                    url=reverse("elearning:catalogue"),
                    detail="Modules à suivre à votre rythme",
                ),
                Entree(libelle="Équipe professorale", url=reverse("formations:professeur_list")),
            ),
        ),
        Rubrique(
            cle="institut",
            libelle="L'institut",
            # Pages éditoriales Wagtail : leur adresse est leur identité
            # publique, elle ne se dérive d'aucune route nommée.
            url="/presentation/",
            entrees=(
                Entree(libelle="Découvrir l'ITEAG", url="/presentation/"),
                Entree(libelle="Actualités", url="/actualites/"),
                # Les travaux des enseignants-chercheurs. Sans cette entrée,
                # les articles publiés existaient à leur adresse sans qu'aucun
                # chemin n'y mène : un visiteur ne les trouvait jamais.
                Entree(libelle="Articles", url=reverse("website:articles")),
                Entree(libelle="Nous contacter", url="/contact/"),
            ),
        ),
        Rubrique(
            cle="bibliotheque",
            libelle="Bibliothèque",
            url=reverse("library:catalogue"),
        ),
        Rubrique(
            cle="boutique",
            libelle="Boutique",
            url=reverse("commerce:catalogue"),
        ),
    ]


def rubriques_pour(chemin: str) -> list[Rubrique]:
    """Les rubriques, celle du chemin courant marquée active.

    Au plus une rubrique est active : deux intitulés soulignés diraient deux
    endroits à la fois. En cas de recouvrement, le chemin le plus précis gagne.
    """
    liste = rubriques()
    meilleure, longueur = None, 0
    for rubrique in liste:
        for revendique in rubrique.chemins:
            if chemin.startswith(revendique) and len(revendique) > longueur:
                meilleure, longueur = rubrique.cle, len(revendique)
    return [replace(rubrique, active=rubrique.cle == meilleure) for rubrique in liste]
