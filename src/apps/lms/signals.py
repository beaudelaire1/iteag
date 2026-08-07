"""Invariants transversaux du LMS.

Un questionnaire incomplet ne doit jamais devenir visible, quel que soit le
point d'entrée utilisé pour le publier. Le contrôle est donc placé au niveau du
modèle sauvegardé, en complément des messages explicites du portail enseignant.
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.lms.models import Devoir


@receiver(pre_save, sender=Devoir)
def refuser_publication_qcm_incomplet(sender, instance: Devoir, **kwargs):
    if instance.modalite != Devoir.Modalite.QCM or instance.statut != Devoir.Statut.PUBLIE:
        return

    if not instance.pk:
        raise ValidationError("Enregistrez d'abord le questionnaire en brouillon avant de le publier.")

    # Import tardif pour éviter une dépendance circulaire pendant le chargement
    # des modèles. À ce stade, l'application Django est complètement initialisée.
    from apps.lms.services import motif_qcm_incomplet

    probleme = motif_qcm_incomplet(instance)
    if probleme:
        raise ValidationError(f"Questionnaire incomplet : {probleme}")
