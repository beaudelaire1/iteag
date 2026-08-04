"""
Ce qu'un destinataire doit trouver dans un courriel de la plateforme.

Ces messages ne sont pas des avis de service : ils sortent au nom d'un
institut, et ce sont souvent les seuls écrits que l'étudiant reçoit de lui.
Trois défauts constatés sont verrouillés ici :

1. un objet préfixé « [ITEAG] » — les crochets font message automatisé, et
   certains filtres les pénalisent ;
2. aucune salutation : le courriel s'ouvrait sur un titre, sans s'adresser à
   personne ;
3. un corps interchangeable — « une information est disponible » — qui oblige
   à se connecter pour découvrir de quoi il retournait.
"""

import pytest
from django.core import mail

from apps.accounts.models import User
from apps.core.models import Notification
from apps.core.services.emails import envoyer_notification_email
from apps.core.services.notifications import notifier

pytestmark = pytest.mark.django_db


@pytest.fixture
def etudiante(db):
    return User.objects.create_user(
        username="lea_courriel",
        email="lea@iteag.org",
        password="motdepasse-long-12",
        first_name="Léa",
        last_name="Abaul",
        role=User.Role.ETUDIANT,
    )


def _dernier_html() -> str:
    return mail.outbox[-1].alternatives[0][0]


def test_l_objet_ne_porte_plus_de_crochets(etudiante, django_capture_on_commit_callbacks):
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        notifier(etudiante, "Note publiée — Herméneutique")

    assert mail.outbox[0].subject == "ITEAG - Note publiée — Herméneutique"


def test_le_courriel_salue_le_destinataire_par_son_prenom(etudiante, django_capture_on_commit_callbacks):
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        notifier(etudiante, "Note publiée", message="Votre note est disponible.")

    assert "Bonjour Léa," in _dernier_html()


def test_un_compte_sans_prenom_reste_salue_correctement(db, django_capture_on_commit_callbacks):
    """« Bonjour , » serait pire que pas de prénom du tout."""
    anonyme = User.objects.create_user(
        username="sans_prenom", email="sp@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
    )
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        notifier(anonyme, "Information")

    html = _dernier_html()
    assert "Bonjour," in html
    assert "Bonjour ," not in html


def test_les_precisions_figurent_dans_le_courriel(etudiante, django_capture_on_commit_callbacks):
    """Savoir de quoi il retourne sans avoir à se connecter."""
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        notifier(
            etudiante,
            "Note publiée",
            message="Votre note vient d'être publiée.",
            details=[
                {"libelle": "Cours", "valeur": "Théologie propre et christologie"},
                {"libelle": "Session", "valeur": "Session de Juillet 2026"},
            ],
        )

    html = _dernier_html()
    assert "Théologie propre et christologie" in html
    assert "Session de Juillet 2026" in html


def test_le_type_de_notification_titre_le_courriel(etudiante, django_capture_on_commit_callbacks):
    """L'en-tête annonce la nature du message plutôt qu'un « Information » constant."""
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        notifier(etudiante, "Note publiée", type_notification=Notification.Type.NOTE_PUBLIEE)

    assert "Note publiée" in _dernier_html()


def test_le_courriel_se_termine_par_une_signature(etudiante, django_capture_on_commit_callbacks):
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        notifier(etudiante, "Information")

    html = _dernier_html()
    assert "Bien cordialement" in html
    assert "Le secrétariat de l'ITEAG" in html


def test_le_courriel_reste_lisible_sans_precisions():
    """La plupart des points d'appel n'en fournissent pas : le gabarit doit tenir sans."""
    mail.outbox.clear()
    assert envoyer_notification_email(
        sujet="Information",
        titre="Information",
        message="Un message simple.",
        destinataires=["a@b.org"],
        differe=False,
    )
    html = _dernier_html()
    assert "Un message simple." in html
    assert "Bonjour," in html


def test_l_apercu_reprend_le_message_et_non_le_titre():
    """L'aperçu de la boîte de réception doit apporter autre chose que l'objet."""
    mail.outbox.clear()
    envoyer_notification_email(
        sujet="Note publiée",
        titre="Note publiée",
        message="Votre note pour le cours « Herméneutique » vient d'être publiée.",
        destinataires=["a@b.org"],
        differe=False,
    )
    # Sans apostrophe : le rendu HTML les échappe en « &#x27; ».
    html = _dernier_html()
    assert "Herméneutique" in html, "Le message doit apparaître, et pas seulement le titre"
    assert "pour le cours" in html


# ──────────────────────────────────────────────
# Les règles tenues par le socle
# ──────────────────────────────────────────────


def test_aucun_message_ne_reste_interchangeable():
    """
    Garde-fou de style, sur le code source plutôt que sur un rendu.

    Les formules ci-dessous ont toutes été employées telles quelles : elles
    annoncent qu'il s'est passé quelque chose sans dire quoi, et obligent à se
    connecter pour l'apprendre. Leur réapparition est un retour en arrière.
    """
    import pathlib
    import re

    bannies = [
        "est disponible dans votre espace.",
        "sont disponibles.",
        "Consultez les informations",
    ]
    fautifs = []
    for fichier in pathlib.Path("apps").rglob("*.py"):
        chemin = str(fichier).replace("\\", "/")
        if "/migrations/" in chemin or "/test" in chemin:
            continue
        texte = fichier.read_text(encoding="utf-8")
        if not re.search(r"notifier(?:_plusieurs)?\(", texte):
            continue
        for formule in bannies:
            if formule in texte:
                fautifs.append(f"{chemin} : « {formule} »")

    assert not fautifs, "Messages trop génériques :\n  " + "\n  ".join(fautifs)


def test_la_note_chiffree_ne_circule_pas_par_courriel(etudiante, django_capture_on_commit_callbacks):
    """Un résultat se lit derrière une authentification, pas dans une boîte de réception."""
    from apps.core.services.notifications import notifier as notifier_note

    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        notifier_note(
            etudiante,
            "Note publiée — Herméneutique",
            message="Votre note pour le cours « Herméneutique » vient d'être publiée.",
            details=[{"libelle": "Cours", "valeur": "Herméneutique"}],
        )

    html = _dernier_html()
    assert "Herméneutique" in html
    assert "/20" not in html, "Aucune note chiffrée ne doit figurer dans le courriel"
