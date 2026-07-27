"""
Écran de profil — commun aux quatre rôles.

Il n'existait aucune façon, pour qui que ce soit, de corriger son adresse ou de
changer son mot de passe sans passer par l'administration. Ces cas fixent ce
que chacun peut faire sur son propre compte, et ce qu'il ne peut pas.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

MOT_DE_PASSE = "MotDePasseSolide!2026"


def _compte(role, username="titulaire", **extra):
    return User.objects.create_user(
        username=username,
        email=f"{username}@iteag.org",
        password=MOT_DE_PASSE,
        first_name="Jean",
        last_name="Dupont",
        role=role,
        **extra,
    )


@pytest.mark.parametrize(
    "role",
    [User.Role.ETUDIANT, User.Role.ENSEIGNANT, User.Role.SECRETARIAT, User.Role.ADMIN],
)
def test_chaque_role_atteint_son_profil(client, db, role):
    """La page est la même pour tous : c'est le compte qui est édité, pas le rôle."""
    client.force_login(_compte(role))
    reponse = client.get(reverse("accounts:profil"))
    assert reponse.status_code == 200
    assert "Mon profil" in reponse.content.decode()


def test_visiteur_renvoye_vers_la_connexion(client, db):
    reponse = client.get(reverse("accounts:profil"))
    assert reponse.status_code == 302
    assert "/connexion/" in reponse["Location"]


def test_coordonnees_enregistrees(client, db):
    utilisateur = _compte(User.Role.ETUDIANT)
    client.force_login(utilisateur)

    reponse = client.post(
        reverse("accounts:profil"),
        {
            "first_name": "Jean-Marc",
            "last_name": "Dupont",
            "email": "jm.dupont@iteag.org",
            "phone": "0690123456",
            "adresse": "12 rue des Flamboyants",
            "complement_adresse": "",
            "code_postal": "97139",
            "ville": "Les Abymes",
            "pays": "Guadeloupe",
        },
    )
    assert reponse.status_code == 302

    utilisateur.refresh_from_db()
    assert utilisateur.first_name == "Jean-Marc"
    assert utilisateur.email == "jm.dupont@iteag.org"
    assert utilisateur.phone == "0690123456"
    assert utilisateur.adresse_postale == "12 rue des Flamboyants, 97139 Les Abymes"


def test_adresse_deja_prise_refusee(client, db):
    """L'adresse sert à se connecter : deux comptes ne peuvent pas la partager."""
    _compte(User.Role.ETUDIANT, username="autre")
    utilisateur = _compte(User.Role.ETUDIANT)
    client.force_login(utilisateur)

    reponse = client.post(
        reverse("accounts:profil"),
        {
            "first_name": "Jean",
            "last_name": "Dupont",
            "email": "autre@iteag.org",
            "phone": "",
            "adresse": "",
            "complement_adresse": "",
            "code_postal": "",
            "ville": "",
            "pays": "Guadeloupe",
        },
    )
    assert reponse.status_code == 200
    assert "déjà utilisée" in reponse.content.decode()

    utilisateur.refresh_from_db()
    assert utilisateur.email == "titulaire@iteag.org"


def test_le_role_n_est_pas_modifiable_depuis_le_profil(client, db):
    """Un compte corrige son adresse, il ne se promeut pas."""
    utilisateur = _compte(User.Role.ETUDIANT)
    client.force_login(utilisateur)

    client.post(
        reverse("accounts:profil"),
        {
            "first_name": "Jean",
            "last_name": "Dupont",
            "email": "titulaire@iteag.org",
            "phone": "",
            "adresse": "",
            "complement_adresse": "",
            "code_postal": "",
            "ville": "",
            "pays": "Guadeloupe",
            "role": User.Role.ADMIN,
            "is_superuser": True,
            "is_staff": True,
        },
    )

    utilisateur.refresh_from_db()
    assert utilisateur.role == User.Role.ETUDIANT
    assert utilisateur.is_superuser is False
    assert utilisateur.is_staff is False


def test_changement_de_mot_de_passe(client, db):
    utilisateur = _compte(User.Role.ENSEIGNANT)
    client.force_login(utilisateur)

    reponse = client.post(
        reverse("accounts:profil"),
        {
            "changer_mot_de_passe": "1",
            "old_password": MOT_DE_PASSE,
            "new_password1": "AutreMotDePasse!2026",
            "new_password2": "AutreMotDePasse!2026",
        },
    )
    assert reponse.status_code == 302

    utilisateur.refresh_from_db()
    assert utilisateur.check_password("AutreMotDePasse!2026")

    # La session survit au changement : sans cela, l'auteur du changement se
    # retrouvait déconnecté au clic suivant, sans comprendre pourquoi.
    assert client.get(reverse("accounts:profil")).status_code == 200


def test_mot_de_passe_actuel_faux_refuse(client, db):
    utilisateur = _compte(User.Role.ENSEIGNANT)
    client.force_login(utilisateur)

    reponse = client.post(
        reverse("accounts:profil"),
        {
            "changer_mot_de_passe": "1",
            "old_password": "PasLeBon!2026",
            "new_password1": "AutreMotDePasse!2026",
            "new_password2": "AutreMotDePasse!2026",
        },
    )
    assert reponse.status_code == 200

    utilisateur.refresh_from_db()
    assert utilisateur.check_password(MOT_DE_PASSE)


def test_initiales_de_repli(db):
    """Sans photo, l'espace privé affiche des initiales plutôt qu'un vide."""
    assert _compte(User.Role.ETUDIANT).initiales == "JD"
