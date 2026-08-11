from django.db import migrations

CHOIX_OBJET = "Renseignements généraux\nInscriptions et admissions\nFormations et cursus\nBibliothèque\nAutre"

NOMS_NOM = {"nom", "nom_complet", "name", "full_name"}
NOMS_PRENOM = {"prenom", "first_name"}
NOMS_TELEPHONE = {"telephone", "tel", "phone", "numero_de_telephone"}
NOMS_OBJET = {"objet", "sujet", "subject", "objet_de_votre_demande"}


def _creer_champ(FormField, page_id, *, clean_name, label, field_type, required, choices="", help_text=""):
    return FormField.objects.create(
        page_id=page_id,
        sort_order=100,
        clean_name=clean_name,
        label=label,
        field_type=field_type,
        required=required,
        choices=choices,
        default_value="",
        help_text=help_text,
    )


def _serialiser(champ, page_id):
    return {
        "pk": champ.pk,
        "sort_order": champ.sort_order,
        "clean_name": champ.clean_name,
        "label": champ.label,
        "field_type": champ.field_type,
        "required": champ.required,
        "choices": champ.choices,
        "default_value": champ.default_value,
        "help_text": champ.help_text,
        "page": page_id,
    }


def completer_formulaire_contact(apps, schema_editor):
    ContactPage = apps.get_model("website", "ContactPage")
    FormField = apps.get_model("website", "FormField")
    Revision = apps.get_model("wagtailcore", "Revision")

    # Même précaution que dans 0012 : values() évite d'instancier le modèle
    # historique ContactPage, dont le FormMixin attend une propriété template.
    pages = ContactPage.objects.values("pk", "live_revision_id", "latest_revision_id")
    for page in pages:
        page_id = page["pk"]
        champs = list(FormField.objects.filter(page_id=page_id).order_by("sort_order", "pk"))

        nom = next((champ for champ in champs if champ.clean_name in NOMS_NOM), None)
        if nom is None:
            nom = _creer_champ(
                FormField,
                page_id,
                clean_name="nom",
                label="Nom",
                field_type="singleline",
                required=True,
            )
            champs.append(nom)
        elif nom.clean_name == "nom_complet" and nom.label != "Nom":
            nom.label = "Nom"
            nom.save(update_fields=["label"])

        prenom = next((champ for champ in champs if champ.clean_name in NOMS_PRENOM), None)
        if prenom is None:
            prenom = _creer_champ(
                FormField,
                page_id,
                clean_name="prenom",
                label="Prénom",
                field_type="singleline",
                required=True,
            )
            champs.append(prenom)

        email = next((champ for champ in champs if champ.field_type == "email"), None)
        if email is None:
            email = _creer_champ(
                FormField,
                page_id,
                clean_name="email",
                label="Email",
                field_type="email",
                required=True,
            )
            champs.append(email)

        telephone = next((champ for champ in champs if champ.clean_name in NOMS_TELEPHONE), None)
        if telephone is None:
            telephone = _creer_champ(
                FormField,
                page_id,
                clean_name="telephone",
                label="Téléphone",
                field_type="singleline",
                required=False,
                help_text="Facultatif",
            )
            champs.append(telephone)
        elif telephone.label != "Téléphone":
            telephone.label = "Téléphone"
            telephone.save(update_fields=["label"])

        objet = next((champ for champ in champs if champ.clean_name in NOMS_OBJET), None)
        if objet is None:
            objet = _creer_champ(
                FormField,
                page_id,
                clean_name="objet",
                label="Objet",
                field_type="dropdown",
                required=True,
                choices=CHOIX_OBJET,
            )
            champs.append(objet)
        else:
            mises_a_jour = []
            if objet.label != "Objet":
                objet.label = "Objet"
                mises_a_jour.append("label")
            if objet.field_type == "dropdown" and not objet.choices.strip():
                objet.choices = CHOIX_OBJET
                mises_a_jour.append("choices")
            if mises_a_jour:
                objet.save(update_fields=mises_a_jour)

        message = next((champ for champ in champs if champ.field_type == "multiline"), None)
        if message is None:
            message = _creer_champ(
                FormField,
                page_id,
                clean_name="message",
                label="Message",
                field_type="multiline",
                required=True,
            )
            champs.append(message)

        priorite = {
            nom.pk: 0,
            prenom.pk: 1,
            email.pk: 2,
            telephone.pk: 3,
            objet.pk: 4,
            message.pk: 5,
        }
        champs.sort(key=lambda champ: (priorite.get(champ.pk, 100), champ.sort_order or 0, champ.pk))
        for sort_order, champ in enumerate(champs):
            if champ.sort_order != sort_order:
                champ.sort_order = sort_order
                champ.save(update_fields=["sort_order"])

        # La révision publiée doit porter les mêmes champs que la table enfant,
        # sinon une republication Wagtail peut remettre l'ancien formulaire.
        champs_serialises = [_serialiser(champ, page_id) for champ in champs]
        revision_ids = {page["live_revision_id"], page["latest_revision_id"]} - {None}
        for revision in Revision.objects.filter(pk__in=revision_ids):
            contenu = revision.content
            contenu["form_fields"] = champs_serialises
            revision.content = contenu
            revision.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0012_champs_formulaire_contact"),
    ]

    operations = [
        migrations.RunPython(completer_formulaire_contact, migrations.RunPython.noop),
    ]
