from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel


class SeanceCours(TimeStampedModel):
    """Créneau réel d'un cours utilisé pour l'émargement numérique."""

    cours_session = models.ForeignKey(
        "academics.CoursDeSession",
        on_delete=models.CASCADE,
        related_name="seances_assiduite",
        verbose_name="Cours de session",
    )
    date = models.DateField()
    heure_debut = models.TimeField(verbose_name="Heure de début")
    heure_fin = models.TimeField(verbose_name="Heure de fin")
    libelle = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Intitulé",
        help_text="Facultatif : matin, examen, atelier…",
    )
    cloturee = models.BooleanField(
        default=False,
        verbose_name="Feuille clôturée",
        help_text="Une feuille clôturée n'est plus modifiable avant sa réouverture.",
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seances_assiduite_creees",
    )

    class Meta:
        verbose_name = "Séance de cours"
        verbose_name_plural = "Séances de cours"
        ordering = ["-date", "-heure_debut"]
        constraints = [
            models.UniqueConstraint(
                fields=["cours_session", "date", "heure_debut"],
                name="seance_assiduite_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(heure_fin__gt=models.F("heure_debut")),
                name="seance_assiduite_fin_apres_debut",
            ),
        ]
        indexes = [
            models.Index(fields=["cours_session", "-date"], name="academics_s_cours_s_8752db_idx"),
        ]

    def __str__(self):
        return f"{self.cours_session} — {self.date:%d/%m/%Y} {self.heure_debut:%H:%M}"

    def clean(self):
        super().clean()
        if self.heure_debut and self.heure_fin and self.heure_fin <= self.heure_debut:
            raise ValidationError({"heure_fin": "L'heure de fin doit suivre l'heure de début."})
        if self.cours_session_id and self.date:
            session = self.cours_session.session
            if not session.date_debut <= self.date <= session.date_fin:
                raise ValidationError({"date": "La séance doit être comprise dans les dates de la session académique."})


class Presence(TimeStampedModel):
    """État d'assiduité d'un étudiant pour une séance."""

    class Statut(models.TextChoices):
        PRESENT = "present", "Présent"
        ABSENT = "absent", "Absent"
        RETARD = "retard", "En retard"
        EXCUSE = "excuse", "Absence excusée"

    seance = models.ForeignKey(
        SeanceCours,
        on_delete=models.CASCADE,
        related_name="presences",
    )
    etudiant = models.ForeignKey(
        "academics.ProfilEtudiant",
        on_delete=models.CASCADE,
        related_name="presences",
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.PRESENT)
    commentaire = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Commentaire",
        help_text="Motif, durée du retard ou précision utile.",
    )
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presences_saisies",
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presences_modifiees",
    )

    class Meta:
        verbose_name = "Présence"
        verbose_name_plural = "Présences"
        ordering = ["seance__date", "etudiant__utilisateur__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["seance", "etudiant"],
                name="presence_unique_par_seance_et_etudiant",
            )
        ]
        indexes = [
            models.Index(fields=["etudiant", "statut"], name="academics_p_etudian_5abdb4_idx"),
            models.Index(fields=["seance", "statut"], name="academics_p_seance__b0148b_idx"),
        ]

    def __str__(self):
        return f"{self.etudiant} — {self.seance} : {self.get_statut_display()}"

    def clean(self):
        super().clean()
        if self.seance_id and self.etudiant_id:
            from apps.academics.models import InscriptionSession

            inscrit = InscriptionSession.objects.filter(
                cours_session=self.seance.cours_session,
                etudiant=self.etudiant,
            ).exists()
            if not inscrit:
                raise ValidationError({"etudiant": "Cet étudiant n'est pas inscrit à ce cours de session."})


class HistoriquePresence(TimeStampedModel):
    """Trace les corrections apportées à une présence déjà enregistrée."""

    presence = models.ForeignKey(
        Presence,
        on_delete=models.CASCADE,
        related_name="historique",
    )
    ancien_statut = models.CharField(max_length=20, choices=Presence.Statut.choices)
    nouveau_statut = models.CharField(max_length=20, choices=Presence.Statut.choices)
    ancien_commentaire = models.CharField(max_length=300, blank=True)
    nouveau_commentaire = models.CharField(max_length=300, blank=True)
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="corrections_assiduite",
    )

    class Meta:
        verbose_name = "Correction de présence"
        verbose_name_plural = "Corrections de présence"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["presence", "-created_at"], name="academics_h_presenc_f6b852_idx")]

    def __str__(self):
        return f"{self.presence_id} : {self.ancien_statut} → {self.nouveau_statut}"
