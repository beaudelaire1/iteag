from django.db import migrations

PRESENTATION_META = (
    "Découvrir l'ITEAG, centre de formation en théologie évangélique des Antilles et de la Guyane : "
    "sa vocation, sa forme associative et les principes de sa formation."
)

PRESENTATION_BODY = [
    {
        "type": "texte",
        "id": "593cb50e-ffb2-4e89-aa90-2b6949a11cef",
        "value": (
            "<p>L'Institut de Théologie Évangélique des Antilles et de la Guyane est un centre de formation "
            "en théologie évangélique. Il s'adresse à celles et ceux qui souhaitent librement développer "
            "leurs connaissances théologiques ou suivre un parcours diplômant afin de mieux exercer un "
            "ministère au sein de leur assemblée.</p>"
        ),
    },
    {
        "type": "texte",
        "id": "b7887e9a-af61-45ad-b7c0-741a2c1cab79",
        "value": (
            "<h2>L'ITEAG, qu'est-ce que c'est ?</h2>"
            "<p>La vocation de l'ITEAG est la formation théologique. L'institut articule l'acquisition de "
            "connaissances et la préparation au service dans les Églises, avec la possibilité de se former "
            "par intérêt personnel ou dans le cadre d'un parcours conduisant à un diplôme.</p>"
        ),
    },
    {
        "type": "encadre",
        "id": "4277360f-af3a-4699-8e47-d5b97da4eb07",
        "value": {
            "titre": "Un projet fédérateur",
            "contenu": (
                "<p>L'ITEAG se présente comme une association loi 1905 et comme un projet fédérateur "
                "œuvrant à l'unité évangélique.</p>"
            ),
            "tonalite": "information",
        },
    },
    {
        "type": "texte",
        "id": "bcda39ce-cea2-4995-b33e-06f730d7cf47",
        "value": (
            "<h2>Pourquoi choisir l'ITEAG ?</h2>"
            "<p>L'institut met en avant une formation de qualité au service d'une pratique efficace :</p>"
            "<ul>"
            "<li>une formation dispensée localement ;</li>"
            "<li>une équipe pédagogique engagée spirituellement et compétente académiquement ;</li>"
            "<li>une formation à la fois théorique et pratique ;</li>"
            "<li>des personnes en formation disponibles pour les Églises tout au long de leur cursus ;</li>"
            "<li>une bibliothèque accessible aux étudiants.</li>"
            "</ul>"
        ),
    },
    {
        "type": "texte",
        "id": "6ae1b0e8-ffac-46dc-8711-25134a8d1e13",
        "value": (
            "<h2>Se former à l'ITEAG</h2>"
            "<p>Les parcours proposés permettent d'aborder la formation théologique selon son projet : "
            "approfondissement personnel, préparation au ministère ou parcours diplômant.</p>"
            '<p><a href="/formations/">Découvrir les formations proposées</a></p>'
        ),
    },
]


def remplir_presentation(apps, schema_editor):
    ContentPage = apps.get_model("website", "ContentPage")
    page = ContentPage.objects.filter(slug="presentation").first()
    if page is None:
        return

    # Une page déjà rédigée dans Wagtail est une décision éditoriale humaine :
    # le déploiement ne doit jamais l'écraser. La page créée historiquement par
    # setup_initial_pages était vide, c'est uniquement ce cas que l'on complète.
    if page.body:
        return

    page.body = PRESENTATION_BODY
    page.meta_description = PRESENTATION_META
    page.search_description = PRESENTATION_META
    page.save(update_fields=["body", "meta_description", "search_description"])


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0010_temoignage_photo_retrait"),
    ]

    operations = [
        migrations.RunPython(remplir_presentation, migrations.RunPython.noop),
    ]
