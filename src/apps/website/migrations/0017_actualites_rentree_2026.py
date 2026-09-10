"""Publie les deux annonces de la rentrée 2026 : la session de formation
biblique du 26 au 30 octobre, et le cycle d'ateliers de prédication 2026-2027.

Ces deux contenus sont rédigés d'après les affiches fournies par le secrétariat.
Ils sont créés une seule fois, et jamais réécrits : une actualité déjà présente
sous le même slug est une décision éditoriale humaine, que le déploiement laisse
intacte. Sur une base sans arborescence Wagtail — les tests, une base neuve —
il n'y a pas d'index d'actualités et la migration ne fait rien.

Contrairement à la plupart des migrations de données, celle-ci travaille avec
les vrais modèles et non avec les modèles historiques : créer une page Wagtail
demande « add_child », « save_revision » et « publish », qui n'existent pas sur
un modèle reconstruit par le mécanisme des migrations.
"""

import datetime

from django.db import migrations

DATE_FORMATION = datetime.date(2026, 9, 10)
DATE_ATELIERS = datetime.date(2026, 9, 9)

# ── Formation biblique — 26 au 30 octobre 2026 ────────────────────────────────

FORMATION_SLUG = "formation-biblique-26-30-octobre-2026"
FORMATION_TITRE = "Formation biblique du 26 au 30 octobre 2026"
FORMATION_CHAPEAU = (
    "Cinq matinées de formation, du lundi 26 au vendredi 30 octobre 2026, de 8h à 13h, à l'Église "
    "Protestante Évangélique de Morne Bernard (Baie-Mahault). Deux cours : la « Bible » éthiopienne "
    "avec le théologien Alain Nisus, et une introduction à l'exégèse du Nouveau Testament avec "
    "Cédric Eugène, professeur à la Faculté Libre de Théologie Évangélique. Formation payante, "
    "accessible à tous."
)

FORMATION_CONTENU = [
    {
        "type": "chiffres_cles",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a01",
        "value": {
            "titre": "La session en un coup d'œil",
            "elements": [
                {
                    "valeur": "26 → 30 oct.",
                    "libelle": "Du lundi au vendredi",
                    "precision": "Cinq matinées consécutives, en octobre 2026",
                },
                {
                    "valeur": "8h – 13h",
                    "libelle": "Chaque matin",
                    "precision": "Cinq heures d'enseignement par jour",
                },
                {
                    "valeur": "2 cours",
                    "libelle": "Deux enseignants",
                    "precision": "Alain Nisus et Cédric Eugène",
                },
                {
                    "valeur": "Baie-Mahault",
                    "libelle": "Église Protestante Évangélique",
                    "precision": "Morne Bernard, 97122 Baie-Mahault",
                },
            ],
        },
    },
    {
        "type": "important",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a02",
        "value": {
            "titre": "Formation payante, accessible à tous",
            "contenu": (
                "<p>La session est ouverte à toute personne qui souhaite se former : membre d'Église, "
                "responsable, prédicateur ou étudiant. Le tarif et les modalités d'inscription "
                "s'obtiennent auprès du secrétariat de l'ITEAG.</p>"
            ),
        },
    },
    {
        "type": "texte",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a03",
        "value": (
            "<h2>Deux cours au programme</h2>"
            "<p>Une formation de qualité pour un service efficace : la semaine réunit deux "
            "enseignements complémentaires, l'un sur l'histoire du texte biblique, l'autre sur la "
            "manière de le lire.</p>"
        ),
    },
    {
        "type": "tableau",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a04",
        "value": {
            "columns": [
                {"type": "texte", "heading": "Cours"},
                {"type": "texte", "heading": "Intervenant"},
            ],
            "rows": [
                {
                    "values": [
                        "<p><b>La « Bible » éthiopienne est-elle la « vraie » Bible ?</b></p>"
                        "<p>Étude de l'histoire de ce livre et de ses textes apocryphes "
                        "(Hénoch, Psaumes 151, 3 Esdras, etc.)</p>",
                        "<p><b>Alain Nisus</b></p><p>Théologien</p>",
                    ]
                },
                {
                    "values": [
                        "<p><b>Comment étudier rigoureusement un texte du Nouveau Testament ?</b></p>"
                        "<p>Introduction à l'exégèse</p>",
                        "<p><b>Cédric Eugène</b></p>"
                        "<p>Professeur de Nouveau Testament à la Faculté Libre de Théologie "
                        "Évangélique</p>",
                    ]
                },
            ],
            "caption": "",
        },
    },
    {
        "type": "texte",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a05",
        "value": (
            "<h2>La « Bible » éthiopienne est-elle la « vraie » Bible ?</h2>"
            "<h3>Avec Alain Nisus, théologien</h3>"
            "<p>On parle beaucoup en ce moment de la « Bible » éthiopienne. On prétend qu'elle est la "
            "véritable bible que l'Église « officielle » a longtemps tenu cachée car elle révèlerait "
            "des secrets particuliers que l'Église veut taire.</p>"
            "<p>Dans ce cours, nous allons procéder à une démystification de cette collection de "
            "livres. Après avoir fourni quelques éléments historiques sur l'Église éthiopienne, nous "
            "étudierons certains livres de la Bible éthiopienne.</p>"
        ),
    },
    {
        "type": "encadre",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a06",
        "value": {
            "titre": "Ce que ce cours abordera",
            "contenu": (
                "<ul>"
                "<li>quelques repères historiques de l'Église éthiopienne ;</li>"
                "<li>l'étude détaillée de certains livres de la Bible éthiopienne ;</li>"
                "<li>la question du canon — la liste des livres bibliques que l'on tient pour "
                "inspirés.</li>"
                "</ul>"
            ),
            "tonalite": "information",
        },
    },
    {
        "type": "texte",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a07",
        "value": (
            "<h2>Comment étudier rigoureusement un texte du Nouveau Testament ?</h2>"
            "<h3>Introduction à l'exégèse, avec Cédric Eugène, professeur de Nouveau Testament à la "
            "Faculté Libre de Théologie Évangélique</h3>"
        ),
    },
    {
        "type": "citation",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a08",
        "value": {
            "citation": "La Parole de Dieu mérite d'être lue avec le cœur et avec l'intelligence.",
            "auteur": "Cédric Eugène",
            "source": "Présentation du cours",
        },
    },
    {
        "type": "texte",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a09",
        "value": (
            "<p>Mais comment lire un texte biblique sans le déformer ? Comment le laisser vraiment "
            "parler ? Ce cours proposera une méthodologie concrète pour étudier la Bible avec "
            "intelligence, profondeur et respect.</p>"
        ),
    },
    {
        "type": "encadre",
        "id": "3f0d6a11-1c4b-4a4e-9f2a-6c0f1d2e4a10",
        "value": {
            "titre": "S'inscrire et se renseigner",
            "contenu": (
                "<p>Le secrétariat de l'ITEAG reçoit les inscriptions et répond aux questions.</p>"
                "<ul>"
                "<li>Téléphone : 0690 37 64 17</li>"
                '<li>Courriel : <a href="mailto:secretariat.iteag@gmail.com">'
                "secretariat.iteag@gmail.com</a></li>"
                "<li>Lieu : Église Protestante Évangélique, Morne Bernard, 97122 Baie-Mahault</li>"
                "</ul>"
            ),
            "tonalite": "conseil",
        },
    },
]

