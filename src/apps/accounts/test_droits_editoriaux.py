"""Le droit d'ouvrir la médiathèque suit le rôle, et rien d'autre.

Le défaut que ces règles évitent : un bouton d'insertion d'image qui ouvre une
fenêtre vide. Le sélecteur de Wagtail parcourt et téléverse — chacune de ses
actions repose vers « /admin/images/… ». Sans le droit d'y entrer, il s'ouvre
et ne montre rien, sans message qui l'explique.
"""

import pytest
from django.contrib.auth.models import Group

from apps.accounts.models import User
from apps.accounts.services.droits_editoriaux import NOM_GROUPE, PERMISSIONS

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


def _compte(role, nom):
    return User.objects.create_user(username=nom, email=f"{nom}@iteag.org", password=MOT_DE_PASSE, role=role)


def _dans_le_groupe(compte) -> bool:
    return compte.groups.filter(name=NOM_GROUPE).exists()


class TestGroupeMediatheque:
    def test_le_groupe_porte_les_quatre_droits(self):
        """Inclusion, et non égalité stricte.

        Le premier jet exigeait l'ensemble exact et échouait : Wagtail ajoute
        de lui-même « choose_document » à un groupe qui sait accéder à son
        administration. Interdire tout ajout ferait échouer ce test sur une
        décision de Wagtail plutôt que sur un défaut d'ici. Ce qui doit être
        vrai, c'est que les quatre droits demandés sont accordés — vérifié en
        isolation avant d'assouplir l'assertion, pour ne pas confondre « le
        test était trop strict » avec « le service pose n'importe quoi ».
        """
        _compte(User.Role.SECRETARIAT, "sec_droits")
        groupe = Group.objects.get(name=NOM_GROUPE)

        accordes = {f"{p.content_type.app_label}.{p.codename}" for p in groupe.permissions.all()}
        assert {f"{app}.{code}" for app, code in PERMISSIONS} <= accordes

    def test_le_groupe_n_ouvre_pas_les_pages_du_site(self):
        """Le périmètre est la médiathèque, pas la rédaction du site public."""
        _compte(User.Role.SECRETARIAT, "sec_pages")
        groupe = Group.objects.get(name=NOM_GROUPE)

        assert not groupe.page_permissions.exists()
        assert not groupe.permissions.filter(codename__endswith="_page").exists()

    @pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.SECRETARIAT])
    def test_les_roles_qui_redigent_y_sont_rattaches(self, role):
        assert _dans_le_groupe(_compte(role, f"redige_{role}"))

    @pytest.mark.parametrize("role", [User.Role.ENSEIGNANT, User.Role.ETUDIANT])
    def test_les_autres_roles_n_y_sont_pas(self, role):
        """Un enseignant écrit des articles, pas les courriers de l'institut."""
        assert not _dans_le_groupe(_compte(role, f"hors_{role}"))

    def test_un_changement_de_role_retire_l_acces(self):
        """Un secrétariat devenu enseignant garderait sinon un droit périmé."""
        compte = _compte(User.Role.SECRETARIAT, "mute_droits")
        assert _dans_le_groupe(compte)

        compte.role = User.Role.ENSEIGNANT
        compte.save()

        assert not _dans_le_groupe(compte)

    def test_un_compte_desactive_perd_l_acces(self):
        compte = _compte(User.Role.SECRETARIAT, "inactif_droits")
        compte.is_active = False
        compte.save()

        assert not _dans_le_groupe(compte)

    def test_le_selecteur_d_image_s_ouvre_pour_le_secretariat(self, client):
        """La vérification qui compte : la route que le bloc image appelle."""
        compte = _compte(User.Role.SECRETARIAT, "chooser_droits")
        client.force_login(compte)

        reponse = client.get("/admin/images/chooser/")
        assert reponse.status_code == 200, "Sans ce droit, le bouton d'insertion d'image ouvre une fenêtre vide."

    def test_le_selecteur_reste_ferme_a_un_etudiant(self, client):
        client.force_login(_compte(User.Role.ETUDIANT, "chooser_etu"))
        assert client.get("/admin/images/chooser/").status_code != 200
