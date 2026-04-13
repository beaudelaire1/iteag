"""
Seed complet des fiches professorales ITEAG avec données réelles iteag.org.
Usage : python manage.py seed_profs_detail
"""

from django.core.management.base import BaseCommand

from apps.formations.models import Professeur


PROFESSORS_DATA = {
    # ─── Alain NISUS ─────────────────────────────────────────────
    "alain-nisus": {
        "biographie": (
            "Alain Nisus est directeur de l'ITEAG, professeur associé à la FLTE "
            "et à l'Université Laval (en partenariat avec l'ETEQ), et chargé de cours "
            "à l'ETEQ. Il est l'auteur de nombreux ouvrages théologiques tels que "
            "« L'Église comme communion et comme institution », ou « Pour une foi "
            "réfléchie » écrit sous sa direction."
        ),
        "specialite": "Théologie systématique, Ecclésiologie",
        "parcours_academique": [
            {"annee": "Depuis 2022", "description": "Professeur associé à l'Université Laval (Canada), en partenariat avec l'ETEQ, et chargé de cours à l'ETEQ"},
            {"annee": "2006 – 2018", "description": "Professeur de théologie systématique à la FLTE"},
            {"annee": "2008", "description": "Doctorat en Théologie de l'Institut Catholique de Paris et de la Katholieke Universiteit Leuven sous la direction du professeur Hervé Legrand, « L'Église comme communion et comme institution. Une lecture de l'ecclésiologie du cardinal Congar à partir de la tradition des Églises de professants »"},
            {"annee": "2003 – 2006", "description": "Professeur assistant en théologie systématique à la FLTE"},
            {"annee": "1998 – 2003", "description": "Pasteur de l'Église Baptiste de Grenoble (FEEBF)"},
            {"annee": "1996", "description": "Capacité doctorale en Théologie : Institut Catholique de Paris"},
            {"annee": "1995", "description": "Licence en Philosophie de l'Université Paris VIII"},
            {"annee": "1994 – 1998", "description": "Pasteur de l'Église Baptiste de Versailles (FEEBF)"},
            {"annee": "1993", "description": "Maîtrise en théologie de la FLTE"},
        ],
        "expertises": [
            "Ecclésiologie",
            "Théologie systématique",
            "Éthique chrétienne",
            "Apologétique",
        ],
        "autres_engagements": (
            "Directeur pédagogique de l'Institut de Théologie Évangélique des Antilles et de la Guyane (ITEAG).\n"
            "Professeur associé à la Faculté Libre de Théologie Évangélique (FLTE) à Vaux-sur-Seine.\n"
            "Pasteur de l'Église Évangélique Baptiste de Baie-Mahault (Guadeloupe / France)."
        ),
        "publications_ouvrages": (
            "Une foi, des arguments. Apologétique pour tous (direction en collaboration avec L. Jaeger), Romanel-sur-Lausanne, Maison de la Bible, 2021, 988 p.\n"
            "Mais délivre nous du mal… Traité de démonologie biblique, Romanel-sur-Lausanne, Maison de la Bible, 2015, 238 p.\n"
            "Vivre en chrétiens aujourd'hui. Théologie pour tous (direction en collaboration avec L. Schweitzer et L. Olekhnovitch), Romanel-sur-Lausanne, Maison de la Bible, 2015, 796 p.\n"
            "L'Église comme communion et comme institution, « Cogitatio fidei, 282 », Paris, Cerf, 2012, 508 p (thèse de doctorat révisée et abrégée).\n"
            "L'amour de la sagesse. Hommage à Henri Blocher (s. dir.), Charols, Excelsis, 2012, 408 p.\n"
            "Pour une foi réfléchie. Théologie pour tous (s. dir.), Romanel-sur-Lausanne, Maison de la Bible, 2011, 922 p.\n"
            "Autour du credo, Paris, Croire Publications, 2002, 63 p."
        ),
        "publications_articles": (
            "« Repas du Seigneur et vie fraternelle », Christus 272, 2021, p. 82-88.\n"
            "« Judaïsme et protestantisme évangélique », Hokhma 106, 2014, p. 87-100.\n"
            "« Collégialité et autorité », Les cahiers de l'école pastorale HS 16, 2014, p. 9-36.\n"
            "« Le Seigneur de la création. Éléments d'une éco-théologie », dans J.-P. Bru (s. dir.), Contre vents et marée. Mélanges offerts à Pierre Berthoud et Paul Wells, Charols, Excelsis, 2014, p. 187-207.\n"
            "La foi chrétienne et les défis du monde contemporain, C. Paya et N. Farelly (s. dir.), Charols, Excelsis, 2013 — contributions : « Racisme » p. 297-304, « Sport » p. 398-404, « Être humain » p. 43-49, « Monde invisible, anges et démons » p. 95-101.\n"
            "« La contribution d'Henri Blocher à la théologie », dans A. Nisus (s. dir.), L'amour de la sagesse. Hommage à Henri Blocher, Charols, Excelsis, 2012, p. 11-48.\n"
            "« Actualité du baptême dans les traditions protestantes », Esprit et Vie n° 250, 2012, p. 11-19.\n"
            "Dictionnaire de Théologie pratique, s. dir. C. Paya, Charols, Excelsis, 2011 — contributions : « Autorité » p. 131-138, « Cène » p. 165-171, « Dons spirituels » p. 276-279, « Structures d'Église » p. 629-634.\n"
            "« Le Congrès missionnaire de Lausanne III à Cape Town 2010 : Continuité de l'esprit d'Edimbourg 1910 ? », Perspectives missionnaires 60, 2010, p. 59-66."
        ),
        "cours_enseignes": [
            "La doctrine de l'Écriture, inspiration et autorité de la Bible",
            "La christologie ou étude de la Personne de Jésus Christ",
            "L'homme : image de Dieu et pécheur !",
            "L'œuvre de la croix",
            "La doctrine des fins dernières (eschatologie)",
            "La doctrine de la création",
            "Histoire de la pensée chrétienne",
            "La sotériologie ou doctrine du salut",
            "La pneumatologie ou doctrine de l'Esprit Saint",
            "Le Dieu trinitaire et ses attributs",
            "La doctrine de l'élection",
            "Comment interpréter la Bible ? Introduction à l'herméneutique",
            "Introduction à l'éthique",
        ],
    },

    # ─── Ruth LABETH ─────────────────────────────────────────────
    "ruth-labeth": {
        "biographie": (
            "Ruth Labeth est professeure en théologie pratique et en langues bibliques "
            "et directrice des études de 1er cycle à l'École de théologie évangélique "
            "du Québec (ETEQ). Elle est professeure associée à la Faculté de théologie "
            "et de sciences religieuses de l'Université Laval (Québec, Canada)."
        ),
        "specialite": "Théologie pratique, Langues bibliques",
        "parcours_academique": [
            {"annee": "Depuis 2019", "description": "Directrice des études de 1er cycle à l'ETEQ"},
            {"annee": "2014", "description": "Doctorat en théologie pratique, option musique liturgique, Faculté de théologie Aix-en-Provence (France). Titre de la thèse : « La musique dans le culte évangélique en terrain créole : une lecture anthropo-théologique des pratiques musicales de l'Église évangélique de la Guadeloupe de 1947 à nos jours »"},
            {"annee": "2005", "description": "Diplôme d'études approfondies en théologie de la Faculté libre de théologie réformée Jean Calvin (Aix-en-Provence, France)"},
            {"annee": "1993", "description": "Master of Divinity (Maîtrise) au Toronto Baptist Seminary (Toronto, Canada), « The Stranger in the Land of Israël with special attention to the Book of Ruth »"},
            {"annee": "1989", "description": "Diplôme universitaire du musicien intervenant, Faculté des Arts, Université Marc Bloch de Strasbourg (France)"},
            {"annee": "1985", "description": "Licence en musicologie, Faculté des Arts, Université Marc Bloch de Strasbourg (France)"},
        ],
        "expertises": [
            "Interculturalité et culte",
            "Théologie pratique",
            "Théologie du culte",
            "Ethnodoxologie",
            "Musique liturgique",
            "Hébreu ancien",
            "Histoire d'Israël",
        ],
        "autres_engagements": (
            "Chargée de cours en théologie pratique et Ancien Testament à l'Institut de théologie Évangélique des Antilles-Guyane depuis 2017.\n"
            "Chargée d'enseignement à l'École de Théologie Évangélique au Québec (cours d'hébreu biblique, cours en liturgie, arts et interculturalité) depuis 2016.\n"
            "Enseignement de l'hébreu biblique 2e année à la Faculté Libre de Théologie Évangélique de Vaux-sur-Seine (semaine intensive) 2009-2010.\n"
            "Chargée d'enseignement à la FLTE (cours de musique/chorale) 2009-2011.\n"
            "Enseignement de cours d'histoire d'Israël à l'Institut Biblique de Nogent-sur-Marne (cours intensif) 2006.\n"
            "Chargée d'enseignement à Toronto Baptist Seminary and Bible College (méthodologie, hébreu biblique, exégèse, liturgie) 2002-2008.\n"
            "Membre de l'Association francophone européenne des théologies évangéliques (AFETE).\n"
            "Membre de l'International Council of Ethnodoxologists (ICE).\n"
            "Membre de la Société canadienne de théologie (SCT).\n"
            "Accompagnatrice spirituelle en aumônerie auprès des étudiants de 2017-2019."
        ),
        "publications_ouvrages": "",
        "publications_articles": (
            "« Struggling to be Creole », Global Forum on Arts and Christian Faith 9 (2021): 54-69.\n"
            "« Catholiques et protestants évangéliques face à la question culturelle aux Antilles françaises : entre réception, opposition et composition », revue Kreolistica, 2021.\n"
            "« Le cercle rituel du Gwo-Ka. Musique, identité et spiritualité », éditions Arcanes (Italie), 2019.\n"
            "« Le service à l'Église, femmes, créativité et culte » in Femmes antillaises et christianisme : vers une identité restaurée, s. dir. J.-C. Girondin, Farel, 2017, p. 117-128.\n"
            "« L'ethnodoxologie ou la louange parmi les nations » in Perspectives Missionnaires 74, 2017.\n"
            "« Femmes, créativité et culte » in Femmes antillaises et christianisme : vers une identité restaurée, s. dir. J.-C. Girondin, Farel, 2017, p. 117-128.\n"
            "« La musique : un défi pour la diversité culturelle dans l'Église. Le cas de la musique antillaise » in L'Église, promesses et passerelles vers l'interculturalité ?, s. dir. J.-C. Girondin et F. de Conninck, Charols, Excelsis, 2015, p. 83-100."
        ),
        "cours_enseignes": [
            "Le culte évangélique",
            "Les Psaumes : poésie et théologie",
            "Études du livre des Proverbes et de l'Ecclésiaste",
            "La Bible, d'où vient-elle ? Manuscrits, canon, versions de la Bible",
        ],
    },

    # ─── Daniel REIVAX ───────────────────────────────────────────
    "daniel-reivax": {
        "biographie": (
            "Daniel Reivax possède un doctorat en histoire des civilisations et histoire "
            "contemporaine. Spécialiste du protestantisme français et de l'histoire des "
            "mouvements de réveil, il est également aumônier militaire."
        ),
        "specialite": "Histoire des civilisations, Histoire du protestantisme",
        "parcours_academique": [
            {"annee": "2021", "description": "Doctorat en histoire des civilisations et histoire contemporaine, Université de Picardie Jules Verne. Sujet de thèse : « Raoul Allier (1862-1939), un protestant engagé, une voix du protestantisme français »"},
            {"annee": "2014", "description": "Master de recherche en Sciences humaines et sociales, Université d'Artois"},
            {"annee": "1993", "description": "Maîtrise en théologie, Faculté Libre de théologie évangélique de Vaux-sur-Seine"},
        ],
        "expertises": [
            "Histoire du protestantisme",
            "Séparation des Églises et de l'État",
            "Missiologie",
            "Éthique contemporaine",
        ],
        "autres_engagements": "Aumônier militaire.",
        "publications_ouvrages": "",
        "publications_articles": (
            "« La réponse de la théologie de la libération au problème de la pauvreté », Antilla n°565, semaine du 24 au 30 décembre 1993, p. 34-37.\n"
            "« Éthique familiale et sociale », Amdle, 1996.\n"
            "« Being a Christian in a Post-Modern World: Reflection on a Difficult Issue from a West Indian Perspective », Caribbean Journal of Evangelical Theology, vol. 3, 1999, p. 1-16.\n"
            "« Debout les femmes ! », Les Cahiers de l'histoire de la civilisation chrétienne XVIe–XXe s, vol. 3, 1999-2000, p. 167-178.\n"
            "« Les âmes ont-elles une couleur ? », Les Cahiers de l'histoire de la civilisation chrétienne, XVIe–XXe s, vol. 4, 2001, p. 125-133.\n"
            "« L'abbé Moussa ou la désillusion d'un prêtre nègre », Les Cahiers de l'histoire de la civilisation chrétienne XVIe–XXe s, vol. 5, 2002, p. 131-141.\n"
            "« Pétition des Dames de Paris en faveur de l'abolition de l'esclavage », revue Mofwaz, n°6, 2004, p. 113-124 (Ibis-Rouge).\n"
            "« Raoul Allier, un prédicateur en temps de guerre (1914-1917) », La Cause, 2016."
        ),
        "cours_enseignes": [
            "Histoire de l'Église",
            "Histoire des Réformes et des mouvements de réveil",
        ],
    },

    # ─── Patrice KAULANJAN ───────────────────────────────────────
    "patrice-kaulanjan": {
        "biographie": (
            "Patrice Kaulanjan est chargé de l'encadrement des stages à l'Institut Biblique "
            "de Nogent. Patrice est également le pasteur d'une communauté évangélique "
            "naissante à Versailles."
        ),
        "specialite": "Théologie pratique, Relation d'aide",
        "parcours_academique": [
            {"annee": "", "description": "Diplômé de l'Institut Biblique Européen de Lamorlaye"},
            {"annee": "", "description": "Diplômé de l'IEP d'Aix-en-Provence en Médiation, Gestion des conflits et Coaching"},
            {"annee": "", "description": "Diplômé en Relation d'aide"},
            {"annee": "", "description": "Professeur de Théologie pratique à l'Institut Biblique de Nogent-sur-Marne"},
        ],
        "expertises": [
            "Théologie pratique",
            "Relation d'aide",
            "Médiation et gestion des conflits",
            "Coaching",
        ],
        "autres_engagements": (
            "Pasteur à Versailles.\n"
            "Président de l'Alliance des Églises Évangéliques Interdépendantes."
        ),
        "publications_ouvrages": "",
        "publications_articles": "",
        "cours_enseignes": [
            "Les épîtres pastorales",
            "Théologie et relation d'aide",
        ],
    },

    # ─── Cédric EUGÈNE ───────────────────────────────────────────
    # Pas de fiche détaillée sur iteag.org (retourne Undefined).
    "cedric-eugene": {
        "biographie": "",
        "specialite": "Théologie pratique, Homilétique",
        "parcours_academique": [],
        "expertises": [],
        "autres_engagements": "",
        "publications_ouvrages": "",
        "publications_articles": "",
        "cours_enseignes": [],
    },

    # ─── Stéphane GUILLET ────────────────────────────────────────
    # Pas de fiche détaillée sur iteag.org (retourne Undefined).
    "stephane-guillet": {
        "biographie": "",
        "specialite": "Théologie systématique, Apologétique",
        "parcours_academique": [],
        "expertises": [],
        "autres_engagements": "",
        "publications_ouvrages": "",
        "publications_articles": "",
        "cours_enseignes": [],
    },

    # ─── Jean-Claude GIRONDIN ────────────────────────────────────
    # Pas de fiche détaillée sur iteag.org (retourne Undefined).
    "jean-claude-girondin": {
        "biographie": "",
        "specialite": "Histoire de l'Église, Théologie pratique",
        "parcours_academique": [],
        "expertises": [],
        "autres_engagements": "",
        "publications_ouvrages": "",
        "publications_articles": "",
        "cours_enseignes": [],
    },
}


