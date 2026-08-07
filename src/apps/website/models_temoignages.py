from django.conf import settings
from django.db import models


class TemoignageEtudiant(models.Model):
    """Témoignage proposé depuis l'espace étudiant puis modéré par la direction.

    Le nom et la promotion sont figés au moment de la soumission : un témoignage
    publié reste compréhensible si le profil change plus tard. Le lien vers le
    compte reste facultatif afin qu'une suppression de compte n'efface pas une
    publication déjà autorisée.
    """

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        PUBLIE = "publie", "Publié"
        REFUSE = "refuse", "Refusé"

    etudiant = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="temoignage_iteag",
        limit_choices_to={"role": "etudiant"},
        verbose_name="Étudiant",
    )
    nom_affiche = models.CharField(max_length=160, verbose_name="Nom affiché")
    promotion = models.CharField(max_length=160, blank=True, verbose_name="Promotion / parcours")
    texte = models.TextField(max_length=2000, verbose_name="Témoignage")
    consentement_publication = models.BooleanField(default=False, verbose_name="Consentement à la publication")
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE, db_index=True)
    motif_refus = models.CharField(max_length=500, blank=True, verbose_name="Motif du refus")
    soumis_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)
    valide_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="temoignages_valides",
        verbose_name="Validé par",
    )

    class Meta:
        app_label = "website"
        verbose_name = "Témoignage étudiant"
        verbose_name_plural = "Témoignages étudiants"
        ordering = ["-soumis_le"]

    def __str__(self):
        return f"{self.nom_affiche} — {self.get_statut_display()}"
