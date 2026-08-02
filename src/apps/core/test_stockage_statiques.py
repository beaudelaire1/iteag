"""Le manifeste des statiques doit rester strict — sauf là où c'est déclaré.

Défaut constaté en production, jamais en développement : toutes les pages de
« /django-admin/ » répondaient 500, sur

    ValueError: Missing staticfiles manifest entry for 'vendor/bootswatch'

`jazzmin` désigne un **répertoire** dans un `{% static %}`, pour que son script
y ajoute côté client le nom du thème choisi. Un manifeste ne recense que des
fichiers : la référence n'y figure donc jamais.

Le piège tient à ce que le développement ne consulte aucun manifeste. Un
gabarit fautif y passe inaperçu, et n'échoue qu'une fois déployé.
"""

from pathlib import Path

import pytest
from django.conf import settings

from apps.core.stockage import CHEMINS_HORS_MANIFESTE, StockageStatiquesITEAG

GABARITS_JAZZMIN = Path(settings.BASE_DIR).parent / ".venv" / "Lib" / "site-packages" / "jazzmin" / "templates"


@pytest.fixture
def stockage():
    instance = StockageStatiquesITEAG()
    # Un manifeste vide : tout chemin y est absent, ce qui est justement la
    # situation qu'on veut départager.
    instance.hashed_files = {}
    return instance


def test_le_chemin_declare_est_servi_tel_quel(stockage):
    assert stockage.stored_name("vendor/bootswatch") == "vendor/bootswatch"


def test_un_chemin_non_declare_echoue_toujours(stockage):
    """Le filet reste armé : c'est tout l'intérêt du manifeste.

    Désarmer le manifeste pour tout le projet aurait réglé le symptôme et rendu
    silencieuse la prochaine référence réellement cassée.
    """
    with pytest.raises(ValueError, match="Missing staticfiles manifest entry"):
        stockage.stored_name("css/feuille-inexistante.css")


def test_la_liste_des_exceptions_reste_courte(stockage):
    """Une exception non retirée devient une règle. Celle-ci se compte."""
    assert len(CHEMINS_HORS_MANIFESTE) == 1, (
        "Toute entrée ajoutée doit être justifiée dans « apps/core/stockage.py », "
        "et retirée dès que la bibliothèque tierce est corrigée."
    )


@pytest.mark.skipif(not GABARITS_JAZZMIN.exists(), reason="jazzmin absent de cet environnement")
def test_l_exception_correspond_bien_a_un_besoin_de_jazzmin():
    """Le jour où jazzmin corrigera son gabarit, ce test dira de retirer l'exception."""
    base = (GABARITS_JAZZMIN / "admin" / "base.html").read_text(encoding="utf-8")
    assert "{% static 'vendor/bootswatch' %}" in base, (
        "jazzmin ne réclame plus ce répertoire : retirer l'entrée de CHEMINS_HORS_MANIFESTE."
    )


def test_la_production_emploie_ce_stockage():
    """Le réglage et la classe doivent rester solidaires."""
    reglages = Path(settings.BASE_DIR) / "config" / "settings" / "prod.py"
    assert "apps.core.stockage.StockageStatiquesITEAG" in reglages.read_text(encoding="utf-8")
