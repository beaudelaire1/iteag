from django.db import migrations

CHAMPS_CONTACT_PAR_DEFAUT = (
    {
        "clean_name": "nom",
        "label": "Nom",
        "field_type": "singleline",
        "required": True,
    },
    {
        "clean_name": "email",
        "label": "Email",
        "field_type": "email",
        "required": True,
    },
    {
        "clean_name": "message",
        "label": "Message",
        "field_type": "multiline",
        "required": True,
    },
)


def assurer_champs_contact(apps, schema_editor):
    ContactPage = apps.get_model("website", "ContactPage")
    FormField = apps.get_model("website", "FormField")
    Revision = apps.get_model("wagtailcore", "Revision")

    # Ne jamais instancier ici le modèle historique ContactPage : son héritage
    # FormMixin appelle `self.template` dans __init__, tandis que les modèles
    # reconstruits par Django pendant une migration n'exposent pas cette
    # propriété Wagtail. `values()` contourne entièrement cette initialisation.
    pages = ContactPage.objects.values("pk", "live_revision_id", "latest_revision_id")
    for page in pages:
        page_id = page["pk"]
        champs = list(FormField.objects.filter(page_id=page_id).order_by("sort_order", "pk"))
        if not champs:
            for sort_order, definition in enumerate(CHAMPS_CONTACT_PAR_DEFAUT):
                FormField.objects.create(
                    page_id=page_id,
                    sort_order=sort_order,
                    choices="",
                    default_value="",
                    help_text="",
                    **definition,
                )
        elif not any(champ.field_type == "multiline" for champ in champs):
            # Les formulaires éditoriaux existants sont conservés. On garantit
            # seulement qu'ils offrent une vraie zone de rédaction.
            message = next((champ for champ in champs if champ.clean_name == "message"), None)
            if message is not None:
                message.field_type = "multiline"
                message.save(update_fields=["field_type"])
            else:
                derniers_ordres = [champ.sort_order for champ in champs if champ.sort_order is not None]
                FormField.objects.create(
                    page_id=page_id,
                    sort_order=(max(derniers_ordres) + 1) if derniers_ordres else len(champs),
                    clean_name="message",
                    label="Message",
                    field_type="multiline",
                    required=True,
                    choices="",
                    default_value="",
                    help_text="",
                )

        # Historiquement les champs avaient parfois été ajoutés directement
        # dans leur table après publication. Le site les affichait, mais la
        # révision Wagtail restait vide et pouvait les effacer à la prochaine
        # publication. On complète uniquement les révisions qui n'en portent
        # aucun, sans toucher à une ébauche éditoriale déjà configurée.
        champs = list(FormField.objects.filter(page_id=page_id).order_by("sort_order", "pk"))
        champs_serialises = [
            {
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
            for champ in champs
        ]
        revision_ids = {page["live_revision_id"], page["latest_revision_id"]} - {None}
        for revision in Revision.objects.filter(pk__in=revision_ids):
            contenu = revision.content
            if contenu.get("form_fields"):
                continue
            contenu["form_fields"] = champs_serialises
            revision.content = contenu
            revision.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0011_remplir_presentation_iteag"),
    ]

    operations = [
        migrations.RunPython(assurer_champs_contact, migrations.RunPython.noop),
    ]