# ── Ateliers de prédication — cycle 2026-2027 ─────────────────────────────────

ATELIERS_SLUG = "ateliers-de-predication-2026-2027"
ATELIERS_TITRE = "Ateliers de prédication 2026-2027, avec le Dr Alain Nisus"
ATELIERS_CHAPEAU = (
    "Un samedi matin par mois, de 9h à 12h, de septembre 2026 à juin 2027 : dix ateliers animés par "
    "le Dr Alain Nisus, pour prédicateurs en « espérance », débutants ou confirmés. Thème de "
    "l'année : clartés sur la mort, l'au-delà, la résurrection, le jugement, « l'enfer » et le "
    "« ciel ». Exercices pratiques. Tarif : 200,00 €."
)

# La colonne « Samedi du mois » n'est pas une glose : l'affiche signale elle-même
# les séances qui ne tombent pas le troisième samedi. Elle les rend simplement
# lisibles ligne à ligne, plutôt que par un jeu d'astérisques en bas de page.
ATELIERS_SEANCES = [
    ("1", "Samedi 26 septembre 2026", "4<sup>e</sup> samedi du mois"),
    ("2", "Samedi 31 octobre 2026", "5<sup>e</sup> samedi du mois"),
    ("3", "Samedi 28 novembre 2026", "4<sup>e</sup> samedi du mois"),
    ("4", "Samedi 19 décembre 2026", "3<sup>e</sup> samedi du mois"),
    ("5", "Samedi 16 janvier 2027", "3<sup>e</sup> samedi du mois"),
    ("6", "Samedi 20 février 2027", "3<sup>e</sup> samedi du mois"),
    ("7", "Samedi 6 mars 2027", "1<sup>er</sup> samedi du mois"),
    ("8", "Samedi 17 avril 2027", "3<sup>e</sup> samedi du mois"),
    ("9", "Samedi 15 mai 2027", "3<sup>e</sup> samedi du mois"),
    ("10", "Samedi 19 juin 2027", "3<sup>e</sup> samedi du mois"),
]