class Command(BaseCommand):
    help = "Met à jour les fiches professorales avec les données détaillées d'iteag.org"

    def handle(self, *args, **options):
        updated = 0
        for slug, data in PROFESSORS_DATA.items():
            try:
                prof = Professeur.objects.get(slug=slug)
            except Professeur.DoesNotExist:
                self.stderr.write(self.style.WARNING(f"  ⚠ Professeur « {slug} » introuvable, ignoré."))
                continue

            prof.biographie = data["biographie"] or prof.biographie
            prof.specialite = data["specialite"] or prof.specialite
            prof.parcours_academique = data["parcours_academique"] or prof.parcours_academique
            prof.expertises = data["expertises"] or prof.expertises
            prof.autres_engagements = data["autres_engagements"] or prof.autres_engagements
            prof.publications_ouvrages = data["publications_ouvrages"] or prof.publications_ouvrages
            prof.publications_articles = data["publications_articles"] or prof.publications_articles
            prof.cours_enseignes = data["cours_enseignes"] or prof.cours_enseignes
            prof.save()
            updated += 1
            self.stdout.write(self.style.SUCCESS(f"  ✓ {prof.nom_complet}"))

        self.stdout.write(self.style.SUCCESS(f"\n{updated} fiche(s) mise(s) à jour."))
