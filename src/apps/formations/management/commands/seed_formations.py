"""
Peuple la base avec les données réelles de formations issues d'iteag.org.
Usage: python manage.py seed_formations
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.formations.models import Cours, Discipline, Parcours, Professeur, Tarif


class Command(BaseCommand):
    help = "Insère les données de référence formations (disciplines, parcours, professeurs, tarifs, cours)"

    def handle(self, *args, **options):
        self._seed_disciplines()
        self._seed_parcours()
        self._seed_professeurs()
        self._seed_tarifs()
        self._seed_cours()
        self.stdout.write(self.style.SUCCESS("Seed formations terminé."))

    # ── Disciplines ──────────────────────────────────────────
    def _seed_disciplines(self):
        data = [
            {"nom": "Ancien Testament", "ordre": 1, "description": "Étude des textes de l'Ancien Testament : Pentateuque, livres historiques, poétiques et prophétiques. Exégèse, théologie et contexte historique."},
            {"nom": "Nouveau Testament", "ordre": 2, "description": "Étude des Évangiles, des Actes, des Épîtres et de l'Apocalypse. Exégèse, contexte gréco-romain et théologie néotestamentaire."},
            {"nom": "Théologie systématique", "ordre": 3, "description": "Doctrine chrétienne : théologie propre, christologie, pneumatologie, sotériologie, ecclésiologie, eschatologie. Aussi appelée « doctrine »."},
            {"nom": "Histoire de l'Église", "ordre": 4, "description": "Des origines à nos jours : Pères de l'Église, Réforme, mouvements évangéliques, histoire du christianisme dans la Caraïbe et aux Antilles-Guyane."},
            {"nom": "Théologie pratique", "ordre": 5, "description": "Homilétique, pastorale, counseling, leadership ecclésial, missiologie, éthique chrétienne et accompagnement spirituel."},
        ]
        for d in data:
            obj, created = Discipline.objects.update_or_create(
                slug=slugify(d["nom"]),
                defaults=d,
            )
            status = "créée" if created else "mise à jour"
            self.stdout.write(f"  Discipline {obj.nom} — {status}")

    # ── Parcours ─────────────────────────────────────────────
    def _seed_parcours(self):
        data = [
            {
                "nom": "Parcours diplômant ITEAG",
                "slug": "diplomant-iteag",
                "type_parcours": "diplomant_iteag",
                "ects_requis": 180,
                "duree_annees": 6,
                "description": (
                    "Formation complète en théologie évangélique sanctionnée par le diplôme de l'ITEAG.\n\n"
                    "Aucun diplôme d'entrée n'est exigé. L'obtention du diplôme nécessite un total de 180 ECTS. "
                    "Chaque cours validé permet d'obtenir 2,5 ECTS. Un crédit représente un volume de travail de 25 à 30 heures.\n\n"
                    "Validation : travaux écrits (dissertation, recension, commentaire de textes, résumés ou comparaisons de livres), "
                    "stages (30 ECTS), VAE possible. En cas d'impossibilité de stage : dissertation de fin d'études (15 ECTS). "
                    "Les 30 ECTS manquants peuvent être obtenus par cours in absentia ou e-learning de la FLTE."
                ),
                "conditions_entree": (
                    "Aucun diplôme d'entrée exigé.\n"
                    "Assiduité requise.\n"
                    "4 sessions d'une semaine par an pendant 6 ans."
                ),
                "meta_description": "Parcours diplômant ITEAG : 180 ECTS, 6 ans, aucun diplôme d'entrée exigé. Formation théologique complète aux Antilles-Guyane.",
            },
            {
                "nom": "Bachelor FLTE",
                "slug": "bachelor-flte",
                "type_parcours": "bachelor_flte",
                "ects_requis": 180,
                "duree_annees": 6,
                "description": (
                    "En partenariat avec la Faculté Libre de Théologie Évangélique (FLTE) de Vaux-sur-Seine.\n\n"
                    "Tous les étudiants suivent les mêmes cours magistraux que le parcours diplômant. "
                    "La différence se fait au niveau des exigences de validation (Bachelor FLTE vs diplôme ITEAG).\n\n"
                    "Nécessite l'obtention de 180 ECTS (ceux proposés par l'ITEAG + 30 de la FLTE). "
                    "Mêmes conditions que pour le diplôme de l'ITEAG pour la partie ITEAG."
                ),
                "conditions_entree": (
                    "Baccalauréat ou équivalent requis.\n"
                    "Lecture de l'anglais vivement conseillée.\n"
                    "4 sessions d'une semaine par an pendant 6 ans."
                ),
                "meta_description": "Bachelor FLTE en partenariat avec Vaux-sur-Seine. Baccalauréat requis, 180 ECTS, formation théologique de niveau universitaire.",
            },
            {
                "nom": "Parcours libre",
                "slug": "parcours-libre",
                "type_parcours": "libre",
                "ects_requis": 0,
                "duree_annees": 0,
                "description": (
                    "Ouvert à tous, sans exigence de diplôme ni de validation.\n\n"
                    "Choisissez vos sessions et profitez simplement des cours ! "
                    "Pas de visée diplômante — idéal pour ceux qui souhaitent approfondir "
                    "leurs connaissances théologiques à leur rythme, sans contrainte d'évaluation."
                ),
                "conditions_entree": (
                    "Aucune condition d'entrée.\n"
                    "Ouvert à tous.\n"
                    "Choix des sessions possible."
                ),
                "meta_description": "Parcours libre ITEAG : ouvert à tous, sans diplôme requis, sans validation. Suivez les cours de théologie de votre choix.",
            },
            {
                "nom": "ITEAG Pro",
                "slug": "iteag-pro",
                "type_parcours": "pro",
                "ects_requis": 0,
                "duree_annees": 0,
                "description": (
                    "Formation continue et renforcement des compétences des cadres de l'Église aux Antilles.\n\n"
                    "Trois axes fondamentaux :\n"
                    "• Caractère (savoir-être) : renforcer la vie intérieure et les capacités intérieures.\n"
                    "• Connaissance (savoir) : acquérir, actualiser et renforcer les connaissances et compétences pratiques.\n"
                    "• Compétence (savoir-faire) : créer et consolider une communauté de compétences au service des Églises.\n\n"
                    "Retombées : progrès personnel (piété, vie intérieure, connaissance), professionnalisme dans le ministère, "
                    "crédibilité dans l'exercice du ministère, force de l'exemple pour la nouvelle génération, "
                    "opportunité d'une dynamique inter-ecclésiale."
                ),
                "conditions_entree": (
                    "Destiné aux cadres d'Église en activité.\n"
                    "Pasteurs, anciens, responsables de ministère."
                ),
                "meta_description": "ITEAG Pro : formation continue pour les cadres d'Église. Savoir-être, savoir, savoir-faire au service des assemblées.",
            },
        ]
        for d in data:
            obj, created = Parcours.objects.update_or_create(
                slug=d["slug"],
                defaults=d,
            )
            status = "créé" if created else "mis à jour"
            self.stdout.write(f"  Parcours {obj.nom} — {status}")

    # ── Professeurs ──────────────────────────────────────────
    def _seed_professeurs(self):
        data = [
            {"prenom": "Ruth", "nom": "Labeth", "ordre": 1},
            {"prenom": "Alain", "nom": "Nisus", "ordre": 2},
            {"prenom": "Daniel", "nom": "Reivax", "ordre": 3},
            {"prenom": "Cédric", "nom": "Eugène", "ordre": 4},
            {"prenom": "Stéphane", "nom": "Guillet", "ordre": 5},
            {"prenom": "Jean-Claude", "nom": "Girondin", "ordre": 6},
            {"prenom": "Patrice", "nom": "Kaulanjan", "ordre": 7},
        ]
        for d in data:
            slug = slugify(f"{d['prenom']}-{d['nom']}")
            obj, created = Professeur.objects.update_or_create(
                slug=slug,
                defaults={**d, "actif": True},
            )
            status = "créé" if created else "mis à jour"
            self.stdout.write(f"  Professeur {obj.prenom} {obj.nom} — {status}")

    # ── Tarifs (iteag.org/enroll) ────────────────────────────
    def _seed_tarifs(self):
        data = [
            {"formule": "toutes", "type_membre": "fondatrice", "montant_session": 200},
            {"formule": "toutes", "type_membre": "autre", "montant_session": 250},
            {"formule": "choix", "type_membre": "fondatrice", "montant_session": 250},
            {"formule": "choix", "type_membre": "autre", "montant_session": 300},
        ]
        for d in data:
            obj, created = Tarif.objects.update_or_create(
                formule=d["formule"],
                type_membre=d["type_membre"],
                defaults={"montant_session": d["montant_session"], "actif": True},
            )
            status = "créé" if created else "mis à jour"
            self.stdout.write(f"  Tarif {obj} — {status}")

    # ── Cours exemples (rattachés aux disciplines) ───────────
    def _seed_cours(self):
        disciplines = {d.slug: d for d in Discipline.objects.all()}
        parcours_diplomant = Parcours.objects.filter(type_parcours__in=["diplomant_iteag", "bachelor_flte"])
        parcours_all = Parcours.objects.filter(type_parcours__in=["diplomant_iteag", "bachelor_flte", "libre"])

        cours_data = [
            # Ancien Testament
            {"titre": "Introduction à l'Ancien Testament", "code": "AT-101", "discipline": "ancien-testament", "description": "Survol de l'Ancien Testament : contexte historique, littéraire et théologique. Présentation des grands thèmes et de la structure canonique."},
            {"titre": "Pentateuque", "code": "AT-201", "discipline": "ancien-testament", "description": "Étude approfondie des cinq livres de Moïse : Genèse, Exode, Lévitique, Nombres, Deutéronome. Questions d'auteur, de date et de théologie."},
            {"titre": "Livres prophétiques", "code": "AT-301", "discipline": "ancien-testament", "description": "Étude des prophètes majeurs et mineurs. Contexte historique, message prophétique et pertinence contemporaine."},
            {"titre": "Livres poétiques et sapientiaux", "code": "AT-302", "discipline": "ancien-testament", "description": "Job, Psaumes, Proverbes, Ecclésiaste, Cantique des Cantiques. Genres littéraires et sagesse biblique."},
            # Nouveau Testament
            {"titre": "Introduction au Nouveau Testament", "code": "NT-101", "discipline": "nouveau-testament", "description": "Survol du Nouveau Testament : contexte gréco-romain, judaïsme du Second Temple, questions d'introduction."},
            {"titre": "Évangiles synoptiques", "code": "NT-201", "discipline": "nouveau-testament", "description": "Étude comparative de Matthieu, Marc et Luc. Problème synoptique, critique rédactionnelle, théologie de chaque évangéliste."},
            {"titre": "Épîtres pauliniennes", "code": "NT-301", "discipline": "nouveau-testament", "description": "Étude des lettres de Paul : Romains, Corinthiens, Galates, Éphésiens, etc. Théologie paulinienne et contexte ecclésial."},
            {"titre": "Évangile et Épîtres de Jean", "code": "NT-302", "discipline": "nouveau-testament", "description": "Le corpus johannique : quatrième évangile, 1-3 Jean, Apocalypse. Théologie johannique."},
            # Théologie systématique
            {"titre": "Théologie propre et christologie", "code": "TS-101", "discipline": "theologie-systematique", "description": "Doctrine de Dieu (attributs, trinité) et doctrine du Christ (personne et œuvre)."},
            {"titre": "Sotériologie et pneumatologie", "code": "TS-201", "discipline": "theologie-systematique", "description": "Doctrine du salut et doctrine du Saint-Esprit. Justification, sanctification, dons spirituels."},
            {"titre": "Ecclésiologie et eschatologie", "code": "TS-301", "discipline": "theologie-systematique", "description": "Doctrine de l'Église et des derniers temps. Nature de l'Église, sacrements, retour de Christ."},
            # Histoire de l'Église
            {"titre": "Histoire de l'Église ancienne", "code": "HE-101", "discipline": "histoire-de-leglise", "description": "Des origines au Moyen Âge : Pères apostoliques, conciles, développement de la doctrine, christianisation de l'Empire romain."},
            {"titre": "Réforme et post-Réforme", "code": "HE-201", "discipline": "histoire-de-leglise", "description": "Luther, Calvin, Zwingli, Réforme radicale. Contre-Réforme, orthodoxie protestante, piétisme, revivalisme."},
            {"titre": "Histoire du christianisme dans la Caraïbe", "code": "HE-301", "discipline": "histoire-de-leglise", "description": "Christianisation des Antilles, missions protestantes, mouvements évangéliques caribéens, histoire de l'Église aux Antilles-Guyane."},
            # Théologie pratique
            {"titre": "Homilétique", "code": "TP-101", "discipline": "theologie-pratique", "description": "Art de la prédication : préparation, structure, communication, illustration. Exercices pratiques de prédication."},
            {"titre": "Pastorale et counseling", "code": "TP-201", "discipline": "theologie-pratique", "description": "Accompagnement pastoral : visites, counseling biblique, gestion de conflits, soin des âmes."},
            {"titre": "Leadership ecclésial et missiologie", "code": "TP-301", "discipline": "theologie-pratique", "description": "Direction d'Église, gestion d'équipe, vision missionnaire, implantation d'Églises, contexte caribéen."},
            {"titre": "Éthique chrétienne", "code": "TP-302", "discipline": "theologie-pratique", "description": "Fondements bibliques de l'éthique, questions contemporaines, bioéthique, éthique sociale et politique."},
        ]

        for cd in cours_data:
            disc = disciplines.get(cd["discipline"])
            if not disc:
                self.stdout.write(self.style.WARNING(f"  Discipline {cd['discipline']} introuvable, cours ignoré."))
                continue
            obj, created = Cours.objects.update_or_create(
                slug=slugify(cd["titre"]),
                defaults={
                    "titre": cd["titre"],
                    "code": cd["code"],
                    "discipline": disc,
                    "description": cd["description"],
                    "ects": 2.5,
                    "actif": True,
                },
            )
            # Rattacher aux parcours diplômant/bachelor/libre
            obj.parcours.set(parcours_all)
            status = "créé" if created else "mis à jour"
            self.stdout.write(f"  Cours {obj.code} {obj.titre} — {status}")
