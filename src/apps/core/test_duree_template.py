from apps.core.templatetags.duree import duree_humaine


def test_duree_inferieure_a_une_heure_reste_en_minutes():
    assert duree_humaine(45 * 60) == "45 min"


def test_duree_exacte_en_heures_n_affiche_pas_zero_minute():
    assert duree_humaine(60 * 60) == "1 h"


def test_duree_longue_est_affichee_en_heures_et_minutes():
    assert duree_humaine(132 * 60) == "2 h 12 min"


def test_minutes_sont_alignees_sur_deux_chiffres_apres_une_heure():
    assert duree_humaine(65 * 60) == "1 h 05 min"
