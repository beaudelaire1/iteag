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

    # ── Coordonnées ──
    #
    # Portées par le compte, et non par le profil étudiant : un enseignant et
    # une secrétaire ont une adresse et un téléphone comme un étudiant, et le
    # même écran doit pouvoir les tenir à jour. Le dossier de scolarité, lui,
    # garde ce qui n'a de sens que pour un étudiant (église, promotion, tarif).
    photo = models.ImageField(
        upload_to="comptes/photos/%Y/",
        blank=True,
        verbose_name="Photo",
        help_text="Portrait affiché dans les espaces privés et sur la fiche de scolarité.",
    )
    signature = models.ImageField(
        upload_to="comptes/signatures/%Y/",
        blank=True,
        verbose_name="Signature numérique",
        help_text="Image PNG, JPEG ou WebP apposée sur les documents que vous rédigez.",
    )
    titre_qualite_signature = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Titre / Qualité du signataire",
        help_text=(
            "Titre officiel apparaissant sur les documents (ex: Le secrétariat, Le Directeur, Le Secrétaire Général)."
        ),
    )
    nom_autorite_signature = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Nom de l'autorité / du signataire",
        help_text=(
            "Nom du signataire ou de l'autorité apparaissant au bas des documents (ex: Jean DUPONT, Secrétariat ITEAG)."
        ),
    )
    adresse = models.CharField(max_length=250, blank=True, verbose_name="Adresse")
    complement_adresse = models.CharField(max_length=250, blank=True, verbose_name="Complément d'adresse")
    code_postal = models.CharField(max_length=20, blank=True, verbose_name="Code postal")
    ville = models.CharField(max_length=120, blank=True, verbose_name="Ville")
    pays = models.CharField(max_length=120, blank=True, default="Guadeloupe", verbose_name="Pays")

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        full = self.get_full_name()
        return full if full else self.username

    @property
    def initiales(self) -> str:
        """Repli lorsqu'aucune photo n'est déposée."""
        return f"{self.first_name[:1]}{self.last_name[:1]}".upper() or self.username[:2].upper()

    @property
    def adresse_postale(self) -> str:
        """Adresse sur une ligne, sans virgule orpheline si un champ manque."""
        lignes = [self.adresse, self.complement_adresse, " ".join(filter(None, [self.code_postal, self.ville]))]
        return ", ".join(part for part in (ligne.strip() for ligne in lignes) if part)

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