ATELIERS_CONTENU = [
    {
        "type": "chiffres_cles",
        "id": "7b2c9e33-5d81-4f60-8a13-2e5b7c9d1f01",
        "value": {
            "titre": "L'essentiel en un coup d'œil",
            "elements": [
                {
                    "valeur": "10 séances",
                    "libelle": "De septembre 2026 à juin 2027",
                    "precision": "Un samedi matin par mois",
                },
                {
                    "valeur": "9h – 12h",
                    "libelle": "Le 3ᵉ samedi du mois",
                    "precision": "Quatre séances font exception — voir le calendrier",
                },
                {
                    "valeur": "200,00 €",
                    "libelle": "Tarif de la formation",
                    "precision": "",
                },
                {
                    "valeur": "Baie-Mahault",
                    "libelle": "Église Évangélique Protestante",
                    "precision": "Morne Bernard – Destrellan, 97122 Baie-Mahault",
                },
            ],
        },
    },
    {
        "type": "important",
        "id": "7b2c9e33-5d81-4f60-8a13-2e5b7c9d1f02",
        "value": {
            "titre": "Pour prédicateurs en « espérance », débutants ou confirmés",
            "contenu": (
                "<p>Les ateliers s'adressent aussi bien à celles et ceux qui commencent qu'aux "
                "prédicateurs déjà expérimentés. Chaque séance comporte des <b>exercices "
                "pratiques</b>.</p>"
            ),
        },
    },
    {
        "type": "texte",
        "id": "7b2c9e33-5d81-4f60-8a13-2e5b7c9d1f03",
        "value": (
            "<h2>Le thème de l'année</h2>"
            "<p>Le Dr Alain Nisus conduit l'ensemble du cycle. Les ateliers apportent des "
            "<b>clartés sur</b> :</p>"
            "<ul>"
            "<li>la mort ;</li>"
            "<li>l'au-delà ;</li>"
            "<li>la résurrection ;</li>"
            "<li>le jugement ;</li>"
            "<li>« l'enfer » ;</li>"
            "<li>le « ciel ».</li>"
            "</ul>"
        ),
    },
    {
        "type": "texte",
        "id": "7b2c9e33-5d81-4f60-8a13-2e5b7c9d1f04",
        "value": "<h2>Le calendrier des dix séances</h2>",
    },
    {
        "type": "tableau",
        "id": "7b2c9e33-5d81-4f60-8a13-2e5b7c9d1f05",
        "value": {
            "columns": [
                {"type": "texte", "heading": "Séance"},
                {"type": "texte", "heading": "Date"},
                {"type": "texte", "heading": "Samedi du mois"},
            ],
            "rows": [
                {
                    "values": [
                        f"<p>{numero}</p>",
                        f"<p><b>{date}</b></p>",
                        f"<p>{precision}</p>",
                    ]
                }
                for numero, date, precision in ATELIERS_SEANCES
            ],
            "caption": "",
        },
    },
    {
        "type": "encadre",
        "id": "7b2c9e33-5d81-4f60-8a13-2e5b7c9d1f06",
        "value": {
            "titre": "Horaire de chaque atelier",
            "contenu": "<p>De <b>9h à 12h</b>, le samedi matin.</p>",
            "tonalite": "information",
        },
    },
    {
        "type": "encadre",
        "id": "7b2c9e33-5d81-4f60-8a13-2e5b7c9d1f07",
        "value": {
            "titre": "Lieu, inscription et contact",
            "contenu": (
                "<p>Église Évangélique Protestante — Morne Bernard, Destrellan, "
                "97122 Baie-Mahault.</p>"
                "<ul>"
                "<li>Téléphone : 0690 37 64 17</li>"
                '<li>Courriel : <a href="mailto:secretariat.iteag@gmail.com">'
                "secretariat.iteag@gmail.com</a></li>"
                '<li>Site : <a href="https://iteag.org">iteag.org</a></li>'
                "</ul>"
            ),
            "tonalite": "conseil",
        },
    },
]


def _publier_actualite(index, *, slug, titre, date, chapeau, contenu):
    """Crée puis publie une actualité, sans jamais toucher à une page existante."""
    from apps.website.models import NewsPage
    from apps.website.models_publications import ContenuActualite

    if NewsPage.objects.filter(slug=slug).exists():
        return

    actualite = NewsPage(
        title=titre,
        slug=slug,
        date=date,
        excerpt=chapeau,
        body=f"<p>{chapeau}</p>",
        meta_description=chapeau[:300],
        search_description=chapeau[:300],
        live=False,
    )
    index.add_child(instance=actualite)
    ContenuActualite.objects.create(actualite=actualite, contenu=contenu)
    actualite.save_revision().publish()


def publier_les_annonces(apps, schema_editor):
    from apps.website.models import NewsIndexPage

    index = NewsIndexPage.objects.first()
    if index is None:
        # Pas d'arborescence Wagtail : base de test ou installation neuve.
        return

    _publier_actualite(
        index,
        slug=FORMATION_SLUG,
        titre=FORMATION_TITRE,
        date=DATE_FORMATION,
        chapeau=FORMATION_CHAPEAU,
        contenu=FORMATION_CONTENU,
    )
    _publier_actualite(
        index,
        slug=ATELIERS_SLUG,
        titre=ATELIERS_TITRE,
        date=DATE_ATELIERS,
        chapeau=ATELIERS_CHAPEAU,
        contenu=ATELIERS_CONTENU,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0016_catalogue_brochures"),
    ]

    operations = [
        migrations.RunPython(publier_les_annonces, migrations.RunPython.noop),
    ]
