from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    fichier = ROOT / path
    contenu = fichier.read_text(encoding="utf-8")
    if old not in contenu:
        raise RuntimeError(f"Motif introuvable dans {path}: {old[:80]!r}")
    fichier.write_text(contenu.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str) -> None:
    fichier = ROOT / path
    contenu = fichier.read_text(encoding="utf-8")
    if old not in contenu:
        raise RuntimeError(f"Motif introuvable dans {path}: {old[:80]!r}")
    fichier.write_text(contenu.replace(old, new), encoding="utf-8")


# QCM : la règle de complétude doit être imposée par le service métier, pas
# seulement signalée dans l'atelier enseignant.
replace_once(
    "src/apps/lms/services.py",
    "    inscrits = list(devoir.inscriptions_destinataires())\n",
    "    if devoir.modalite == Devoir.Modalite.QCM:\n"
    "        probleme = motif_qcm_incomplet(devoir)\n"
    "        if probleme:\n"
    "            raise ValidationError(f\"Questionnaire incomplet : {probleme}\")\n\n"
    "    inscrits = list(devoir.inscriptions_destinataires())\n",
)

# Les routes de construction ne doivent accepter que des devoirs QCM.
replace_once(
    "src/apps/lms/views_qcm.py",
    "            Devoir.objects.filter(cours_session__enseignant=professeur).select_related(\n",
    "            Devoir.objects.filter(\n"
    "                cours_session__enseignant=professeur,\n"
    "                modalite=Devoir.Modalite.QCM,\n"
    "            ).select_related(\n",
)
replace_all(
    "src/apps/lms/views_qcm.py",
    "Question.objects.filter(devoir__cours_session__enseignant=professeur)",
    "Question.objects.filter(\n"
    "            devoir__cours_session__enseignant=professeur,\n"
    "            devoir__modalite=Devoir.Modalite.QCM,\n"
    "        )",
)
replace_all(
    "src/apps/lms/views_qcm.py",
    "Choix.objects.filter(question__devoir__cours_session__enseignant=professeur)",
    "Choix.objects.filter(\n"
    "                question__devoir__cours_session__enseignant=professeur,\n"
    "                question__devoir__modalite=Devoir.Modalite.QCM,\n"
    "            )",
)

# Tests de non-régression : publication impossible si le QCM est incomplet et
# impossibilité de détourner l'atelier pour un devoir fichier.
tests_qcm = ROOT / "src/apps/lms/test_qcm_groupes.py"
contenu_tests = tests_qcm.read_text(encoding="utf-8")
marqueur = "def test_un_questionnaire_complet_est_pret(questionnaire):\n    assert services.motif_qcm_incomplet(questionnaire) == \"\"\n"
ajout = marqueur + "\n\ndef test_un_questionnaire_incomplet_ne_peut_pas_etre_publie(cours, etudiant):\n    devoir = Devoir.objects.create(\n        cours_session=cours,\n        titre=\"Questionnaire incomplet\",\n        modalite=Devoir.Modalite.QCM,\n        date_ouverture=timezone.now(),\n        date_fermeture=timezone.now() + timedelta(days=1),\n    )\n\n    with pytest.raises(ValidationError, match=\"Questionnaire incomplet\"):\n        services.publier_devoir(devoir)\n\n    devoir.refresh_from_db()\n    assert devoir.statut == Devoir.Statut.BROUILLON\n    assert not devoir.copies.exists()\n\n\ndef test_l_atelier_qcm_refuse_un_devoir_fichier(client, cours):\n    devoir = Devoir.objects.create(\n        cours_session=cours,\n        titre=\"Dépôt classique\",\n        modalite=Devoir.Modalite.DEPOT_FICHIER,\n        date_ouverture=timezone.now(),\n        date_fermeture=timezone.now() + timedelta(days=1),\n    )\n    client.force_login(cours.enseignant.user)\n\n    reponse = client.get(reverse(\"lms:questionnaire\", args=[devoir.pk]))\n\n    assert reponse.status_code == 404\n"
if "test_un_questionnaire_incomplet_ne_peut_pas_etre_publie" not in contenu_tests:
    if marqueur not in contenu_tests:
        raise RuntimeError("Point d'insertion des tests QCM introuvable")
    tests_qcm.write_text(contenu_tests.replace(marqueur, ajout, 1), encoding="utf-8")

