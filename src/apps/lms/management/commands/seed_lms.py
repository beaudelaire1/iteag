"""
Peuple l'espace pédagogique : ressources, évaluations, annonces.

Usage : python manage.py seed_lms

C'est ce jeu qui fait vivre le portail enseignant. Les évaluations couvrent
les cinq états du cycle de correction — en attente, soumis, en correction,
noté, publié — parce que c'est exactement ce que les écrans « préparer les
évaluations », « noter » et « publier les notes » servent à faire avancer.
Sans copies dans plusieurs états, ces trois écrans paraissent inertes.

Les fichiers de ressources sont écrits pour de bon : un lien de téléchargement
qui renvoie une erreur pendant une démonstration est pire que pas de lien.
"""

from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.academics.models import CoursDeSession, InscriptionSession
from apps.lms.models import Annonce, Evaluation, RessourcePedagogique

# (titre, description, extension)
RESSOURCES = [
    ("Plan de cours et bibliographie", "Progression séance par séance et ouvrages à se procurer.", "pdf"),
    ("Support de la séance 1", "Diapositives projetées lors de la première séance.", "pdf"),
    ("Texte à préparer pour la séance 2", "Extrait à lire et annoter avant la prochaine rencontre.", "pdf"),
    ("Consignes du devoir écrit", "Sujet, attendus, critères d'évaluation et date de remise.", "pdf"),
]

ANNONCES = [
    (
        "Bienvenue dans ce cours",
        "Le cours commence lundi à 8 h 00. Merci de vous être procuré les ouvrages indiqués dans la "
        "bibliographie : nous les utiliserons dès la première séance.",
    ),
    (
        "Salle modifiée pour la séance de jeudi",
        "En raison d'une réunion du conseil, la séance de jeudi se tiendra en salle Siloé et non en "
        "amphithéâtre. Les horaires restent inchangés.",
    ),
    (
        "Remise du devoir écrit",
        "Le devoir est à déposer sur le portail avant dimanche 23 h 59. Les consignes détaillées "
        "figurent dans les ressources du cours.",
    ),
]

APPRECIATIONS = [
    "Travail sérieux et bien documenté. L'argumentation gagnerait à s'appuyer davantage sur le texte hébreu.",
    "Bonne maîtrise du contexte historique. Attention à la rigueur des références bibliographiques.",
    "Devoir clair et bien construit. La conclusion mériterait d'être développée.",
    "Excellente lecture du passage. Analyse personnelle et bien étayée.",
    "Ensemble satisfaisant, mais la problématique reste trop implicite dans l'introduction.",
]

CYCLE = [
    (Evaluation.StatutEvaluation.PUBLIE, Decimal("15.5")),
    (Evaluation.StatutEvaluation.NOTE, Decimal("13.0")),
    (Evaluation.StatutEvaluation.EN_CORRECTION, None),
    (Evaluation.StatutEvaluation.SOUMIS, None),
    (Evaluation.StatutEvaluation.EN_ATTENTE, None),
    (Evaluation.StatutEvaluation.PUBLIE, Decimal("17.0")),
    (Evaluation.StatutEvaluation.NOTE, Decimal("9.5")),
]


class Command(BaseCommand):
    help = "Insère ressources pédagogiques, évaluations dans tous leurs états, et annonces de cours."

    @transaction.atomic
    def handle(self, *args, **options):
        cours_sessions = list(
            CoursDeSession.objects.select_related("cours", "enseignant__user").order_by("session_id", "id")
        )
        if not cours_sessions:
            self.stdout.write(
                self.style.ERROR("Aucun cours programmé — lancez d'abord « manage.py seed_vie_academique ».")
            )
            return

        self._seed_ressources(cours_sessions)
        self._seed_annonces(cours_sessions)
        self._seed_evaluations(cours_sessions)

        self.stdout.write(
            self.style.SUCCESS(
                f"Espace pédagogique : {RessourcePedagogique.objects.count()} ressource(s), "
                f"{Evaluation.objects.count()} évaluation(s), {Annonce.objects.count()} annonce(s)."
            )
        )

    # ── Ressources ───────────────────────────────────────────
    def _seed_ressources(self, cours_sessions) -> None:
        # Un PDF minimal mais valide : les lecteurs l'ouvrent, ce qui vaut mieux
        # qu'un fichier vide qui ferait échouer le téléchargement en démonstration.
        pdf = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n"
        )

        for programme in cours_sessions:
            if programme.ressources.exists():
                continue
            for rang, (titre, description, extension) in enumerate(RESSOURCES):
                ressource = RessourcePedagogique(
                    cours_session=programme,
                    titre=f"{titre} — {programme.cours.titre}",
                    description=description,
                    type_fichier=extension,
                    taille=len(pdf),
                    uploade_par=getattr(programme.enseignant, "user", None),
                    visible_etudiants=rang < 3,  # la dernière reste en préparation
                )
                ressource.fichier.save(
                    f"{programme.cours.slug}-{rang + 1}.{extension}",
                    ContentFile(pdf),
                    save=False,
                )
                ressource.save()

    # ── Annonces ─────────────────────────────────────────────
    def _seed_annonces(self, cours_sessions) -> None:
        for programme in cours_sessions:
            if programme.annonces.exists():
                continue
            nombre = 3 if programme.statut == CoursDeSession.StatutCours.EN_COURS else 1
            for titre, contenu in ANNONCES[:nombre]:
                Annonce.objects.create(
                    cours_session=programme,
                    auteur=getattr(programme.enseignant, "user", None),
                    titre=titre,
                    contenu=contenu,
                )

    # ── Évaluations ──────────────────────────────────────────
    def _seed_evaluations(self, cours_sessions) -> None:
        """Une copie par inscrit, réparties sur tout le cycle de correction."""
        copie = ContentFile(b"Copie de demonstration.\n", name="copie.txt")
        compteur = 0

        for programme in cours_sessions:
            inscrits = InscriptionSession.objects.filter(cours_session=programme).select_related("etudiant")
            for inscription in inscrits:
                statut, note = CYCLE[compteur % len(CYCLE)]
                type_evaluation = (
                    Evaluation.TypeEvaluation.EXAMEN if compteur % 3 == 0 else Evaluation.TypeEvaluation.DEVOIR
                )
                compteur += 1

                if Evaluation.objects.filter(etudiant=inscription.etudiant, cours_session=programme).exists():
                    continue

                soumise = statut != Evaluation.StatutEvaluation.EN_ATTENTE
                notee = note is not None

                evaluation = Evaluation(
                    etudiant=inscription.etudiant,
                    cours_session=programme,
                    type_evaluation=type_evaluation,
                    statut=statut,
                    date_soumission=timezone.now() if soumise else None,
                    note=note,
                    appreciation=APPRECIATIONS[compteur % len(APPRECIATIONS)] if notee else "",
                    ects_valides=(programme.cours.ects or Decimal("5.0")) if notee and note >= 10 else Decimal("0.0"),
                    date_notation=timezone.now() if notee else None,
                )
                if soumise:
                    copie.seek(0)
                    evaluation.fichier_soumis.save(
                        f"copie-{inscription.etudiant.numero_etudiant}-{programme.pk}.txt",
                        copie,
                        save=False,
                    )
                evaluation.save()
