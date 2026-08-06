"""Le corps revient à l'éditeur riche, celui des articles et des actualités.

Le widget StreamField ne s'amorçait pas dans les portails : la zone de saisie
restait vide et l'envoi partait sans « corps-count ». Six correctifs successifs
ont chacun levé un obstacle réel — amorçage, préfixe, socle de scripts,
configuration Wagtail, nonce CSP, forme de la sentinelle — sans jamais rendre le
champ utilisable. L'éditeur riche, lui, fonctionne déjà dans ces mêmes écrans.

Ce qu'on perd : tableaux, encadrés, pictogrammes et images dans le corps. Ce
qu'on regagne : un champ où écrire. Le vocabulaire reste dans « blocs.py » pour
le jour où son widget démarrera.

La conversion précède le changement de type : les paragraphes sont recollés en
HTML, le reste n'a pas d'équivalent et disparaît.
"""

import json
import uuid

from django.db import migrations, models


def blocs_vers_html(apps, schema_editor):
    """Recolle les paragraphes ; les autres blocs n'ont pas d'équivalent."""
    Document = apps.get_model("documents", "DocumentRedige")
    for identifiant, corps in Document.objects.values_list("pk", "corps"):
        if hasattr(corps, "raw_data"):
            blocs = corps.raw_data
        else:
            texte = (corps or "").strip()
            if not texte.startswith("["):
                continue  # deja du HTML : une migration doit pouvoir etre rejouee
            try:
                blocs = json.loads(texte)
            except (TypeError, ValueError):
                continue
        Document.objects.filter(pk=identifiant).update(
            corps="".join(b.get("value", "") for b in blocs if b.get("type") == "paragraphe")
        )


def html_vers_blocs(apps, schema_editor):
    """Marche arriere : le HTML redevient un unique bloc « paragraphe »."""
    Document = apps.get_model("documents", "DocumentRedige")
    for identifiant, corps in Document.objects.values_list("pk", "corps"):
        texte = (corps or "").strip()
        if not texte or texte.startswith("["):
            continue
        Document.objects.filter(pk=identifiant).update(
            corps=json.dumps([{"type": "paragraphe", "value": texte, "id": str(uuid.uuid4())}], ensure_ascii=False)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0006_bloc_image"),
    ]

    operations = [
        migrations.RunPython(blocs_vers_html, html_vers_blocs),
        migrations.AlterField(
            model_name="documentredige",
            name="corps",
            field=models.TextField(blank=True, verbose_name="Corps du document"),
        ),
    ]