# Chargement normal des modèles d'assiduité, afin que les relations inverses
# soient installées avant les requêtes Django.
apps_academics = ROOT / "src/apps/academics/apps.py"
apps_academics.write_text(
    "from django.apps import AppConfig\n\n\n"
    "class AcademicsConfig(AppConfig):\n"
    "    default_auto_field = \"django.db.models.BigAutoField\"\n"
    "    name = \"apps.academics\"\n"
    "    verbose_name = \"Vie académique\"\n",
    encoding="utf-8",
)
models_academics = ROOT / "src/apps/academics/models.py"
contenu_models = models_academics.read_text(encoding="utf-8")
import_assiduite = (
    "\n\n# Les modèles isolés restent découverts pendant l'import normal de l'app.\n"
    "from apps.academics.models_assiduite import (  # noqa: E402, F401\n"
    "    HistoriquePresence,\n"
    "    Presence,\n"
    "    SeanceCours,\n"
    ")\n"
)
if "from apps.academics.models_assiduite import" not in contenu_models:
    models_academics.write_text(contenu_models.rstrip() + import_assiduite, encoding="utf-8")

# Erreurs de lint qui empêchent actuellement tout test PostgreSQL de démarrer.
replace_once(
    "src/apps/administration/views.py",
    "from apps.library.models import NoticeBibliographique\n",
    "from apps.library.models import Emprunt, NoticeBibliographique\n",
)
replace_once(
    "src/apps/accounts/forms.py",
    '            "titre_qualite_signature": "Mention apparaissant sous/au-dessus de la signature (ex: Le secrétariat, Le Directeur).",\n'
    '            "nom_autorite_signature": "Nom complet imprimé sur les documents officiels (ex: Jean DUPONT, Secrétariat ITEAG).",\n',
    '            "titre_qualite_signature": (\n'
    '                "Mention apparaissant sous/au-dessus de la signature "\n'
    '                "(ex: Le secrétariat, Le Directeur)."\n'
    '            ),\n'
    '            "nom_autorite_signature": (\n'
    '                "Nom complet imprimé sur les documents officiels "\n'
    '                "(ex: Jean DUPONT, Secrétariat ITEAG)."\n'
    '            ),\n',
)
replace_once(
    "src/apps/accounts/models.py",
    '        help_text="Titre officiel apparaissant sur les documents (ex: Le secrétariat, Le Directeur, Le Secrétaire Général).",\n',
    '        help_text=(\n'
    '            "Titre officiel apparaissant sur les documents "\n'
    '            "(ex: Le secrétariat, Le Directeur, Le Secrétaire Général)."\n'
    '        ),\n',
)
replace_once(
    "src/apps/accounts/models.py",
    '        help_text="Nom du signataire ou de l\'autorité apparaissant au bas des documents (ex: Jean DUPONT, Secrétariat ITEAG).",\n',
    '        help_text=(\n'
    '            "Nom du signataire ou de l\'autorité apparaissant au bas des documents "\n'
    '            "(ex: Jean DUPONT, Secrétariat ITEAG)."\n'
    '        ),\n',
)
replace_once(
    "src/apps/documents/test_generation_pdf.py",
    "        from django.core.files.uploadedfile import SimpleUploadedFile\n        from apps.documents.services_generation import fabriquer_document_administratif\n",
    "        from django.core.files.uploadedfile import SimpleUploadedFile\n\n"
    "        from apps.documents.services_generation import fabriquer_document_administratif\n",
)
replace_once(
    "src/apps/documents/test_generation_pdf.py",
    '        image_png = b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01\\x00\\x00\\x00\\x01\\x08\\x06\\x00\\x00\\x00\\x1f\\x15c4\\x00\\x00\\x00\\rIDATx\\x9cc\\xf8\\xff\\xff?\\x03\\x00\\x05\\xfe\\x02\\xfe\\xa7\\x9a\\x9c\\\"\\x00\\x00\\x00\\x00IEND\\xaeB`\\x82"\n',
    '        image_png = (\n'
    '            b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR"\n'
    '            b"\\x00\\x00\\x00\\x01\\x00\\x00\\x00\\x01\\x08\\x06\\x00\\x00\\x00"\n'
    '            b"\\x1f\\x15c4\\x00\\x00\\x00\\rIDATx\\x9cc\\xf8\\xff\\xff?"\n'
    '            b"\\x03\\x00\\x05\\xfe\\x02\\xfe\\xa7\\x9a\\x9c\\\"\\x00\\x00\\x00\\x00"\n'
    '            b"IEND\\xaeB`\\x82"\n'
    '        )\n',
)
replace_once(
    "src/apps/library/tests.py",
    "        notice_ret = services.annuler_reservation(emprunt, user)\n",
    "        services.annuler_reservation(emprunt, user)\n",
)
replace_once(
    "src/apps/library/tests.py",
    "    def test_mes_emprunts_view_etudiant(self, client: Client, notice):\n"
    "        from apps.accounts.models import User\n"
    "        from apps.library import services\n"
    "        from apps.library.models import Emprunt\n",
    "    def test_mes_emprunts_view_etudiant(self, client: Client, notice):\n"
    "        from apps.accounts.models import User\n"
    "        from apps.library import services\n",
)
replace_once(
    "src/apps/library/views.py",
    "    \n    Affiche la liste des livres actuellement en sa possession",
    "\n    Affiche la liste des livres actuellement en sa possession",
)
