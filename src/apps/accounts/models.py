from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model for the ITEAG platform.
    Uses email as the display identifier but keeps username for Wagtail compatibility.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Administrateur"
        SECRETARIAT = "secretariat", "Secrétariat"
        ENSEIGNANT = "enseignant", "Enseignant"
        ETUDIANT = "etudiant", "Étudiant"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.ETUDIANT,
        verbose_name="Rôle",
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        full = self.get_full_name()
        return full if full else self.username

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_secretariat(self):
        return self.role == self.Role.SECRETARIAT

    @property
    def is_enseignant(self):
        return self.role == self.Role.ENSEIGNANT

    @property
    def is_etudiant(self):
        return self.role == self.Role.ETUDIANT
