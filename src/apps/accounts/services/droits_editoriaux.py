"""Les droits Wagtail qu'exige la rédaction, accordés par le rôle.

**Pourquoi passer par un groupe Wagtail plutôt que de le contourner.** Le
sélecteur d'image de Wagtail n'est pas un formulaire : il parcourt, cherche,
pagine et téléverse, et chacune de ces actions repose vers « /admin/images/… ».
Le servir depuis une route de portail — comme le fait « LienExterneEditeurView »
pour le dialogue de lien, qui n'a lui aucune navigation — donnerait un premier
écran qui s'ouvre et un deuxième clic qui redirige vers la connexion.

Reproduire le sélecteur reviendrait à maintenir une interface de navigation
parallèle, alignée sur le protocole de modale de Wagtail, à refaire à chaque
montée de version. Lui accorder ses droits le fait fonctionner nativement, et
il n'y a rien à maintenir.

**Ce n'est pas le RBAC écarté.** Ce qui a été refusé, c'est une visibilité par
document et des listes de rôles autorisés — un second système de permissions en
concurrence avec les mixins. Ici, aucun droit n'est attaché à un document : on
donne à deux rôles la capacité d'ouvrir une médiathèque. Wagtail est bâti sur
ces groupes ; s'en priver n'annule pas le besoin, cela oblige à le réimplémenter
moins bien.

**Ce que le groupe n'ouvre pas.** « access_admin » laisse entrer dans
l'administration Wagtail, mais son menu est piloté par les permissions : sans
droit sur les pages, les documents ou les réglages, il ne reste que les images.
"""

from django.contrib.auth.models import Group, Permission

NOM_GROUPE = "Rédaction — médiathèque"

# (app_label, codename) — nommés en clair pour que le jour où l'un disparaît
# d'une version de Wagtail, l'erreur cite le droit manquant.
PERMISSIONS = (
    ("wagtailadmin", "access_admin"),
    ("wagtailimages", "add_image"),
    ("wagtailimages", "change_image"),
    ("wagtailimages", "choose_image"),
)

# Les rôles qui rédigent des contenus illustrés.
ROLES_CONCERNES = ("admin", "secretariat")


def assurer_le_groupe(modele_groupe=Group, modele_permission=Permission) -> Group:
    """Crée le groupe s'il manque et lui pose ses permissions.

    Les modèles sont injectables : une migration de données doit travailler sur
    l'état historique du schéma, pas sur les classes importées.
    """
    groupe, _ = modele_groupe.objects.get_or_create(name=NOM_GROUPE)
    for app_label, codename in PERMISSIONS:
        droit = modele_permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
        # Un droit absent n'interrompt pas l'installation : Wagtail crée ses
        # permissions par migration, et l'ordre entre applications n'est pas
        # garanti. Ce qui manque sera reposé au prochain passage.
        if droit is not None:
            groupe.permissions.add(droit)
    return groupe


def synchroniser(utilisateur, modele_groupe=Group, modele_permission=Permission) -> None:
    """Rattache ou détache le compte selon son rôle.

    Le détachement compte autant que l'ajout : un secrétariat devenu enseignant
    garderait sinon un accès à la médiathèque que son rôle ne justifie plus.
    """
    groupe = assurer_le_groupe(modele_groupe, modele_permission)
    if getattr(utilisateur, "role", None) in ROLES_CONCERNES and utilisateur.is_active:
        utilisateur.groups.add(groupe)
    else:
        utilisateur.groups.remove(groupe)
