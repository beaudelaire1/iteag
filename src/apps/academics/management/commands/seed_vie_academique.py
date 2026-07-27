"""
Peuple la vie académique : étudiants, sessions, inscriptions, finances, ECTS.

Usage : python manage.py seed_vie_academique

C'est le jeu de données dont dépend l'essentiel du portail secrétariat. Le
principe qui a guidé sa composition : **chaque écran doit montrer au moins un
cas de chaque état qu'il sait afficher**. Une liste où toutes les lignes sont
identiques ne démontre ni les filtres, ni les compteurs, ni les actions.

D'où des étudiants dans six statuts, des demandes d'inscription dans quatre,
des paiements en attente autant que confirmés, un stage validé et un en cours,
une VAE accordée et une en examen.

Le mot de passe des comptes créés est volontairement le même et sans valeur :
ce sont des comptes de démonstration, jamais destinés à un serveur ouvert.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.academics.models import (
    VAE,
    CoursDeSession,
    CreditECTS,
    DemandeInscriptionCours,
    InscriptionSession,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
    Stage,
)
from apps.accounts.models import User
from apps.formations.models import Cours, Parcours, Professeur

MOT_DE_PASSE_DEMO = "DemoIteag!2026"

# (prénom, nom, n° étudiant, statut, parcours (slug ou None), église fondatrice)
ETUDIANTS = [
    ("Josiane", "Marceline", "ETU-2026-001", ProfilEtudiant.StatutInscription.ACTIF, True),
    ("Emmanuel", "Sainte-Rose", "ETU-2026-002", ProfilEtudiant.StatutInscription.ACTIF, False),
    ("Marie-Claire", "Bhagavan", "ETU-2026-003", ProfilEtudiant.StatutInscription.ACTIF, False),
    ("Alexandre", "Nordé", "ETU-2026-004", ProfilEtudiant.StatutInscription.ACTIF, True),
    ("Sylviane", "Kancel", "ETU-2026-005", ProfilEtudiant.StatutInscription.INSCRIT, False),
    ("Gérard", "Toussaint", "ETU-2026-006", ProfilEtudiant.StatutInscription.INSCRIT, False),
    ("Léonie", "Abaul", "ETU-2026-007", ProfilEtudiant.StatutInscription.PAIEMENT_ATTENTE, False),
    ("Patrick", "Céleste", "ETU-2026-008", ProfilEtudiant.StatutInscription.PRE_INSCRIT, False),
    ("Nadège", "Boisrond", "ETU-2026-009", ProfilEtudiant.StatutInscription.SUSPENDU, False),
    ("Rosemonde", "Lauriette", "ETU-2025-014", ProfilEtudiant.StatutInscription.DIPLOME, True),
    ("Jean-Marc", "Édouard", "ETU-2025-021", ProfilEtudiant.StatutInscription.DIPLOME, False),
    ("Christiane", "Pancrate", "ETU-2026-010", ProfilEtudiant.StatutInscription.ACTIF, False),
]


class Command(BaseCommand):
    help = "Insère étudiants, sessions, cours de session, inscriptions, paiements, stages, VAE et crédits ECTS."

    @transaction.atomic
    def handle(self, *args, **options):
        parcours = list(Parcours.objects.all())
        cours = list(Cours.objects.filter(actif=True))
        professeurs = list(Professeur.objects.all())
        if not (parcours and cours and professeurs):
            self.stdout.write(self.style.ERROR("Référentiel absent — lancez d'abord « manage.py seed_formations »."))
            return

        promotions = self._seed_promotions(parcours)
        etudiants = self._seed_etudiants(parcours, promotions)
        sessions = self._seed_sessions()
        cours_sessions = self._seed_cours_de_session(sessions, cours, professeurs)
        self._seed_inscriptions(etudiants, cours_sessions)
        self._seed_paiements(etudiants, sessions)
        self._seed_stages_vae_ects(etudiants, professeurs, cours, sessions)

        self.stdout.write(
            self.style.SUCCESS(
                f"Vie académique : {ProfilEtudiant.objects.count()} étudiant(s), "
                f"{SessionAcademique.objects.count()} session(s), "
                f"{CoursDeSession.objects.count()} cours programmé(s), "
                f"{Paiement.objects.count()} paiement(s)."
            )
        )
        self.stdout.write(f"  Comptes étudiants — mot de passe commun : {MOT_DE_PASSE_DEMO}")

    # ── Promotions ───────────────────────────────────────────
    def _seed_promotions(self, parcours) -> list[Promotion]:
        promotions = []
        for index, parcours_courant in enumerate(parcours):
            debut = 2024 + index % 2
            promotion, _ = Promotion.objects.get_or_create(
                nom=f"Promotion {debut}-{debut + 3} — {parcours_courant.nom}",
                parcours=parcours_courant,
                defaults={"annee_debut": debut, "annee_fin": debut + 3, "actif": True},
            )
            promotions.append(promotion)
        return promotions

    # ── Étudiants ────────────────────────────────────────────
    def _seed_etudiants(self, parcours, promotions) -> list[ProfilEtudiant]:
        profils = []
        for index, (prenom, nom, numero, statut, eglise) in enumerate(ETUDIANTS):
            identifiant = f"{prenom}.{nom}".lower().replace(" ", "").replace("-", "").replace("é", "e")
            utilisateur, cree = User.objects.get_or_create(
                username=identifiant,
                defaults={
                    "email": f"{identifiant}@example.org",
                    "first_name": prenom,
                    "last_name": nom,
                    "role": User.Role.ETUDIANT,
                    "is_active": statut != ProfilEtudiant.StatutInscription.SUSPENDU,
                },
            )
            if cree:
                utilisateur.set_password(MOT_DE_PASSE_DEMO)
                utilisateur.save(update_fields=["password"])

            profil, _ = ProfilEtudiant.objects.get_or_create(
                utilisateur=utilisateur,
                defaults={
                    "parcours": parcours[index % len(parcours)],
                    "promotion": promotions[index % len(promotions)],
                    "numero_etudiant": numero,
                    "statut_inscription": statut,
                    "eglise_fondatrice": eglise,
                },
            )
            profils.append(profil)
        return profils

    # ── Sessions ─────────────────────────────────────────────
    def _seed_sessions(self) -> list[SessionAcademique]:
        aujourdhui = timezone.localdate()
        planifiees = [
            (
                "Session de Carnaval 2026",
                SessionAcademique.Periode.CARNAVAL,
                "2025-2026",
                aujourdhui - timedelta(days=150),
                aujourdhui - timedelta(days=140),
                SessionAcademique.StatutSession.TERMINEE,
            ),
            (
                "Session de Pâques 2026",
                SessionAcademique.Periode.PAQUES,
                "2025-2026",
                aujourdhui - timedelta(days=8),
                aujourdhui + timedelta(days=2),
                SessionAcademique.StatutSession.EN_COURS,
            ),
            (
                "Session de Juillet 2026",
                SessionAcademique.Periode.JUILLET,
                "2025-2026",
                aujourdhui + timedelta(days=40),
                aujourdhui + timedelta(days=52),
                SessionAcademique.StatutSession.PLANIFIEE,
            ),
            (
                "Session de Toussaint 2026",
                SessionAcademique.Periode.TOUSSAINT,
                "2026-2027",
                aujourdhui + timedelta(days=95),
                aujourdhui + timedelta(days=105),
                SessionAcademique.StatutSession.PLANIFIEE,
            ),
        ]
        sessions = []
        for nom, periode, annee, debut, fin, statut in planifiees:
            session, _ = SessionAcademique.objects.get_or_create(
                nom=nom,
                defaults={
                    "periode": periode,
                    "annee_academique": annee,
                    "date_debut": debut,
                    "date_fin": fin,
                    "statut": statut,
                },
            )
            sessions.append(session)
        return sessions

    # ── Cours programmés ─────────────────────────────────────
    def _seed_cours_de_session(self, sessions, cours, professeurs) -> list[CoursDeSession]:
        modalites = [
            CoursDeSession.Modalite.PRESENTIEL,
            CoursDeSession.Modalite.HYBRIDE,
            CoursDeSession.Modalite.DISTANCIEL,
        ]
        salles = ["Salle Bethel", "Salle Siloé", "Amphithéâtre Carmel", "Salle Emmaüs"]
        programmes = []
        compteur = 0

        for session in sessions:
            for rang in range(4):
                cours_courant = cours[(compteur) % len(cours)]
                enseignant = professeurs[compteur % len(professeurs)]
                compteur += 1

                if session.statut == SessionAcademique.StatutSession.TERMINEE:
                    statut = CoursDeSession.StatutCours.TERMINE
                elif session.statut == SessionAcademique.StatutSession.EN_COURS:
                    statut = CoursDeSession.StatutCours.EN_COURS if rang < 3 else CoursDeSession.StatutCours.EVALUATION
                else:
                    statut = CoursDeSession.StatutCours.PROGRAMME

                programme, _ = CoursDeSession.objects.get_or_create(
                    session=session,
                    cours=cours_courant,
                    defaults={
                        "enseignant": enseignant,
                        "modalite": modalites[rang % len(modalites)],
                        "salle": salles[rang % len(salles)],
                        "horaires": "Lundi au vendredi, 8 h 00 – 12 h 00",
                        "statut": statut,
                        "capacite": 25,
                        "inscriptions_ouvertes": session.statut == SessionAcademique.StatutSession.PLANIFIEE,
                        "date_limite_inscription": session.date_debut - timedelta(days=15),
                        "frais_inscription": Decimal("120.00"),
                        "informations_pratiques": (
                            "Prévoir une bible d'étude et de quoi prendre des notes. "
                            "Restauration possible sur place le midi."
                        ),
                    },
                )
                programmes.append(programme)
        return programmes

    # ── Inscriptions et demandes ─────────────────────────────
    def _seed_inscriptions(self, etudiants, cours_sessions) -> None:
        """Remplit les classes, puis ajoute des demandes encore à trancher.

        Le peuplement se fait **par cours** et non par étudiant. Réparti par
        étudiant, chaque classe finissait avec un ou deux inscrits : les écrans
        de l'enseignant — liste des inscrits, copies à corriger, publication des
        notes — restaient squelettiques, et certains professeurs n'avaient
        aucune copie du tout.
        """
        inscriptibles = [
            e
            for e in etudiants
            if e.statut_inscription
            in (
                ProfilEtudiant.StatutInscription.ACTIF,
                ProfilEtudiant.StatutInscription.INSCRIT,
                ProfilEtudiant.StatutInscription.DIPLOME,
            )
        ]
        if not inscriptibles:
            return

        # 1 — Chaque cours déjà commencé reçoit un effectif réel.
        commences = [
            c
            for c in cours_sessions
            if c.statut
            in (
                CoursDeSession.StatutCours.EN_COURS,
                CoursDeSession.StatutCours.EVALUATION,
                CoursDeSession.StatutCours.TERMINE,
            )
        ]
        depart = 0
        for programme in commences:
            effectif = 6 + (programme.pk % 3)  # entre 6 et 8 inscrits
            for rang in range(effectif):
                etudiant = inscriptibles[(depart + rang) % len(inscriptibles)]
                demande, _ = DemandeInscriptionCours.objects.get_or_create(
                    etudiant=etudiant,
                    cours_session=programme,
                    defaults={
                        "statut": DemandeInscriptionCours.Statut.CONFIRMEE,
                        "montant_du": programme.frais_inscription,
                        "note_etudiant": "Demande déposée depuis le portail étudiant.",
                        "date_decision": timezone.now(),
                    },
                )
                if demande.statut == DemandeInscriptionCours.Statut.CONFIRMEE:
                    InscriptionSession.objects.get_or_create(
                        etudiant=etudiant,
                        cours_session=programme,
                        defaults={"demande": demande},
                    )
            depart += 2  # décalage : les classes ne sont pas toutes identiques

        # 2 — Sur les cours à venir, des demandes dans les états que le
        #     secrétariat doit trancher. C'est sa file de travail.
        a_trancher = [
            DemandeInscriptionCours.Statut.SOUMISE,
            DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE,
            DemandeInscriptionCours.Statut.SOUMISE,
            DemandeInscriptionCours.Statut.REFUSEE,
            DemandeInscriptionCours.Statut.ANNULEE,
        ]
        futurs = [c for c in cours_sessions if c.statut == CoursDeSession.StatutCours.PROGRAMME]
        compteur = 0
        for programme in futurs:
            for rang in range(4):
                etudiant = inscriptibles[(compteur + rang) % len(inscriptibles)]
                statut = a_trancher[compteur % len(a_trancher)]
                compteur += 1
                DemandeInscriptionCours.objects.get_or_create(
                    etudiant=etudiant,
                    cours_session=programme,
                    defaults={
                        "statut": statut,
                        "montant_du": programme.frais_inscription,
                        "note_etudiant": "Demande déposée depuis le portail étudiant.",
                        "motif_decision": (
                            "Capacité atteinte pour cette session."
                            if statut == DemandeInscriptionCours.Statut.REFUSEE
                            else ""
                        ),
                        "date_decision": (timezone.now() if statut == DemandeInscriptionCours.Statut.REFUSEE else None),
                    },
                )

    # ── Finances ─────────────────────────────────────────────
    def _seed_paiements(self, etudiants, sessions) -> None:
        modes = [
            Paiement.ModePaiement.VIREMENT,
            Paiement.ModePaiement.CARTE,
            Paiement.ModePaiement.CHEQUE,
            Paiement.ModePaiement.ESPECES,
        ]
        aujourdhui = timezone.localdate()

        for index, etudiant in enumerate(etudiants):
            if etudiant.statut_inscription == ProfilEtudiant.StatutInscription.PRE_INSCRIT:
                continue  # rien n'est encore dû
            statut = (
                Paiement.StatutPaiement.EN_ATTENTE
                if etudiant.statut_inscription == ProfilEtudiant.StatutInscription.PAIEMENT_ATTENTE
                else Paiement.StatutPaiement.CONFIRME
            )
            reference = f"PAI-DEMO-{etudiant.numero_etudiant}"
            Paiement.objects.get_or_create(
                reference=reference,
                defaults={
                    "etudiant": etudiant,
                    "session": sessions[index % len(sessions)],
                    "montant": Decimal("120.00") + Decimal(index % 4) * Decimal("30.00"),
                    "date_paiement": aujourdhui - timedelta(days=7 * (index % 8)),
                    "mode": modes[index % len(modes)],
                    "statut": statut,
                },
            )

    # ── Stages, VAE, crédits ─────────────────────────────────
    def _seed_stages_vae_ects(self, etudiants, professeurs, cours, sessions) -> None:
        aujourdhui = timezone.localdate()
        avances = [
            e
            for e in etudiants
            if e.statut_inscription
            in (ProfilEtudiant.StatutInscription.ACTIF, ProfilEtudiant.StatutInscription.DIPLOME)
        ]

        for index, etudiant in enumerate(avances[:6]):
            statut_stage = (
                Stage.StatutStage.VALIDE
                if etudiant.statut_inscription == ProfilEtudiant.StatutInscription.DIPLOME
                else Stage.StatutStage.EN_COURS
            )
            Stage.objects.get_or_create(
                etudiant=etudiant,
                type_stage="Stage pastoral en Église locale",
                defaults={
                    "lieu": ["Pointe-à-Pitre", "Cayenne", "Fort-de-France", "Basse-Terre"][index % 4],
                    "tuteur": professeurs[index % len(professeurs)],
                    "date_debut": aujourdhui - timedelta(days=180),
                    "date_fin": aujourdhui - timedelta(days=30)
                    if statut_stage == Stage.StatutStage.VALIDE
                    else aujourdhui + timedelta(days=60),
                    "ects": Decimal("30.0"),
                    "statut": statut_stage,
                },
            )

        for index, etudiant in enumerate(avances[:4]):
            statut_vae = [VAE.StatutVAE.ACCORDE, VAE.StatutVAE.EN_EXAMEN, VAE.StatutVAE.SOUMIS, VAE.StatutVAE.REFUSE][
                index % 4
            ]
            VAE.objects.get_or_create(
                etudiant=etudiant,
                defaults={
                    "description_experience": (
                        "Douze années de responsabilité dans une Église locale : prédication régulière, "
                        "accompagnement pastoral et formation de moniteurs d'école du dimanche."
                    ),
                    "ects_demandes": Decimal("20.0"),
                    "ects_accordes": Decimal("15.0") if statut_vae == VAE.StatutVAE.ACCORDE else Decimal("0.0"),
                    "statut": statut_vae,
                    "date_soumission": aujourdhui - timedelta(days=90),
                    "date_decision": aujourdhui - timedelta(days=20)
                    if statut_vae in (VAE.StatutVAE.ACCORDE, VAE.StatutVAE.REFUSE)
                    else None,
                },
            )

        for index, etudiant in enumerate(avances):
            for rang in range(3):
                cours_valide = cours[(index + rang) % len(cours)]
                CreditECTS.objects.get_or_create(
                    etudiant=etudiant,
                    cours=cours_valide,
                    session=sessions[rang % len(sessions)],
                    defaults={
                        "ects_obtenus": cours_valide.ects or Decimal("5.0"),
                        "source": CreditECTS.SourceCredit.ITEAG,
                        "date_validation": aujourdhui - timedelta(days=45 * (rang + 1)),
                    },
                )
