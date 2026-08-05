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
    Le jeu vit dans « templates/documents/pdf/icones/ ».
    """

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
