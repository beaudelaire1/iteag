"""Le vocabulaire d'un document officiel — et pourquoi il n'est pas celui du site.

Un corps de texte libre ne sait pas porter un tableau. On peut certes coller du
HTML de tableau dans un éditeur riche, mais plus rien ne le vérifie : ni le
nombre de colonnes, ni les en-têtes, ni ce qui arrive à l'impression quand il
dépasse la page. Le contenu structuré se déclare, il ne se colle pas.

**Pourquoi des blocs distincts de ceux du site.** « apps/website » possède déjà
un encadré, une image légendée, une citation. Les réutiliser tels quels
donnerait un PDF mis en page pour un navigateur : largeurs en pourcentage,
ombres portées, images qui se coupent entre deux pages. Un bloc destiné au
papier connaît les millimètres, l'orphelin et la veuve, et le fait qu'il n'y a
pas de survol sur une feuille A4. Ces blocs-ci partagent la structure des
autres, pas leur rendu.

**Ce que ce vocabulaire coûte.** Le widget StreamField hors de l'administration
Wagtail réclame cinq scripts, dont quatre sont déjà servis par l'éditeur riche
des portails. Le surcoût réel est de 44 Ko — le prix d'une petite image, pour
un contenu qui devient vérifiable.
"""

from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.contrib.typed_table_block.blocks import TypedTableBlock

# Les mêmes fonctionnalités que le corps des articles et des actualités : un
# document n'a pas besoin d'un autre jeu de mise en forme, et deux profils
# différents produiraient deux rendus différents pour le même gras.
MISE_EN_FORME = (
    "h2",
    "h3",
    "bold",
    "italic",
    "underline",
    "ol",
    "ul",
    "link",
    "superscript",
    "subscript",
)


class ParagrapheBlock(blocks.RichTextBlock):
    """Le texte courant. C'est le bloc par défaut, et le plus fréquent."""

    def __init__(self, **kwargs):
        kwargs.setdefault("features", MISE_EN_FORME)
        kwargs.setdefault("label", _("Paragraphes"))
        super().__init__(**kwargs)

    class Meta:
        icon = "pilcrow"
        template = "documents/pdf/blocs/paragraphe.html"


class TableauBlock(TypedTableBlock):
    """Un tableau dont les colonnes sont typées, et non un collage de HTML.

    « TypedTableBlock » plutôt que « TableBlock » : le second embarque
    Handsontable, une bibliothèque de tableur de plusieurs centaines de kilos,
    pour un usage où l'on saisit six lignes. Le premier déclare ses colonnes,
    ce qui permet d'aligner les nombres à droite sans le demander à chaque
    cellule.
    """

    def __init__(self, **kwargs):
        super().__init__(
            [
                ("texte", blocks.CharBlock(label=_("Texte"))),
                ("nombre", blocks.DecimalBlock(label=_("Nombre"), required=False)),
                ("date", blocks.DateBlock(label=_("Date"), required=False)),
                ("paragraphe", blocks.RichTextBlock(features=["bold", "italic", "link"], required=False)),
            ],
            **kwargs,
        )

    class Meta:
        icon = "table"
        label = _("Tableau")
        template = "documents/pdf/blocs/tableau.html"


class EncadreBlock(blocks.StructBlock):
    """Une mention détachée du fil : avertissement, rappel, mention légale.

    La tonalité n'est pas une couleur mais une intention : elle décide du filet
    et du picto, ici comme sur le site, et elle reste lisible en noir et blanc —
    un document officiel se photocopie.
    """

    titre = blocks.CharBlock(required=False, max_length=140, label=_("Titre"))
    texte = blocks.RichTextBlock(features=["bold", "italic", "ol", "ul", "link"], label=_("Texte"))
    tonalite = blocks.ChoiceBlock(
        choices=[
            ("information", _("Information")),
            ("avertissement", _("Avertissement")),
            ("mention_legale", _("Mention légale")),
        ],
        default="information",
        label=_("Tonalité"),
    )

    class Meta:
        icon = "warning"
        label = _("Encadré")
        template = "documents/pdf/blocs/encadre.html"


class IconeBlock(blocks.StructBlock):
    """Un pictogramme choisi dans un jeu arrêté, suivi d'une ligne de texte.

    Le choix est fermé, et c'est délibéré : laisser téléverser un picto par
    document produirait dix variantes de la même flèche, à dix résolutions.
    """

    # Le tracé vit ici, et non en huit fichiers SVG : ce sont des glyphes de
    # quelques dizaines d'octets, toujours utilisés ensemble, et les éparpiller
    # obligerait à ouvrir huit fichiers pour vérifier qu'ils s'accordent.
    #
    # Les lignes dépassent la mesure, et l'exception est posée sur chacune
    # plutôt qu'en tête de fichier : un « ruff: noqa » global vaudrait pour tout
    # le module et couvrirait les lignes trop longues qu'on y écrira ensuite.
    TRACES = {
        "calendrier": "M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5",  # noqa: E501
        "horloge": "M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z",
        "lieu": "M15 10.5a3 3 0 11-6 0 3 3 0 016 0z M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z",  # noqa: E501
        "telephone": "M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z",  # noqa: E501
        "courriel": "M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75",  # noqa: E501
        "piece_jointe": "M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13",  # noqa: E501
        "attention": "M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z",  # noqa: E501
        "valide": "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
    }

    ICONES = [
        ("calendrier", _("Calendrier")),
        ("horloge", _("Horloge")),
        ("lieu", _("Lieu")),
        ("telephone", _("Téléphone")),
        ("courriel", _("Courriel")),
        ("piece_jointe", _("Pièce jointe")),
        ("attention", _("Attention")),
        ("valide", _("Validé")),
    ]

    icone = blocks.ChoiceBlock(choices=ICONES, label=_("Pictogramme"))
    texte = blocks.CharBlock(max_length=250, label=_("Texte"))

    def get_context(self, value, parent_context=None):
        contexte = super().get_context(value, parent_context=parent_context)
        contexte["trace"] = self.TRACES.get(value.get("icone"), "")
        return contexte

    class Meta:
        icon = "tag"
        label = _("Ligne avec pictogramme")
        template = "documents/pdf/blocs/icone.html"


class SautDePageBlock(blocks.StaticBlock):
    """Force la suite sur une nouvelle page.

    Sans lui, on obtient le saut voulu en ajoutant des paragraphes vides — qui
    se décalent à la première correction et laissent une page blanche au milieu
    du document.
    """

    class Meta:
        icon = "horizontalrule"
        label = _("Saut de page")
        admin_text = _("Le contenu suivant commencera sur une nouvelle page.")
        template = "documents/pdf/blocs/saut_de_page.html"


class CorpsDocument(blocks.StreamBlock):
    """Le corps d'un document officiel."""

    paragraphe = ParagrapheBlock()
    tableau = TableauBlock(required=False)
    encadre = EncadreBlock()
    icone = IconeBlock()
    saut_de_page = SautDePageBlock()

    # L'image manque, et c'est délibéré. « ImageChooserBlock » fonctionnerait —
    # il ne coûte que trois scripts — mais son dialogue est servi par
    # « /admin/images/chooser/ », que les portails n'atteignent pas. Le poser
    # ici donnerait un bouton qui ouvre une fenêtre vide.
    #
    # Le chemin est connu et déjà emprunté : « core:editeur_lien_externe »
    # sert le dialogue officiel de lien depuis une route de portail. La même
    # passerelle rendra l'image disponible, et ce bloc sera ajouté alors.

    class Meta:
        block_counts = {"saut_de_page": {"max_num": 20}}
