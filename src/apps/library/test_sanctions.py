from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import User
from apps.formations.models import Discipline
from apps.library import services
from apps.library.formulaires import EmpruntForm
from apps.library.models import Emprunt, NoticeBibliographique, SuspensionBibliotheque

pytestmark = pytest.mark.django_db


@pytest.fixture
def lecteur():
    return User.objects.create_user(
        username="lecteur_sanction",
        email="lecteur-sanction@iteag.org",
        password="motdepasse-long-12",
    )


@pytest.fixture
def ouvrages():
    discipline = Discipline.objects.create(nom="Sanctions bibliothèque", slug="sanctions-bibliotheque")
    premier = NoticeBibliographique.objects.create(
        titre="Premier ouvrage",
        auteur="Auteur Un",
        cote="SAN-001",
        discipline=discipline,
    )
    second = NoticeBibliographique.objects.create(
        titre="Second ouvrage",
        auteur="Auteur Deux",
        cote="SAN-002",
        discipline=discipline,
    )
    return premier, second


def _emprunt_en_retard(lecteur, notice, jours=5):
    emprunt = services.reserver_ouvrage(notice, lecteur)
    emprunt = services.valider_retrait(emprunt)
    emprunt.date_retour_prevue = timezone.localdate() - timedelta(days=jours)
    emprunt.save(update_fields=["date_retour_prevue", "updated_at"])
    return emprunt


def test_un_retard_en_cours_bloque_immediatement_toute_nouvelle_reservation(lecteur, ouvrages):
    premier, second = ouvrages
    _emprunt_en_retard(lecteur, premier, jours=3)

    with pytest.raises(ValidationError, match="Nouveau prêt impossible"):
        services.reserver_ouvrage(second, lecteur)

    assert second.disponible is True


def test_la_restitution_tardive_cree_une_suspension_proportionnelle(lecteur, ouvrages):
    premier, _ = ouvrages
    emprunt = _emprunt_en_retard(lecteur, premier, jours=5)

    services.restituer_ouvrage(emprunt)

    sanction = SuspensionBibliotheque.objects.get(emprunt=emprunt)
    assert sanction.jours_retard == 5
    assert sanction.jours_suspension == 5
    assert sanction.date_debut == timezone.localdate()
    assert sanction.date_fin == timezone.localdate() + timedelta(days=4)
    assert sanction.est_active is True


def test_la_suspension_bloque_apres_restitution_puis_la_levee_retablit_le_droit(lecteur, ouvrages):
    premier, second = ouvrages
    emprunt = _emprunt_en_retard(lecteur, premier, jours=4)
    services.restituer_ouvrage(emprunt)
    sanction = SuspensionBibliotheque.objects.get(emprunt=emprunt)

    with pytest.raises(ValidationError, match="suspendu"):
        services.reserver_ouvrage(second, lecteur)

    agent = User.objects.create_user(
        username="agent_bibliotheque",
        email="agent@iteag.org",
        password="motdepasse-long-12",
        role=User.Role.SECRETARIAT,
    )
    services.lever_suspension(sanction, par=agent, motif="Erreur de date confirmée par le secrétariat")

    nouvel_emprunt = services.reserver_ouvrage(second, lecteur)
    assert nouvel_emprunt.statut == Emprunt.Statut.RESERVE


def test_la_suspension_est_plafonnee_a_trente_jours(settings, lecteur, ouvrages):
    settings.LIBRARY_SUSPENSION_DAYS_PER_LATE_DAY = 1
    settings.LIBRARY_SUSPENSION_MAX_DAYS = 30
    premier, _ = ouvrages
    emprunt = _emprunt_en_retard(lecteur, premier, jours=45)

    services.restituer_ouvrage(emprunt)

    sanction = SuspensionBibliotheque.objects.get(emprunt=emprunt)
    assert sanction.jours_retard == 45
    assert sanction.jours_suspension == 30


def test_un_retour_a_temps_ne_cree_aucune_sanction(lecteur, ouvrages):
    premier, _ = ouvrages
    emprunt = services.reserver_ouvrage(premier, lecteur)
    emprunt = services.valider_retrait(emprunt)

    services.restituer_ouvrage(emprunt)

    assert not SuspensionBibliotheque.objects.filter(emprunt=emprunt).exists()


def test_le_formulaire_manuel_refuse_un_lecteur_suspendu(lecteur, ouvrages):
    premier, second = ouvrages
    emprunt = _emprunt_en_retard(lecteur, premier, jours=2)
    services.restituer_ouvrage(emprunt)

    form = EmpruntForm(
        data={
            "notice": second.pk,
            "emprunteur": lecteur.pk,
            "statut": Emprunt.Statut.RESERVE,
            "date_retour_prevue": (timezone.localdate() + timedelta(days=21)).isoformat(),
            "commentaire": "",
        }
    )

    assert form.is_valid() is False
    assert "suspendu" in form.errors["emprunteur"][0]
