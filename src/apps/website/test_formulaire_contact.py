from importlib import import_module

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.template.loader import get_template
from django.urls import reverse
from wagtail.contrib.forms.models import FormSubmission
from wagtail.models import Revision, Site

from apps.website.management.commands.setup_initial_pages import ajouter_champs_contact_par_defaut
from apps.website.models import ContactPage, FormField

pytestmark = pytest.mark.django_db


@pytest.fixture
def page_contact():
    accueil = Site.objects.get(is_default_site=True).root_page
    page = ContactPage(
        title="Contact test",
        slug="contact-test",
        thank_you_text="<p>Merci, votre demande est enregistrée.</p>",
    )
    accueil.add_child(instance=page)
    page.save_revision().publish()
    ajouter_champs_contact_par_defaut(page)
    return page


def test_une_nouvelle_page_contact_contient_une_zone_de_message(page_contact, client):
    reponse = client.get(page_contact.url)

    assert reponse.status_code == 200
    assert '<input type="text" name="nom"' in reponse.content.decode()
    assert '<input type="email" name="email"' in reponse.content.decode()
    assert '<textarea name="message"' in reponse.content.decode()


def test_la_confirmation_existante_est_le_gabarit_de_landing():
    page = ContactPage(title="Contact")

    assert page.get_landing_page_template() == "website/contact_success.html"
    assert get_template(page.get_landing_page_template())


def test_un_message_valide_redirige_sans_erreur_de_gabarit(page_contact, client):
    reponse = client.post(
        page_contact.url,
        {
            "nom": "Visiteur test",
            "email": "visiteur@example.org",
            "message": "Bonjour, je souhaite obtenir des renseignements.",
            "honeypot": "",
        },
    )

    assert reponse.status_code == 302
    assert reponse.url == reverse("website:contact_success")
    assert FormSubmission.objects.filter(page=page_contact).count() == 1
    assert client.get(reponse.url).status_code == 200


def test_la_migration_complete_un_formulaire_existant_et_sa_revision():
    accueil = Site.objects.get(is_default_site=True).root_page
    page = ContactPage(title="Contact incomplet", slug="contact-incomplet")
    accueil.add_child(instance=page)
    page.save_revision().publish()
    FormField.objects.create(
        page=page,
        sort_order=0,
        label="Adresse email",
        field_type="email",
        required=True,
        choices="",
        default_value="",
        help_text="",
    )

    migration = import_module("apps.website.migrations.0012_champs_formulaire_contact")
    # C'est l'état historique que Django fournit réellement à RunPython. Le
    # modèle ContactPage de cet état ne possède pas la propriété `template` :
    # l'instancier reproduit l'AttributeError observée en production.
    historique = MigrationExecutor(connection).loader.project_state(
        [("website", "0011_remplir_presentation_iteag")]
    ).apps
    migration.assurer_champs_contact(historique, None)

    champs = list(page.form_fields.order_by("sort_order"))
    assert [(champ.clean_name, champ.field_type) for champ in champs] == [
        ("adresse_email", "email"),
        ("message", "multiline"),
    ]
    # `page` conserve en cache l'objet Revision chargé avant la migration :
    # relire la ligne valide bien le contenu effectivement persisté.
    revision = Revision.objects.get(pk=page.latest_revision_id)
    assert [champ["clean_name"] for champ in revision.content["form_fields"]] == ["adresse_email", "message"]
